"""PR21 - Testes do helper DataJud (service + rota)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest


def _usuario_fake():
    return {"id": "u1", "nome": "Advogado", "email": "a@a.com", "usuario_id": "u1"}


def _fake_request(path="/api/datajud/validar"):
    from fastapi import Request

    return Request(
        scope={
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 0),
        }
    )


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# Normalizacao de numero CNJ
# ─────────────────────────────────────────────────────────────────────────────


class TestNormalizarNumeroCNJ:
    def test_remove_formatacao_padrao(self):
        from App.services.datajud_service import normalizar_numero_cnj

        assert (
            normalizar_numero_cnj("0000793-00.2009.5.04.0018") == "00007930020095040018"
        )

    def test_aceita_numero_ja_unformatado(self):
        from App.services.datajud_service import normalizar_numero_cnj

        assert normalizar_numero_cnj("00793000920095040018") == "00793000920095040018"

    def test_remove_espacos_internos(self):
        from App.services.datajud_service import normalizar_numero_cnj

        assert (
            normalizar_numero_cnj("0079300 09 2009 5 04 0018") == "00793000920095040018"
        )

    def test_rejeita_numero_curto(self):
        from App.services.datajud_service import normalizar_numero_cnj

        with pytest.raises(ValueError, match="20 digitos"):
            normalizar_numero_cnj("1234")

    def test_rejeita_string_vazia(self):
        from App.services.datajud_service import normalizar_numero_cnj

        with pytest.raises(ValueError):
            normalizar_numero_cnj("")


# ─────────────────────────────────────────────────────────────────────────────
# DataJudClient
# ─────────────────────────────────────────────────────────────────────────────


class TestDataJudClient:
    def test_resolver_alias_aceita_siglas_conhecidas(self):
        from App.services.datajud_service import DataJudClient

        c = DataJudClient()
        assert c._resolver_alias("tst") == "api_publica_tst"
        assert c._resolver_alias("STJ") == "api_publica_stj"  # case-insensitive
        assert c._resolver_alias(" trt6 ") == "api_publica_trt6"  # trim

    def test_resolver_alias_rejeita_tribunal_desconhecido(self):
        from App.services.datajud_service import DataJudClient

        with pytest.raises(ValueError, match="nao suportado"):
            DataJudClient()._resolver_alias("xyz")

    def test_buscar_por_numero_monta_payload_correto(self):
        from App.services.datajud_service import DataJudClient

        c = DataJudClient(rate_limit_sec=0)  # zera rate limit pro teste
        resp_mock = MagicMock()
        resp_mock.ok = True
        resp_mock.status_code = 200
        resp_mock.json.return_value = {"hits": {"hits": []}}
        with patch.object(c.session, "post", return_value=resp_mock) as mocked:
            c.buscar_por_numero("0000793-00.2009.5.04.0018", "tst")

        args, kwargs = mocked.call_args
        assert args[0].endswith("/api_publica_tst/_search")
        assert (
            kwargs["json"]["query"]["term"]["numeroProcesso"] == "00007930020095040018"
        )

    def test_buscar_por_numero_retorna_none_sem_hits(self):
        from App.services.datajud_service import DataJudClient

        c = DataJudClient(rate_limit_sec=0)
        resp_mock = MagicMock()
        resp_mock.ok = True
        resp_mock.json.return_value = {"hits": {"hits": []}}
        with patch.object(c.session, "post", return_value=resp_mock):
            assert c.buscar_por_numero("00793000920095040018", "tst") is None

    def test_buscar_por_numero_retorna_source_quando_acha(self):
        from App.services.datajud_service import DataJudClient

        c = DataJudClient(rate_limit_sec=0)
        source = {
            "numeroProcesso": "00793000920095040018",
            "tribunal": "TST",
            "classe": {"codigo": 1002, "nome": "Agravo"},
        }
        resp_mock = MagicMock()
        resp_mock.ok = True
        resp_mock.json.return_value = {"hits": {"hits": [{"_source": source}]}}
        with patch.object(c.session, "post", return_value=resp_mock):
            doc = c.buscar_por_numero("00793000920095040018", "tst")

        assert doc == source

    def test_401_levanta_datajuderror_explicito(self):
        from App.services.datajud_service import DataJudClient, DataJudError

        c = DataJudClient(rate_limit_sec=0)
        resp_mock = MagicMock()
        resp_mock.ok = False
        resp_mock.status_code = 401
        resp_mock.text = "Unauthorized"
        with patch.object(c.session, "post", return_value=resp_mock):
            with pytest.raises(DataJudError, match="API key publica.*rotacionada"):
                c.buscar_por_numero("00793000920095040018", "tst")

    def test_erro_de_rede_vira_datajuderror(self):
        import requests

        from App.services.datajud_service import DataJudClient, DataJudError

        c = DataJudClient(rate_limit_sec=0)
        with patch.object(
            c.session, "post", side_effect=requests.ConnectionError("offline")
        ):
            with pytest.raises(DataJudError, match="rede"):
                c.buscar_por_numero("00793000920095040018", "tst")

    def test_validar_processo_nunca_levanta_excecao(self):
        """validar_processo eh user-facing — embrulha qualquer erro em dict."""
        from App.services.datajud_service import DataJudClient

        c = DataJudClient(rate_limit_sec=0)
        # numero invalido — ValueError sai como erro:
        resultado = c.validar_processo("123", "tst")
        assert resultado["existe"] is False
        assert resultado["metadata"] is None
        assert "20 digitos" in resultado["erro"]

    def test_destilar_metadata_extrai_campos_essenciais(self):
        from App.services.datajud_service import DataJudClient

        doc = {
            "numeroProcesso": "00793000920095040018",
            "tribunal": "TST",
            "grau": "SUP",
            "classe": {"codigo": 1002, "nome": "AIRR"},
            "sistema": {"codigo": 1, "nome": "PJe"},
            "formato": {"codigo": 1, "nome": "Eletronico"},
            "dataAjuizamento": "20111011222556",
            "dataHoraUltimaAtualizacao": "2026-06-01T23:48:59Z",
            "movimentos": [
                {"orgaoJulgador": {"nome": "GAB. MIN. X"}},
                {"orgaoJulgador": {"nome": "GAB. MIN. Y"}},  # mais recente
            ],
        }
        meta = DataJudClient._destilar_metadata(doc)

        assert meta["numero_processo"] == "00793000920095040018"
        assert meta["tribunal"] == "TST"
        assert meta["classe_codigo"] == 1002
        assert meta["classe_nome"] == "AIRR"
        assert meta["sistema"] == "PJe"
        assert meta["formato"] == "Eletronico"
        assert meta["data_ajuizamento"] == "20111011222556"
        # ultimo movimento com orgaoJulgador setado:
        assert meta["orgao_julgador_atual"] == "GAB. MIN. Y"
        assert meta["total_movimentos"] == 2

    def test_destilar_metadata_tolera_campos_faltantes(self):
        """Doc minimalista nao explode — DataJud as vezes omite campos."""
        from App.services.datajud_service import DataJudClient

        meta = DataJudClient._destilar_metadata({"numeroProcesso": "X"})
        assert meta["numero_processo"] == "X"
        assert meta["classe_codigo"] is None
        assert meta["orgao_julgador_atual"] is None
        assert meta["total_movimentos"] == 0

    def test_rate_limit_aplica_sleep_entre_chamadas(self, monkeypatch):
        """Segunda chamada consecutiva deve aguardar rate_limit_sec."""
        from App.services.datajud_service import DataJudClient

        sleeps: list[float] = []
        monkeypatch.setattr(
            "App.services.datajud_service.time.sleep",
            lambda s: sleeps.append(s),
        )

        c = DataJudClient(rate_limit_sec=1.0)
        resp_mock = MagicMock()
        resp_mock.ok = True
        resp_mock.json.return_value = {"hits": {"hits": []}}
        with patch.object(c.session, "post", return_value=resp_mock):
            c.buscar_por_numero("00793000920095040018", "tst")
            c.buscar_por_numero("00793000920095040018", "tst")

        # Segunda chamada gerou um sleep > 0
        assert any(s > 0 for s in sleeps)


# ─────────────────────────────────────────────────────────────────────────────
# Rota POST /api/datajud/validar
# ─────────────────────────────────────────────────────────────────────────────


class TestRotaValidar:
    def test_payload_vazio_retorna_erro_claro(self):
        from App.routes import datajud as route

        resp = _run(
            route.validar_processo(
                request=_fake_request(),
                payload={},
                usuario=_usuario_fake(),
            )
        )
        assert resp["existe"] is False
        assert resp["metadata"] is None
        assert "tribunal" in resp["erro"].lower()

    def test_tribunal_invalido_retorna_erro_sem_explodir(self):
        from App.routes import datajud as route

        resp = _run(
            route.validar_processo(
                request=_fake_request(),
                payload={"numero_processo": "00793000920095040018", "tribunal": "xyz"},
                usuario=_usuario_fake(),
            )
        )
        assert resp["existe"] is False
        assert "nao suportado" in resp["erro"]

    def test_chamada_valida_retorna_estrutura_correta(self):
        from App.routes import datajud as route
        from App.services.datajud_service import DataJudClient

        # Mocka o cliente singleton pra evitar rede real
        cliente_mock = DataJudClient(rate_limit_sec=0)
        source = {
            "numeroProcesso": "00793000920095040018",
            "tribunal": "TST",
            "classe": {"codigo": 1002, "nome": "AIRR"},
            "movimentos": [],
        }
        resp_mock = MagicMock()
        resp_mock.ok = True
        resp_mock.json.return_value = {"hits": {"hits": [{"_source": source}]}}

        with (
            patch.object(cliente_mock.session, "post", return_value=resp_mock),
            patch("App.routes.datajud._get_cliente", return_value=cliente_mock),
        ):
            resp = _run(
                route.validar_processo(
                    request=_fake_request(),
                    payload={
                        "numero_processo": "0000793-00.2009.5.04.0018",
                        "tribunal": "tst",
                    },
                    usuario=_usuario_fake(),
                )
            )

        assert resp["existe"] is True
        assert resp["metadata"]["classe_codigo"] == 1002
        assert resp["erro"] is None


class TestRotaListarTribunais:
    def test_retorna_lista_ordenada(self):
        from App.routes import datajud as route

        resp = _run(
            route.listar_tribunais_suportados(
                request=_fake_request(path="/api/datajud/tribunais"),
                usuario=_usuario_fake(),
            )
        )
        assert "tst" in resp["tribunais"]
        assert "stj" in resp["tribunais"]
        # ordenado:
        assert resp["tribunais"] == sorted(resp["tribunais"])

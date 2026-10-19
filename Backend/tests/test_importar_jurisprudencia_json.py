"""PR25 - Testes do script scripts/importar_jurisprudencia_json.py.

Cobre:
- 3 entradas validas → 3 upserts (mocka DB + embedding)
- Regex CNJ como fallback quando numero_processo faltar
- Haiku fallback quando ementa faltar (mocka HTTP)
- Skip quando falta tribunal / numero / ementa e sem ANTHROPIC_API_KEY
- texto_integral de 30 KB propagado intacto
- Arquivo inexistente / JSON invalido → exit 1
"""

import json
from unittest.mock import MagicMock

import pytest


def _importar():
    """Import tardio pra pegar o script sob teste."""
    import scripts.importar_jurisprudencia_json as script

    return script


# ─────────────────────────────────────────────────────────────────────────────
# _extrair_cnj
# ─────────────────────────────────────────────────────────────────────────────


class TestExtrairCNJ:
    def test_encontra_numero_cnj_no_meio_do_texto(self):
        script = _importar()
        texto = "acordao TRF5 processo 0001234-56.2023.4.05.8300 relator..."
        assert script._extrair_cnj(texto) == "0001234-56.2023.4.05.8300"

    def test_retorna_none_quando_nao_ha_cnj(self):
        script = _importar()
        assert script._extrair_cnj("texto sem numero de processo") is None
        assert script._extrair_cnj("") is None
        assert script._extrair_cnj(None) is None


# ─────────────────────────────────────────────────────────────────────────────
# _destilar_ementa_via_haiku
# ─────────────────────────────────────────────────────────────────────────────


class TestDestilarEmentaHaiku:
    def test_retorna_texto_extraido_quando_haiku_responde(self, monkeypatch):
        script = _importar()
        resp = MagicMock()
        resp.ok = True
        resp.status_code = 200
        resp.json.return_value = {
            "content": [{"type": "text", "text": "EMENTA DESTILADA PELO HAIKU"}]
        }
        monkeypatch.setattr(script.requests, "post", lambda *a, **kw: resp)

        out = script._destilar_ementa_via_haiku(
            "conteudo integral do acordao", api_key="fake-key"
        )
        assert out == "EMENTA DESTILADA PELO HAIKU"

    def test_retorna_none_sem_api_key(self):
        script = _importar()
        assert script._destilar_ementa_via_haiku("texto", api_key="") is None
        assert script._destilar_ementa_via_haiku("texto", api_key=None) is None

    def test_retorna_none_em_http_error(self, monkeypatch):
        script = _importar()
        resp = MagicMock()
        resp.ok = False
        resp.status_code = 500
        resp.text = "server error"
        monkeypatch.setattr(script.requests, "post", lambda *a, **kw: resp)

        assert script._destilar_ementa_via_haiku("texto", api_key="fake-key") is None

    def test_retorna_none_em_erro_de_rede(self, monkeypatch):
        script = _importar()
        import requests

        def boom(*a, **kw):
            raise requests.ConnectionError("offline")

        monkeypatch.setattr(script.requests, "post", boom)

        assert script._destilar_ementa_via_haiku("texto", api_key="fake-key") is None


# ─────────────────────────────────────────────────────────────────────────────
# _processar_entrada
# ─────────────────────────────────────────────────────────────────────────────


class TestProcessarEntrada:
    def _kwargs_base(self, **overrides):
        base = {
            "indice": 1,
            "total": 3,
            "api_key": None,
            "dry_run": False,
        }
        base.update(overrides)
        return base

    def test_entrada_completa_chama_upsert(self, monkeypatch):
        script = _importar()
        chamado = {}

        def fake_upsert(**kw):
            chamado.update(kw)

        monkeypatch.setattr(script, "upsert_jurisprudencia", fake_upsert)
        monkeypatch.setattr(script, "gerar_embedding", lambda t: [0.1] * 384)

        entry = {
            "tribunal": "TRF5",
            "numero_processo": "0001234-56.2023.4.05.8300",
            "ementa": "APELACAO CIVEL. Ementa completa aqui.",
            "conteudo": "texto integral do acordao aqui",
            "relator": "Des. X",
            "data_julgamento": "2023-05-10",
            "area_juridica": "trabalhista",
            "peso_relevancia": 7,
        }
        resultado = script._processar_entrada(entry, **self._kwargs_base())
        assert resultado == "ok"
        assert chamado["tribunal"] == "TRF5"
        assert chamado["numero_processo"] == "0001234-56.2023.4.05.8300"
        assert chamado["ementa"] == "APELACAO CIVEL. Ementa completa aqui."
        assert chamado["texto_integral"] == "texto integral do acordao aqui"
        assert chamado["peso_relevancia"] == 7

    def test_regex_cnj_extrai_numero_quando_faltar_no_json(self, monkeypatch):
        script = _importar()
        chamado = {}
        monkeypatch.setattr(
            script, "upsert_jurisprudencia", lambda **kw: chamado.update(kw)
        )
        monkeypatch.setattr(script, "gerar_embedding", lambda t: [0.1] * 384)

        entry = {
            "tribunal": "TRF5",
            "ementa": "EMENTA. Fatos processuais relevantes.",
            "conteudo": "no processo 0001234-56.2023.4.05.8300 foi decidido...",
        }
        assert script._processar_entrada(entry, **self._kwargs_base()) == "ok"
        assert chamado["numero_processo"] == "0001234-56.2023.4.05.8300"

    def test_skip_sem_tribunal(self, monkeypatch):
        script = _importar()
        monkeypatch.setattr(
            script,
            "upsert_jurisprudencia",
            lambda **kw: pytest.fail("upsert nao devia ter sido chamado"),
        )
        entry = {"numero_processo": "X", "ementa": "..."}
        assert script._processar_entrada(entry, **self._kwargs_base()) == "skip"

    def test_skip_sem_numero_e_sem_cnj_no_conteudo(self, monkeypatch):
        script = _importar()
        monkeypatch.setattr(
            script,
            "upsert_jurisprudencia",
            lambda **kw: pytest.fail("upsert nao devia ter sido chamado"),
        )
        entry = {"tribunal": "TRF5", "ementa": "sem numero", "conteudo": "sem cnj"}
        assert script._processar_entrada(entry, **self._kwargs_base()) == "skip"

    def test_haiku_destila_ementa_quando_falta(self, monkeypatch):
        script = _importar()
        monkeypatch.setattr(
            script,
            "_destilar_ementa_via_haiku",
            lambda conteudo, **kw: "EMENTA DESTILADA",
        )
        chamado = {}
        monkeypatch.setattr(
            script, "upsert_jurisprudencia", lambda **kw: chamado.update(kw)
        )
        monkeypatch.setattr(script, "gerar_embedding", lambda t: [0.1] * 384)

        entry = {
            "tribunal": "TRF5",
            "numero_processo": "0001234-56.2023.4.05.8300",
            "conteudo": "texto sem ementa explicita",
        }
        resultado = script._processar_entrada(
            entry, **self._kwargs_base(api_key="fake-key")
        )
        assert resultado == "ok"
        assert chamado["ementa"] == "EMENTA DESTILADA"

    def test_skip_sem_ementa_e_sem_haiku_key(self, monkeypatch):
        script = _importar()
        monkeypatch.setattr(
            script,
            "upsert_jurisprudencia",
            lambda **kw: pytest.fail("upsert nao devia ter sido chamado"),
        )
        entry = {
            "tribunal": "TRF5",
            "numero_processo": "0001234-56.2023.4.05.8300",
            "conteudo": "texto grande sem ementa",
        }
        # api_key=None (default do kwargs_base)
        assert script._processar_entrada(entry, **self._kwargs_base()) == "skip"

    def test_texto_integral_grande_propagado_intacto(self, monkeypatch):
        script = _importar()
        chamado = {}
        monkeypatch.setattr(
            script, "upsert_jurisprudencia", lambda **kw: chamado.update(kw)
        )
        monkeypatch.setattr(script, "gerar_embedding", lambda t: [0.1] * 384)

        texto = "linha do acordao " * 2000  # ~34 KB
        entry = {
            "tribunal": "TRF5",
            "numero_processo": "0001234-56.2023.4.05.8300",
            "ementa": "Ementa curta.",
            "conteudo": texto,
        }
        assert script._processar_entrada(entry, **self._kwargs_base()) == "ok"
        # script normaliza conteudo via strip() — trailing whitespace removido
        assert chamado["texto_integral"] == texto.strip()
        assert len(chamado["texto_integral"]) > 30_000

    def test_dry_run_nao_chama_upsert(self, monkeypatch):
        script = _importar()
        monkeypatch.setattr(
            script,
            "upsert_jurisprudencia",
            lambda **kw: pytest.fail("dry_run nao devia chamar upsert"),
        )
        monkeypatch.setattr(script, "gerar_embedding", lambda t: [0.1] * 384)
        entry = {
            "tribunal": "TRF5",
            "numero_processo": "X-001",
            "ementa": "Ementa qualquer aqui.",
        }
        assert (
            script._processar_entrada(entry, **self._kwargs_base(dry_run=True)) == "ok"
        )


# ─────────────────────────────────────────────────────────────────────────────
# main()
# ─────────────────────────────────────────────────────────────────────────────


class TestMain:
    def test_arquivo_inexistente_retorna_1(self, monkeypatch, tmp_path):
        script = _importar()
        monkeypatch.setattr(
            "sys.argv",
            [
                "importar_jurisprudencia_json.py",
                f"--input={tmp_path / 'nao-existe.json'}",
            ],
        )
        assert script.main() == 1

    def test_json_invalido_retorna_1(self, monkeypatch, tmp_path):
        script = _importar()
        p = tmp_path / "invalido.json"
        p.write_text("{[nao e json valido", encoding="utf-8")
        monkeypatch.setattr(
            "sys.argv",
            [
                "importar_jurisprudencia_json.py",
                f"--input={p}",
            ],
        )
        assert script.main() == 1

    def test_json_nao_lista_retorna_1(self, monkeypatch, tmp_path):
        script = _importar()
        p = tmp_path / "objeto.json"
        p.write_text(json.dumps({"nao": "e lista"}), encoding="utf-8")
        monkeypatch.setattr(
            "sys.argv",
            [
                "importar_jurisprudencia_json.py",
                f"--input={p}",
            ],
        )
        assert script.main() == 1

    def test_ingere_3_entradas_validas(self, monkeypatch, tmp_path):
        script = _importar()
        entries = [
            {
                "tribunal": "TRF5",
                "numero_processo": "X-1",
                "ementa": "Ementa 1 " * 5,
                "conteudo": "texto 1",
            },
            {
                "tribunal": "TRT6",
                "numero_processo": "X-2",
                "ementa": "Ementa 2 " * 5,
                "conteudo": "texto 2",
            },
            {
                "tribunal": "TJRJ",
                "numero_processo": "X-3",
                "ementa": "Ementa 3 " * 5,
                "conteudo": "texto 3",
            },
        ]
        p = tmp_path / "seed.json"
        p.write_text(json.dumps(entries), encoding="utf-8")

        chamadas = []
        monkeypatch.setattr(
            script,
            "upsert_jurisprudencia",
            lambda **kw: chamadas.append(kw),
        )
        monkeypatch.setattr(script, "gerar_embedding", lambda t: [0.0] * 384)
        monkeypatch.setattr(
            "sys.argv",
            [
                "importar_jurisprudencia_json.py",
                f"--input={p}",
            ],
        )
        # Remove qualquer ANTHROPIC_API_KEY do env pra teste puro (sem Haiku)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        assert script.main() == 0
        assert len(chamadas) == 3
        assert {c["tribunal"] for c in chamadas} == {"TRF5", "TRT6", "TJRJ"}

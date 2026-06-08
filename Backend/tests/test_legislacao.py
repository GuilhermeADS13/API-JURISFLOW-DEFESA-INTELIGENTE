"""Testes da rota POST /api/legislacao/buscar e helpers DB (PR13 #B3)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest


def _usuario_fake():
    return {"id": "u1", "nome": "Advogado", "email": "a@a.com"}


def _payload(**kw):
    base = {
        "fatos": "Reclamante alega horas extras nao pagas alem da 44a hora semanal.",
        "pedidos": ["horas extras", "adicional de 50%"],
        "tese_central": "Improcedencia — onus do autor",
        "area_juridica": "trabalhista",
    }
    base.update(kw)
    return base


def _fake_request():
    from fastapi import Request

    return Request(
        scope={
            "type": "http",
            "method": "POST",
            "path": "/api/legislacao/buscar",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 0),
        }
    )


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# Rota
# ─────────────────────────────────────────────────────────────────────────────


class TestRotaBuscarLegislacao:
    def test_sem_texto_quando_tudo_vazio(self):
        from App.routes import legislacao as route

        resp = _run(
            route.buscar_legislacao(
                request=_fake_request(),
                payload={"fatos": "", "pedidos": [], "tese_central": ""},
                usuario=_usuario_fake(),
            )
        )
        assert resp["status"] == "sem_texto"
        assert resp["leis"] == []

    def test_sem_resultados_quando_ambas_buscas_vazias(self):
        from App.routes import legislacao as route

        emb = [0.1] * 384
        with (
            patch("App.routes.legislacao.gerar_embedding_query", return_value=emb),
            patch("App.routes.legislacao.buscar_legislacao_semantica", return_value=[]),
            patch("App.routes.legislacao.buscar_legislacao_lexical", return_value=[]),
        ):
            resp = _run(
                route.buscar_legislacao(
                    request=_fake_request(),
                    payload=_payload(),
                    usuario=_usuario_fake(),
                )
            )
        assert resp["status"] == "sem_resultados"
        assert resp["leis"] == []

    def test_sucesso_top5_via_rrf(self):
        from App.routes import legislacao as route

        def _make(origem, numero, texto, score):
            return {
                "origem": origem,
                "numero": numero,
                "texto": texto,
                "area_juridica": "trabalhista",
                "score": score,
            }

        semanticos = [
            _make("CLT", "art. 818", "onus", 0.9),
            _make("Sumula TST", "Sumula 338", "cartao ponto", 0.85),
            _make("CLT", "art. 74", "registro", 0.7),
        ]
        lexicais = [
            # Repete art. 818 — deve dedup via RRF
            _make("CLT", "art. 818", "onus", 0.5),
            _make("CF/88", "art. 7, XVI", "horas extras", 0.4),
        ]

        with (
            patch("App.routes.legislacao.gerar_embedding_query", return_value=[0.1] * 384),
            patch("App.routes.legislacao.buscar_legislacao_semantica", return_value=semanticos),
            patch("App.routes.legislacao.buscar_legislacao_lexical", return_value=lexicais),
        ):
            resp = _run(
                route.buscar_legislacao(
                    request=_fake_request(),
                    payload=_payload(),
                    usuario=_usuario_fake(),
                )
            )

        assert resp["status"] == "sucesso"
        # Sem duplicacao: 3 + 2 - 1 (compartilhado) = 4 unicos
        chaves = {(l["origem"], l["numero"]) for l in resp["leis"]}
        assert len(chaves) == 4
        # art. 818 aparece em ambas → maior RRF, top-1
        assert resp["leis"][0]["origem"] == "CLT"
        assert resp["leis"][0]["numero"] == "art. 818"

    def test_lexical_only_quando_embedding_indisponivel(self):
        """Embeddings off + lexical com hits → vira lexical-only."""
        from App.routes import legislacao as route

        lei_lex = {
            "origem": "CLT", "numero": "art. 71", "texto": "intervalo",
            "area_juridica": "trabalhista", "score": 0.5,
        }
        with (
            patch("App.routes.legislacao.gerar_embedding_query", return_value=None),
            patch("App.routes.legislacao.buscar_legislacao_lexical", return_value=[lei_lex]),
        ):
            resp = _run(
                route.buscar_legislacao(
                    request=_fake_request(),
                    payload=_payload(),
                    usuario=_usuario_fake(),
                )
            )
        assert resp["status"] == "sucesso"
        assert resp["leis"][0]["numero"] == "art. 71"

    def test_erro_em_uma_busca_nao_aborta(self):
        """semantica raise → lexical preenche; status continua sucesso."""
        from App.routes import legislacao as route

        lei = {
            "origem": "CLT", "numero": "art. 477", "texto": "verbas rescisorias",
            "area_juridica": "trabalhista", "score": 0.3,
        }
        with (
            patch("App.routes.legislacao.gerar_embedding_query", return_value=[0.1] * 384),
            patch(
                "App.routes.legislacao.buscar_legislacao_semantica",
                side_effect=RuntimeError("pgvector down"),
            ),
            patch("App.routes.legislacao.buscar_legislacao_lexical", return_value=[lei]),
        ):
            resp = _run(
                route.buscar_legislacao(
                    request=_fake_request(),
                    payload=_payload(),
                    usuario=_usuario_fake(),
                )
            )
        assert resp["status"] == "sucesso"
        assert len(resp["leis"]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Helpers DB (upsert + buscas individuais — guards)
# ─────────────────────────────────────────────────────────────────────────────


class TestHelpersDB:
    def test_upsert_skip_campos_obrigatorios_vazios(self):
        """upsert_legislacao com origem/numero/texto vazio eh no-op (sem tocar DB)."""
        from App import database as db

        # Sem mock — guard deve cortar antes de inicializar pool
        db.upsert_legislacao("", "art. 1", "texto")
        db.upsert_legislacao("CLT", "", "texto")
        db.upsert_legislacao("CLT", "art. 1", "")
        # Se chegou aqui sem RuntimeError, passou

    def test_buscar_lexical_retorna_vazio_sem_query(self):
        from App import database as db

        assert db.buscar_legislacao_lexical("") == []
        assert db.buscar_legislacao_lexical("   ") == []

    def test_buscar_semantica_filtra_area_canonica(self):
        """area_juridica invalida vira None (sem filtro), nao quebra SQL."""
        from App import database as db
        from unittest.mock import MagicMock

        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = lambda s: mock_conn
        mock_conn.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(db, "_ensure_db_initialized"),
            patch.object(db, "_get_connection") as mock_gc,
        ):
            mock_gc.return_value.__enter__ = lambda s: mock_conn
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            db.buscar_legislacao_semantica(
                embedding=[0.1] * 384,
                area_juridica="MARCIANO",  # invalida -> vira None
            )

        # Verifica que SQL foi chamado e o param de area foi None
        sql, params = mock_cur.execute.call_args.args
        # ordem dos params: vec_str, area, area, vec_str, limit
        assert params[1] is None  # area_canonica
        assert params[2] is None

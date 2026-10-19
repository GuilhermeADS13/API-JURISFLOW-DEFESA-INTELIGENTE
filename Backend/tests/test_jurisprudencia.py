"""PR19 — Testes da rota POST /api/jurisprudencia/buscar + helpers DB."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch


def _usuario_fake():
    return {"id": "u1", "nome": "Advogado", "email": "a@a.com"}


def _payload(**kw):
    base = {
        "fatos": "Reclamante alega horas extras nao pagas alem da 44a hora semanal.",
        "pedidos": ["horas extras", "adicional de 50%"],
        "tese_central": "Improcedencia",
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
            "path": "/api/jurisprudencia/buscar",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 0),
        }
    )


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_acordao(numero, tribunal="STJ", peso=5, score=0.8):
    return {
        "tribunal": tribunal,
        "tipo_decisao": "Acordao",
        "numero_processo": numero,
        "relator": "Min. X",
        "data_julgamento": "2023-05-10",
        "ementa": f"Ementa do {numero}",
        "tese_firmada": None,
        "area_juridica": "trabalhista",
        "peso_relevancia": peso,
        "fonte_url": "https://scon.stj.jus.br/...",
        "score": score,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Rota
# ─────────────────────────────────────────────────────────────────────────────


class TestRotaBuscarJurisprudencia:
    def test_sem_texto_quando_tudo_vazio(self):
        from App.routes import jurisprudencia as route

        resp = _run(
            route.buscar_jurisprudencia(
                request=_fake_request(),
                payload={"fatos": "", "pedidos": [], "tese_central": ""},
                usuario=_usuario_fake(),
            )
        )
        assert resp["status"] == "sem_texto"
        assert resp["acordaos"] == []

    def test_sem_resultados_quando_ambas_buscas_vazias(self):
        from App.routes import jurisprudencia as route

        emb = [0.1] * 384
        with (
            patch("App.routes.jurisprudencia.gerar_embedding_query", return_value=emb),
            patch(
                "App.routes.jurisprudencia.buscar_jurisprudencia_semantica",
                return_value=[],
            ),
            patch(
                "App.routes.jurisprudencia.buscar_jurisprudencia_lexical",
                return_value=[],
            ),
        ):
            resp = _run(
                route.buscar_jurisprudencia(
                    request=_fake_request(),
                    payload=_payload(),
                    usuario=_usuario_fake(),
                )
            )
        assert resp["status"] == "sem_resultados"
        assert resp["acordaos"] == []
        assert "scrape_jurisprudencia" in resp["detalhe"]

    def test_sucesso_top3_via_rrf(self):
        from App.routes import jurisprudencia as route

        semanticos = [
            _make_acordao("REsp 1.111/SP", peso=8),
            _make_acordao("REsp 2.222/MG", peso=5),
            _make_acordao("AgInt 3.333/RJ", peso=5),
        ]
        lexicais = [
            _make_acordao("REsp 1.111/SP", peso=8),  # repetido — RRF dedup
            _make_acordao("REsp 4.444/PR", peso=6),
        ]

        with (
            patch(
                "App.routes.jurisprudencia.gerar_embedding_query",
                return_value=[0.1] * 384,
            ),
            patch(
                "App.routes.jurisprudencia.buscar_jurisprudencia_semantica",
                return_value=semanticos,
            ),
            patch(
                "App.routes.jurisprudencia.buscar_jurisprudencia_lexical",
                return_value=lexicais,
            ),
        ):
            resp = _run(
                route.buscar_jurisprudencia(
                    request=_fake_request(),
                    payload=_payload(),
                    usuario=_usuario_fake(),
                )
            )

        assert resp["status"] == "sucesso"
        assert len(resp["acordaos"]) == 3  # cap
        chaves = {(a["tribunal"], a["numero_processo"]) for a in resp["acordaos"]}
        assert len(chaves) == 3
        # REsp 1.111 apareceu em ambas → topo
        assert resp["acordaos"][0]["numero_processo"] == "REsp 1.111/SP"

    def test_lexical_only_quando_embedding_off(self):
        from App.routes import jurisprudencia as route

        lex = _make_acordao("REsp 7.777/SC")
        with (
            patch("App.routes.jurisprudencia.gerar_embedding_query", return_value=None),
            patch(
                "App.routes.jurisprudencia.buscar_jurisprudencia_lexical",
                return_value=[lex],
            ),
        ):
            resp = _run(
                route.buscar_jurisprudencia(
                    request=_fake_request(),
                    payload=_payload(),
                    usuario=_usuario_fake(),
                )
            )
        assert resp["status"] == "sucesso"
        assert resp["acordaos"][0]["numero_processo"] == "REsp 7.777/SC"

    def test_erro_em_uma_busca_nao_aborta(self):
        from App.routes import jurisprudencia as route

        lex = _make_acordao("REsp 9.000/BA")
        with (
            patch(
                "App.routes.jurisprudencia.gerar_embedding_query",
                return_value=[0.1] * 384,
            ),
            patch(
                "App.routes.jurisprudencia.buscar_jurisprudencia_semantica",
                side_effect=RuntimeError("pgvector down"),
            ),
            patch(
                "App.routes.jurisprudencia.buscar_jurisprudencia_lexical",
                return_value=[lex],
            ),
        ):
            resp = _run(
                route.buscar_jurisprudencia(
                    request=_fake_request(),
                    payload=_payload(),
                    usuario=_usuario_fake(),
                )
            )
        assert resp["status"] == "sucesso"
        assert len(resp["acordaos"]) == 1

    def test_data_minima_default_eh_2000(self):
        """data_minima default da rota deve ser 2000-01-01.

        PR22: rebaixado de 2018-01-01 pra incluir Sumulas TST paradigma
        (Sum. 437/2012, Sum. 32/2003, Sum. 14/2003, etc) que continuam
        vigentes. Pra excluir decisao obsoleta, passar data_minima
        explicito no payload da rota.
        """
        from App.database import JURISPRUDENCIA_DATA_MINIMA_DEFAULT
        from App.routes import jurisprudencia as route

        assert JURISPRUDENCIA_DATA_MINIMA_DEFAULT == "2000-01-01"

        captured = {}

        def fake_sem(**kw):
            captured["sem"] = kw
            return []

        def fake_lex(**kw):
            captured["lex"] = kw
            return []

        with (
            patch(
                "App.routes.jurisprudencia.gerar_embedding_query",
                return_value=[0.1] * 384,
            ),
            patch(
                "App.routes.jurisprudencia.buscar_jurisprudencia_semantica",
                side_effect=fake_sem,
            ),
            patch(
                "App.routes.jurisprudencia.buscar_jurisprudencia_lexical",
                side_effect=fake_lex,
            ),
        ):
            _run(
                route.buscar_jurisprudencia(
                    request=_fake_request(),
                    payload=_payload(),  # sem data_minima explicita
                    usuario=_usuario_fake(),
                )
            )

        assert captured["sem"]["data_minima"] == "2000-01-01"
        assert captured["lex"]["data_minima"] == "2000-01-01"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers DB (guards + filtros sem tocar no banco)
# ─────────────────────────────────────────────────────────────────────────────


class TestHelpersDB:
    def test_upsert_skip_quando_campos_obrigatorios_vazios(self):
        """upsert_jurisprudencia ignora chamadas sem tribunal/numero/ementa."""
        from App import database as db

        # Guards cortam antes de inicializar pool — sem RuntimeError
        db.upsert_jurisprudencia("", "REsp 1/SP", "ementa")
        db.upsert_jurisprudencia("STJ", "", "ementa")
        db.upsert_jurisprudencia("STJ", "REsp 1/SP", "")

    def test_buscar_lexical_retorna_vazio_sem_query(self):
        from App import database as db

        assert db.buscar_jurisprudencia_lexical("") == []
        assert db.buscar_jurisprudencia_lexical("   ") == []

    def test_buscar_semantica_filtra_area_canonica_invalida(self):
        """area_juridica fora de canonicas vira None (sem filtro), nao quebra SQL."""
        from App import database as db

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

            db.buscar_jurisprudencia_semantica(
                embedding=[0.1] * 384,
                area_juridica="MARCIANA",  # invalida → vira None
            )

        sql, params = mock_cur.execute.call_args.args
        # ordem: vec, data_minima, area, area, limit
        assert params[2] is None
        assert params[3] is None

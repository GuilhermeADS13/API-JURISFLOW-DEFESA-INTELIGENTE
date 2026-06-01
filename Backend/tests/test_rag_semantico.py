"""Testes do RAG Semantico (PR6 #4 - Guia v3 §2.3).

Default agora e provider 'local' (sentence-transformers, 384 dims).
Providers pagos (cohere/openai) permanecem testados como caminhos opcionais.

Cobre:
- embedding_service: provider local + cohere/openai com mocks
- database: salvar_embedding / buscar_defesas_semanticas com DB mockado
- routes/rag: endpoint POST /api/rag/defesas-similares
- contestacao_peticao: _disparar_embedding (fire-and-forget sem bloquear)
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# embedding_service
# ─────────────────────────────────────────────────────────────────────────────


class TestEmbeddingService:
    def _emb(self, size=1024):
        return [0.1] * size

    def test_gerar_embedding_retorna_none_sem_chave_cohere(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "cohere")
        monkeypatch.delenv("COHERE_API_KEY", raising=False)
        from App.services.embedding_service import gerar_embedding

        assert gerar_embedding("texto qualquer") is None

    def test_gerar_embedding_retorna_none_sem_chave_openai(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from App.services.embedding_service import gerar_embedding

        assert gerar_embedding("texto qualquer") is None

    def test_gerar_embedding_retorna_none_provider_desconhecido(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "voyage")
        from App.services.embedding_service import gerar_embedding

        assert gerar_embedding("texto qualquer") is None

    def test_gerar_embedding_retorna_none_texto_vazio(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "cohere")
        monkeypatch.setenv("COHERE_API_KEY", "key-fake")
        from App.services.embedding_service import gerar_embedding

        assert gerar_embedding("") is None
        assert gerar_embedding("   ") is None

    def test_gerar_embedding_cohere_sucesso(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "cohere")
        monkeypatch.setenv("COHERE_API_KEY", "key-fake")

        emb = self._emb(1024)
        fake_client = MagicMock()
        fake_client.embed.return_value = MagicMock(embeddings=[emb])

        with patch("App.services.embedding_service._gerar_cohere") as mock_fn:
            mock_fn.return_value = emb
            from App.services.embedding_service import gerar_embedding

            resultado = gerar_embedding("texto de teste")

        assert resultado == emb

    def test_gerar_embedding_openai_sucesso(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")

        emb = self._emb(1024)
        with patch("App.services.embedding_service._gerar_openai") as mock_fn:
            mock_fn.return_value = emb
            from App.services.embedding_service import gerar_embedding

            resultado = gerar_embedding("texto de teste")

        assert resultado == emb

    def test_gerar_embedding_cohere_erro_api_retorna_none(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "cohere")
        monkeypatch.setenv("COHERE_API_KEY", "key-fake")

        # _gerar_cohere interno captura Exception e retorna None
        with patch("App.services.embedding_service._gerar_cohere", return_value=None):
            from App.services.embedding_service import gerar_embedding

            resultado = gerar_embedding("texto")

        assert resultado is None

    def test_gerar_embedding_query_usa_search_query_cohere(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "cohere")
        monkeypatch.setenv("COHERE_API_KEY", "key-fake")

        emb = self._emb(1024)
        fake_client = MagicMock()
        fake_client.embed.return_value = MagicMock(embeddings=[emb])
        fake_cohere_module = MagicMock()
        fake_cohere_module.Client.return_value = fake_client

        with patch.dict("sys.modules", {"cohere": fake_cohere_module}):
            from App.services import embedding_service
            import importlib

            importlib.reload(embedding_service)
            embedding_service.gerar_embedding_query("query teste")

        # Verifica que input_type foi 'search_query'
        call_kwargs = fake_client.embed.call_args
        assert call_kwargs is not None
        assert call_kwargs.kwargs.get("input_type") == "search_query"

    def test_gerar_embedding_query_openai_delega_para_gerar_embedding(
        self, monkeypatch
    ):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")

        emb = self._emb(1024)
        with patch("App.services.embedding_service.gerar_embedding") as mock_fn:
            mock_fn.return_value = emb
            from App.services.embedding_service import gerar_embedding_query

            resultado = gerar_embedding_query("query teste")

        mock_fn.assert_called_once_with("query teste")
        assert resultado == emb

    # ── Provider 'local' (sentence-transformers, default) ────────────────────

    def test_default_provider_e_local(self, monkeypatch):
        monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
        from App.services import embedding_service

        assert embedding_service._provider() == "local"

    def test_local_provider_retorna_none_sem_lib(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
        from App.services import embedding_service

        # Reseta cache do modelo
        embedding_service._LOCAL_MODEL = None
        with patch(
            "App.services.embedding_service._carregar_modelo_local", return_value=None
        ):
            assert embedding_service.gerar_embedding("texto") is None

    def test_local_provider_sucesso_com_mock(self, monkeypatch):
        import numpy as np

        monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
        from App.services import embedding_service

        fake_model = MagicMock()
        # Vetor normalizado fake de 384 dims
        fake_vec = np.array([0.05] * 384, dtype=np.float32)
        fake_model.encode.return_value = fake_vec

        embedding_service._LOCAL_MODEL = fake_model
        resultado = embedding_service.gerar_embedding("texto juridico")

        assert resultado is not None
        assert len(resultado) == 384
        assert all(isinstance(v, float) for v in resultado)
        # Verifica que pediu normalizacao
        fake_model.encode.assert_called_once()
        assert fake_model.encode.call_args.kwargs.get("normalize_embeddings") is True

    def test_local_provider_dim_incorreta_retorna_none(self, monkeypatch):
        import numpy as np

        monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
        from App.services import embedding_service

        fake_model = MagicMock()
        # Vetor com dim errada (256 em vez de 384)
        fake_model.encode.return_value = np.array([0.1] * 256, dtype=np.float32)

        embedding_service._LOCAL_MODEL = fake_model
        assert embedding_service.gerar_embedding("texto") is None

    def test_local_provider_query_e_documento_simetrico(self, monkeypatch):
        """Provider local nao distingue input_type — query e doc usam o mesmo modelo."""
        import numpy as np

        monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
        from App.services import embedding_service

        fake_vec = np.array([0.2] * 384, dtype=np.float32)
        fake_model = MagicMock()
        fake_model.encode.return_value = fake_vec
        embedding_service._LOCAL_MODEL = fake_model

        doc = embedding_service.gerar_embedding("documento longo")
        qry = embedding_service.gerar_embedding_query("query curta")

        assert doc == qry  # mesmo vetor mockado, simetria de provider


# ─────────────────────────────────────────────────────────────────────────────
# database: salvar_embedding / buscar_defesas_semanticas
# ─────────────────────────────────────────────────────────────────────────────


class TestDatabaseEmbedding:
    def _make_mock_conn(self, fetchall_result=None):
        """Monta mock de conexao psycopg2 com rowcount=1."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = fetchall_result or []
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        return mock_conn, mock_cur

    def test_salvar_embedding_chama_update(self):
        from App import database as db

        mock_conn, mock_cur = self._make_mock_conn()
        with (
            patch.object(db, "_get_connection") as mock_gc,
            patch.object(db, "_ensure_db_initialized"),
        ):
            mock_gc.return_value.__enter__ = lambda s: mock_conn
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            db.salvar_embedding(42, [0.5] * 384)

        sql, params = mock_cur.execute.call_args.args
        assert "UPDATE contestacoes" in sql
        assert "fatos_embedding" in sql
        assert params[1] == 42

    def test_buscar_defesas_semanticas_retorna_lista_vazia_sem_rows(self):
        from App import database as db

        mock_conn, mock_cur = self._make_mock_conn(fetchall_result=[])
        with (
            patch.object(db, "_get_connection") as mock_gc,
            patch.object(db, "_ensure_db_initialized"),
        ):
            mock_gc.return_value.__enter__ = lambda s: mock_conn
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            resultado = db.buscar_defesas_semanticas(
                embedding=[0.1] * 384,
                tipo_acao="Trabalhista",
                excluir_numero="0001",
                usuario_id="USR-TESTE",
                limit=5,
            )

        assert resultado == []

    def test_buscar_defesas_semanticas_mapeia_row(self):
        from datetime import datetime
        from App import database as db

        n8n_resp = {
            "minuta": {
                "tese_central": "Improcedencia",
                "resumo_estrategico": "Estrategia X",
            }
        }
        fake_row = (
            "0002",  # numero_processo
            "Trabalhista",  # tipo_acao
            "Fatos do caso",  # fatos
            "Horas extras",  # pedido_autor
            n8n_resp,  # n8n_resposta
            True,  # feedback_util
            datetime(2026, 1, 1),  # criado_em
            0.87,  # similarity
        )
        mock_conn, mock_cur = self._make_mock_conn(fetchall_result=[fake_row])

        with (
            patch.object(db, "_get_connection") as mock_gc,
            patch.object(db, "_ensure_db_initialized"),
        ):
            mock_gc.return_value.__enter__ = lambda s: mock_conn
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            resultado = db.buscar_defesas_semanticas(
                embedding=[0.1] * 384,
                tipo_acao="Trabalhista",
                excluir_numero="0001",
                usuario_id="USR-TESTE",
            )

        assert len(resultado) == 1
        item = resultado[0]
        assert item["numero_processo"] == "0002"
        assert item["tese_central"] == "Improcedencia"
        assert item["resumo_estrategico"] == "Estrategia X"
        assert item["similarity"] == pytest.approx(0.87)
        assert item["feedback_util"] is True


# ─────────────────────────────────────────────────────────────────────────────
# routes/rag
# ─────────────────────────────────────────────────────────────────────────────


class TestRagRoute:
    def _usuario_fake(self):
        return {"id": "u1", "nome": "Advogado", "email": "adv@ex.com"}

    def _payload(self, **kw):
        base = {
            "tipo_acao": "Trabalhista - Horas Extras",
            "numero_processo": "0001234-56.2026.5.06.0001",
            "fatos": "Reclamante trabalhou horas extras nao pagas.",
            "pedidos": ["Horas extras", "Adicional noturno"],
        }
        base.update(kw)
        return base

    @staticmethod
    def _run(coro):
        return asyncio.new_event_loop().run_until_complete(coro)

    def _req(self):
        from fastapi import Request

        return Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/api/rag/defesas-similares",
                "headers": [],
                "query_string": b"",
                "client": ("127.0.0.1", 0),
            }
        )

    def test_retorna_embedding_indisponivel_quando_embedding_none(self):
        from App.routes import rag as rag_route

        with patch("App.routes.rag.gerar_embedding_query", return_value=None):
            resp = self._run(
                rag_route.buscar_defesas_similares(
                    request=self._req(),
                    payload=self._payload(),
                    usuario=self._usuario_fake(),
                )
            )

        assert resp["status"] == "embedding_indisponivel"
        assert resp["casos"] == []

    def test_retorna_sem_texto_quando_fatos_e_pedidos_vazios(self):
        from App.routes import rag as rag_route

        resp = self._run(
            rag_route.buscar_defesas_similares(
                request=self._req(),
                payload=self._payload(fatos="", pedidos=[]),
                usuario=self._usuario_fake(),
            )
        )

        assert resp["status"] == "sem_texto"

    def test_retorna_sem_resultados_quando_db_vazio(self):
        from App.routes import rag as rag_route

        emb = [0.1] * 384
        with (
            patch("App.routes.rag.gerar_embedding_query", return_value=emb),
            patch("App.routes.rag.buscar_defesas_semanticas", return_value=[]),
        ):
            resp = self._run(
                rag_route.buscar_defesas_similares(
                    request=self._req(),
                    payload=self._payload(),
                    usuario=self._usuario_fake(),
                )
            )

        assert resp["status"] == "sem_resultados"
        assert resp["casos"] == []

    def test_retorna_top3_rerankeados(self):
        from App.routes import rag as rag_route

        emb = [0.1] * 384

        def _make_caso(n, sim, fb):
            return {
                "numero_processo": f"000{n}",
                "tipo_acao": "Trabalhista",
                "fatos": "fatos",
                "pedido_autor": "pedidos",
                "tese_central": f"tese{n}",
                "resumo_estrategico": "",
                "fundamentos_curtos": "",
                "riscos": [],
                "criado_em": "2026-01-01",
                "similarity": sim,
                "feedback_util": fb,
            }

        # 4 casos: o com feedback True + alta sim deve subir
        rows = [
            _make_caso(1, 0.90, None),
            _make_caso(2, 0.85, True),  # melhor score reranked: 0.6*0.85+0.4*1.0 = 0.91
            _make_caso(3, 0.70, False),
            _make_caso(4, 0.60, None),
        ]

        with (
            patch("App.routes.rag.gerar_embedding_query", return_value=emb),
            patch("App.routes.rag.buscar_defesas_semanticas", return_value=rows),
        ):
            resp = self._run(
                rag_route.buscar_defesas_similares(
                    request=self._req(),
                    payload=self._payload(),
                    usuario=self._usuario_fake(),
                )
            )

        assert resp["status"] == "sucesso"
        assert len(resp["casos"]) == 3
        # caso2 (0.91) > caso1 (0.74) > caso3 (0.42)
        assert resp["casos"][0]["numero_processo"] == "0002"

    def test_tipo_acao_obrigatorio(self):
        from fastapi import HTTPException
        from App.routes import rag as rag_route

        with pytest.raises(HTTPException) as exc_info:
            self._run(
                rag_route.buscar_defesas_similares(
                    request=self._req(),
                    payload={"tipo_acao": "", "fatos": "x", "pedidos": []},
                    usuario=self._usuario_fake(),
                )
            )

        assert exc_info.value.status_code == 422

    def test_erro_na_busca_retorna_status_erro(self):
        from App.routes import rag as rag_route

        emb = [0.1] * 384
        with (
            patch("App.routes.rag.gerar_embedding_query", return_value=emb),
            patch(
                "App.routes.rag.buscar_defesas_semanticas",
                side_effect=RuntimeError("pgvector down"),
            ),
        ):
            resp = self._run(
                rag_route.buscar_defesas_similares(
                    request=self._req(),
                    payload=self._payload(),
                    usuario=self._usuario_fake(),
                )
            )

        assert resp["status"] == "erro_busca"
        assert "pgvector" in resp["detalhe"]


# ─────────────────────────────────────────────────────────────────────────────
# contestacao_peticao: _disparar_embedding (fire-and-forget)
# ─────────────────────────────────────────────────────────────────────────────


class TestDispararEmbedding:
    def test_nao_lanca_excecao_com_texto_vazio(self):
        from App.routes.contestacao_peticao import _disparar_embedding

        # Nao deve levantar mesmo sem keys configuradas
        _disparar_embedding(99, "", "")

    def test_lanca_thread_com_texto_valido(self):
        from App.routes.contestacao_peticao import _disparar_embedding

        started = []

        def mock_start(self_thread):
            started.append(self_thread.name)

        with patch.object(threading.Thread, "start", mock_start):
            _disparar_embedding(42, "fatos teste", "pedidos teste")

        assert any("embedding-42" in name for name in started)

    def test_background_silencia_erro_de_api(self):
        from App.routes.contestacao_peticao import _salvar_embedding_background

        with patch(
            "App.services.embedding_service.gerar_embedding",
            side_effect=Exception("API down"),
        ):
            # Deve capturar a excecao e nao propagar
            _salvar_embedding_background(99, "texto")

    def test_background_nao_chama_salvar_quando_embedding_none(self):
        from App.routes.contestacao_peticao import _salvar_embedding_background

        with (
            patch("App.services.embedding_service.gerar_embedding", return_value=None),
            patch("App.routes.contestacao_peticao.salvar_embedding") as mock_salvar,
        ):
            _salvar_embedding_background(99, "texto")

        mock_salvar.assert_not_called()

    def test_background_chama_salvar_quando_embedding_ok(self):
        from App.routes.contestacao_peticao import _salvar_embedding_background

        emb = [0.1] * 384
        with (
            patch("App.services.embedding_service.gerar_embedding", return_value=emb),
            patch("App.routes.contestacao_peticao.salvar_embedding") as mock_salvar,
        ):
            _salvar_embedding_background(42, "texto")

        mock_salvar.assert_called_once_with(42, emb)

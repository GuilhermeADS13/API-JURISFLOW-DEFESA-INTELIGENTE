"""Quest 2 — Testa rate limiting nos endpoints que antes nao tinham protecao."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from App.security import get_authenticated_user
from main import app

client = TestClient(app, raise_server_exceptions=False)

AUTH_USER = {"id": "u1", "nome": "Teste", "email": "t@t.com", "token": "tok"}
PROCESSO_VALIDO = {
    "numero_processo": "0001234-56.2026.8.00.0000",
    "autor": "Joao",
    "tipo_acao": "Reclamacao trabalhista",
    "fatos": "Fatos do caso",
    "pedido_autor": "Pagamento de verbas",
}


@pytest.fixture
def auth_override():
    """Override da dependencia de auth via FastAPI dependency_overrides."""
    app.dependency_overrides[get_authenticated_user] = lambda: AUTH_USER
    yield
    app.dependency_overrides.clear()


# ── /gerar-contestacao: default 10/minute (configuravel via RATE_LIMIT_CONTESTACAO) ──


def test_gerar_contestacao_rate_limit(auth_override):
    """PR8 P2.1 — default mudou para 10/minute via env RATE_LIMIT_CONTESTACAO."""
    with (
        patch(
            "App.routes.contestacao.enviar_para_n8n",
            new_callable=AsyncMock,
            return_value={"status": "processando"},
        ),
        patch("App.routes.contestacao.save_contestacao", return_value=1),
    ):
        # Primeiras 10 devem passar (default novo)
        for i in range(10):
            r = client.post("/api/gerar-contestacao", json=PROCESSO_VALIDO)
            assert r.status_code != 429, (
                f"Rate limit prematuro na chamada {i + 1}: {r.status_code}"
            )

        # 11a deve retornar 429
        r = client.post("/api/gerar-contestacao", json=PROCESSO_VALIDO)
        assert r.status_code == 429


# ── /contestacoes/resumo: default 30/minute (configuravel via RATE_LIMIT_DASHBOARD) ──


def test_resumo_rate_limit(auth_override):
    """PR8 P2.1 — default mudou para 30/minute via env RATE_LIMIT_DASHBOARD."""
    with (
        patch(
            "App.routes.contestacao.get_dashboard_cards_por_usuario", return_value=[]
        ),
        patch("App.routes.contestacao.list_contestacoes_por_usuario", return_value=[]),
    ):
        for i in range(30):
            r = client.get("/api/contestacoes/resumo")
            assert r.status_code != 429, f"Rate limit prematuro na chamada {i + 1}"

        r = client.get("/api/contestacoes/resumo")
        assert r.status_code == 429


# ── /suporte/contato: 5/minute ──────────────────────────────────────────────

CONTATO_VALIDO = {
    "nome": "Maria Silva",
    "email": "maria@email.com",
    "categoria": "Problema tecnico",
    "assunto": "Nao consigo gerar contestacao",
    "mensagem": "Estou tentando gerar uma contestacao mas o sistema retorna erro.",
}


def test_suporte_rate_limit():
    with patch("App.routes.suporte.enviar_reclamacao_por_email", return_value=None):
        for _ in range(5):
            r = client.post("/api/suporte/contato", json=CONTATO_VALIDO)
            assert r.status_code != 429

        r = client.post("/api/suporte/contato", json=CONTATO_VALIDO)
        assert r.status_code == 429

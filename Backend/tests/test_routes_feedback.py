"""Testes para POST /api/contestacoes/{id}/feedback e endpoints admin de exemplares."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

USUARIO_MOCK = {"id": "user-123", "nome": "Advogado Teste", "email": "adv@escritorio.com", "auth_provider": "legacy"}
ADMIN_MOCK   = {"id": "admin-1",  "nome": "Admin",          "email": "admin@jurisflow.com", "auth_provider": "legacy"}


# ---------- feedback ----------

def test_feedback_util_verdadeiro():
    """Happy path: advogado avalia minuta como util."""
    with patch("App.routes.feedback.salvar_feedback", return_value=True) as mock_save, \
         patch("App.security.get_authenticated_user", return_value=USUARIO_MOCK):
        resp = client.post(
            "/api/contestacoes/42/feedback",
            json={"util": True, "comentario": "Excelente estrutura de tese."},
            cookies={"session": "token-valido"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["contestacao_id"] == 42
    assert data["util"] is True
    mock_save.assert_called_once_with(
        contestacao_id=42,
        usuario_id="user-123",
        util=True,
        comentario="Excelente estrutura de tese.",
    )


def test_feedback_nao_util():
    """Feedback negativo tambem deve ser aceito."""
    with patch("App.routes.feedback.salvar_feedback", return_value=True), \
         patch("App.security.get_authenticated_user", return_value=USUARIO_MOCK):
        resp = client.post(
            "/api/contestacoes/7/feedback",
            json={"util": False},
            cookies={"session": "token-valido"},
        )
    assert resp.status_code == 200
    assert resp.json()["util"] is False


def test_feedback_contestacao_nao_encontrada():
    """404 quando contestacao nao pertence ao usuario ou nao existe."""
    with patch("App.routes.feedback.salvar_feedback", return_value=False), \
         patch("App.security.get_authenticated_user", return_value=USUARIO_MOCK):
        resp = client.post(
            "/api/contestacoes/999/feedback",
            json={"util": True},
            cookies={"session": "token-valido"},
        )
    assert resp.status_code == 404


def test_feedback_sem_autenticacao():
    """401 quando nao ha cookie de sessao valido."""
    resp = client.post("/api/contestacoes/1/feedback", json={"util": True})
    assert resp.status_code in (401, 403)


def test_feedback_comentario_muito_longo():
    """422 quando comentario excede 2000 caracteres."""
    with patch("App.security.get_authenticated_user", return_value=USUARIO_MOCK):
        resp = client.post(
            "/api/contestacoes/1/feedback",
            json={"util": True, "comentario": "x" * 2001},
            cookies={"session": "token-valido"},
        )
    assert resp.status_code == 422


def test_feedback_id_invalido():
    """422 para contestacao_id <= 0."""
    with patch("App.security.get_authenticated_user", return_value=USUARIO_MOCK):
        resp = client.post(
            "/api/contestacoes/0/feedback",
            json={"util": True},
            cookies={"session": "token-valido"},
        )
    assert resp.status_code in (404, 422)


# ---------- admin exemplares ----------

def test_criar_exemplar_admin():
    """Admin pode criar exemplar via POST /api/admin/exemplares."""
    import os
    with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}), \
         patch("App.routes.feedback.salvar_exemplar", return_value=1), \
         patch("App.security.get_authenticated_user", return_value=ADMIN_MOCK):
        resp = client.post(
            "/api/admin/exemplares",
            json={
                "tipo_acao": "Direito do Consumidor",
                "tese_central": "Ausencia de vicio do produto e inexistencia de dano moral.",
                "fundamentos_resumo": "Art. 14 CDC. Laudo tecnico comprova ausencia de defeito.",
                "nota_qualidade": 9,
            },
            cookies={"session": "token-admin"},
        )
    assert resp.status_code == 201
    assert resp.json()["status"] == "criado"


def test_criar_exemplar_nao_admin():
    """403 quando usuario nao e admin."""
    import os
    with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}), \
         patch("App.security.get_authenticated_user", return_value=USUARIO_MOCK):
        resp = client.post(
            "/api/admin/exemplares",
            json={
                "tipo_acao": "Direito do Consumidor",
                "tese_central": "Tese qualquer.",
                "fundamentos_resumo": "Fundamentos quaisquer aqui para preencher minimo.",
            },
            cookies={"session": "token-normal"},
        )
    assert resp.status_code == 403


def test_listar_exemplares_admin():
    """Admin pode listar exemplares por tipo_acao."""
    import os
    exemplares_mock = [
        {
            "tipo_acao": "Direito do Consumidor",
            "tese_central": "Ausencia de defeito.",
            "fundamentos_resumo": "Art. 14 CDC.",
            "nota_qualidade": 9,
        }
    ]
    with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}), \
         patch("App.routes.feedback.get_contestacoes_exemplares", return_value=exemplares_mock), \
         patch("App.security.get_authenticated_user", return_value=ADMIN_MOCK):
        resp = client.get(
            "/api/admin/exemplares?tipo_acao=Direito do Consumidor",
            cookies={"session": "token-admin"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["exemplares"][0]["nota_qualidade"] == 9

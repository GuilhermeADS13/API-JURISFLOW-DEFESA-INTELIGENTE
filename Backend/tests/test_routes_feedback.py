"""Testes para POST /api/contestacoes/{id}/feedback e endpoints admin de exemplares."""
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from App.security import get_authenticated_user
from main import app

client = TestClient(app)

USUARIO_MOCK = {"id": "user-123", "nome": "Advogado Teste", "email": "adv@escritorio.com", "auth_provider": "legacy"}
ADMIN_MOCK   = {"id": "admin-1",  "nome": "Admin",          "email": "admin@jurisflow.com", "auth_provider": "legacy"}


@pytest.fixture
def auth_como_usuario():
    """Substitui a dependencia de auth pelo usuario comum.

    Usa app.dependency_overrides — `patch` em cima do simbolo nao funciona
    porque o FastAPI captura a referencia de get_authenticated_user no
    momento do include_router.
    """
    app.dependency_overrides[get_authenticated_user] = lambda: USUARIO_MOCK
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth_como_admin():
    app.dependency_overrides[get_authenticated_user] = lambda: ADMIN_MOCK
    yield
    app.dependency_overrides.clear()


# ---------- feedback ----------

def test_feedback_util_verdadeiro(auth_como_usuario):
    """Happy path: advogado avalia minuta como util."""
    with patch("App.routes.feedback.salvar_feedback", return_value=True) as mock_save:
        resp = client.post(
            "/api/contestacoes/42/feedback",
            json={"util": True, "comentario": "Excelente estrutura de tese."},
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


def test_feedback_nao_util(auth_como_usuario):
    """Feedback negativo tambem deve ser aceito."""
    with patch("App.routes.feedback.salvar_feedback", return_value=True):
        resp = client.post(
            "/api/contestacoes/7/feedback",
            json={"util": False},
        )
    assert resp.status_code == 200
    assert resp.json()["util"] is False


def test_feedback_contestacao_nao_encontrada(auth_como_usuario):
    """404 quando contestacao nao pertence ao usuario ou nao existe."""
    with patch("App.routes.feedback.salvar_feedback", return_value=False):
        resp = client.post(
            "/api/contestacoes/999/feedback",
            json={"util": True},
        )
    assert resp.status_code == 404


def test_feedback_sem_autenticacao():
    """401 quando nao ha cookie de sessao valido."""
    # Nao usa fixture de auth — dependency real bloqueia.
    resp = client.post("/api/contestacoes/1/feedback", json={"util": True})
    assert resp.status_code in (401, 403)


def test_feedback_comentario_muito_longo(auth_como_usuario):
    """422 quando comentario excede 2000 caracteres."""
    resp = client.post(
        "/api/contestacoes/1/feedback",
        json={"util": True, "comentario": "x" * 2001},
    )
    assert resp.status_code == 422


def test_feedback_id_invalido(auth_como_usuario):
    """422 para contestacao_id <= 0 (validado pelo Path(ge=1))."""
    resp = client.post(
        "/api/contestacoes/0/feedback",
        json={"util": True},
    )
    assert resp.status_code in (404, 422)


# ---------- admin exemplares ----------

def test_criar_exemplar_admin(auth_como_admin):
    """Admin pode criar exemplar via POST /api/admin/exemplares."""
    with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}), \
         patch("App.routes.feedback.salvar_exemplar", return_value=1):
        resp = client.post(
            "/api/admin/exemplares",
            json={
                "tipo_acao": "Direito do Consumidor",
                "tese_central": "Ausencia de vicio do produto e inexistencia de dano moral.",
                "fundamentos_resumo": "Art. 14 CDC. Laudo tecnico comprova ausencia de defeito.",
                "nota_qualidade": 9,
            },
        )
    assert resp.status_code == 201
    assert resp.json()["status"] == "criado"


def test_criar_exemplar_nao_admin(auth_como_usuario):
    """403 quando usuario nao e admin."""
    with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}):
        resp = client.post(
            "/api/admin/exemplares",
            json={
                "tipo_acao": "Direito do Consumidor",
                "tese_central": "Tese qualquer.",
                "fundamentos_resumo": "Fundamentos quaisquer aqui para preencher minimo.",
            },
        )
    assert resp.status_code == 403


def test_listar_exemplares_admin(auth_como_admin):
    """Admin pode listar exemplares por tipo_acao."""
    exemplares_mock = [
        {
            "tipo_acao": "Direito do Consumidor",
            "tese_central": "Ausencia de defeito.",
            "fundamentos_resumo": "Art. 14 CDC.",
            "nota_qualidade": 9,
        }
    ]
    with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}), \
         patch("App.routes.feedback.get_contestacoes_exemplares", return_value=exemplares_mock):
        resp = client.get("/api/admin/exemplares?tipo_acao=Direito do Consumidor")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["exemplares"][0]["nota_qualidade"] == 9

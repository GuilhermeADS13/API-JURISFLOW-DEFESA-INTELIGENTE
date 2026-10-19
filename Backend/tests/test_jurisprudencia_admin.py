"""Testes da rota POST /api/admin/jurisprudencia/criar (PR22)."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from App.security import get_authenticated_user
from main import app

client = TestClient(app)


USUARIO_COMUM = {
    "id": "user-123",
    "nome": "Advogado",
    "email": "adv@escritorio.com",
    "auth_provider": "legacy",
}
USUARIO_ADMIN = {
    "id": "admin-1",
    "nome": "Admin",
    "email": "admin@jurisflow.com",
    "auth_provider": "legacy",
}


@pytest.fixture
def auth_como_usuario():
    app.dependency_overrides[get_authenticated_user] = lambda: USUARIO_COMUM
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth_como_admin():
    app.dependency_overrides[get_authenticated_user] = lambda: USUARIO_ADMIN
    yield
    app.dependency_overrides.clear()


def _payload_minimo(**overrides) -> dict:
    base = {
        "tribunal": "TST",
        "numero_processo": "Sumula TESTE-001",
        "ementa": "Ementa de teste com mais de 20 caracteres pra passar pelo min_length.",
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────


def test_sem_autenticacao_bloqueia():
    """Sem token, dependency real rejeita."""
    resp = client.post("/api/admin/jurisprudencia/criar", json=_payload_minimo())
    assert resp.status_code in (401, 403)


def test_usuario_nao_admin_recebe_403(auth_como_usuario):
    """Usuario logado mas fora de ADMIN_EMAILS deve receber 403."""
    with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}):
        resp = client.post("/api/admin/jurisprudencia/criar", json=_payload_minimo())
    assert resp.status_code == 403
    assert "administradores" in resp.json()["detail"].lower()


def test_admin_consegue_criar(auth_como_admin):
    """Admin com email correto + payload valido → 201 + chama upsert."""
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch(
            "App.routes.jurisprudencia_admin.gerar_embedding",
            return_value=[0.0] * 384,
        ),
        patch("App.database.upsert_jurisprudencia") as mock_upsert,
    ):
        resp = client.post(
            "/api/admin/jurisprudencia/criar",
            json=_payload_minimo(
                relator="Min. Teste",
                data_julgamento="2020-05-10",
                peso_relevancia=8,
                area_juridica="trabalhista",
            ),
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "ok"
    assert data["tribunal"] == "TST"
    assert data["embedding_gerado"] is True
    mock_upsert.assert_called_once()
    kwargs = mock_upsert.call_args.kwargs
    assert kwargs["peso_relevancia"] == 8
    assert kwargs["data_julgamento"] == "2020-05-10"


# ─────────────────────────────────────────────────────────────────────────────
# Validacao Pydantic
# ─────────────────────────────────────────────────────────────────────────────


def test_ementa_vazia_retorna_422(auth_como_admin):
    """Ementa abaixo do min_length=20 deve falhar com 422."""
    with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}):
        resp = client.post(
            "/api/admin/jurisprudencia/criar",
            json=_payload_minimo(ementa="curto"),
        )
    assert resp.status_code == 422


def test_peso_relevancia_fora_do_range_retorna_422(auth_como_admin):
    """Pydantic rejeita peso=15 (max=10)."""
    with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}):
        resp = client.post(
            "/api/admin/jurisprudencia/criar",
            json=_payload_minimo(peso_relevancia=15),
        )
    assert resp.status_code == 422


def test_data_julgamento_formato_invalido_retorna_422(auth_como_admin):
    """data_julgamento '10/05/2020' (BR format) deve falhar; aceitamos so ISO."""
    with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}):
        resp = client.post(
            "/api/admin/jurisprudencia/criar",
            json=_payload_minimo(data_julgamento="10/05/2020"),
        )
    assert resp.status_code == 422


def test_data_julgamento_dia_inexistente_retorna_422(auth_como_admin):
    """'2023-02-30' tem formato ISO mas e data invalida."""
    with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}):
        resp = client.post(
            "/api/admin/jurisprudencia/criar",
            json=_payload_minimo(data_julgamento="2023-02-30"),
        )
    assert resp.status_code == 422


def test_data_julgamento_vazia_aceita_como_none(auth_como_admin):
    """String vazia em data_julgamento vira None sem 422."""
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch(
            "App.routes.jurisprudencia_admin.gerar_embedding",
            return_value=[0.0] * 384,
        ),
        patch("App.database.upsert_jurisprudencia") as mock_upsert,
    ):
        resp = client.post(
            "/api/admin/jurisprudencia/criar",
            json=_payload_minimo(data_julgamento=""),
        )
    assert resp.status_code == 201
    assert mock_upsert.call_args.kwargs["data_julgamento"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Robustez
# ─────────────────────────────────────────────────────────────────────────────


def test_embedding_indisponivel_nao_bloqueia_upsert(auth_como_admin):
    """Sentence-transformers retorna None: ainda assim upserta + log warning."""
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch(
            "App.routes.jurisprudencia_admin.gerar_embedding",
            return_value=None,
        ),
        patch("App.database.upsert_jurisprudencia") as mock_upsert,
    ):
        resp = client.post("/api/admin/jurisprudencia/criar", json=_payload_minimo())
    assert resp.status_code == 201
    assert resp.json()["embedding_gerado"] is False
    mock_upsert.assert_called_once()
    assert mock_upsert.call_args.kwargs["embedding"] is None


def test_upsert_falha_db_retorna_500(auth_como_admin):
    """psycopg2.Error virou HTTPException 500 (nao vaza stacktrace)."""
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch(
            "App.routes.jurisprudencia_admin.gerar_embedding",
            return_value=[0.0] * 384,
        ),
        patch(
            "App.database.upsert_jurisprudencia",
            side_effect=Exception("connection refused"),
        ),
    ):
        resp = client.post("/api/admin/jurisprudencia/criar", json=_payload_minimo())
    assert resp.status_code == 500
    assert "logs" in resp.json()["detail"].lower()


def test_re_submissao_mesmo_acordao_continua_201(auth_como_admin):
    """Idempotencia: chamar 2x com mesmo (tribunal, numero) retorna 201 ambas vezes
    (UPSERT da tabela faz match e atualiza, sem duplicar)."""
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch(
            "App.routes.jurisprudencia_admin.gerar_embedding",
            return_value=[0.0] * 384,
        ),
        patch("App.database.upsert_jurisprudencia") as mock_upsert,
    ):
        resp1 = client.post("/api/admin/jurisprudencia/criar", json=_payload_minimo())
        resp2 = client.post(
            "/api/admin/jurisprudencia/criar",
            json=_payload_minimo(
                ementa="Ementa atualizada com mais detalhes do paradigma."
            ),
        )
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert mock_upsert.call_count == 2


def _resposta_listar(items, total=None):
    """Helper: shape de retorno do listar_jurisprudencia."""
    return {
        "items": items,
        "total": total if total is not None else len(items),
        "limit": 25,
        "offset": 0,
        "has_more": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PR23 — GET listar / GET id / PATCH / DELETE
# ─────────────────────────────────────────────────────────────────────────────


def test_listar_sem_auth_bloqueia():
    resp = client.get("/api/admin/jurisprudencia/listar")
    assert resp.status_code in (401, 403)


def test_listar_nao_admin_403(auth_como_usuario):
    with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}):
        resp = client.get("/api/admin/jurisprudencia/listar")
    assert resp.status_code == 403


def test_listar_admin_retorna_payload_paginado(auth_como_admin):
    fake_items = [
        {
            "id": 1,
            "tribunal": "TST",
            "numero_processo": "Sumula 437",
            "ementa": "x" * 100,
            "peso_relevancia": 10,
        },
        {
            "id": 2,
            "tribunal": "STF",
            "numero_processo": "ADPF 324",
            "ementa": "y" * 100,
            "peso_relevancia": 10,
        },
    ]
    fake_resp = {
        "items": fake_items,
        "total": 2,
        "limit": 25,
        "offset": 0,
        "has_more": False,
    }
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch("App.database.listar_jurisprudencia", return_value=fake_resp),
    ):
        resp = client.get("/api/admin/jurisprudencia/listar?limit=25&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["has_more"] is False


def test_listar_propaga_filtros(auth_como_admin):
    captured = {}

    def fake_listar(**kw):
        captured.update(kw)
        return _resposta_listar([])

    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch("App.database.listar_jurisprudencia", side_effect=fake_listar),
    ):
        resp = client.get(
            "/api/admin/jurisprudencia/listar"
            "?tribunal=TST&area_juridica=trabalhista&busca=intervalo&limit=10&offset=20"
        )
    assert resp.status_code == 200
    assert captured["tribunal"] == "TST"
    assert captured["area_juridica"] == "trabalhista"
    assert captured["busca"] == "intervalo"
    assert captured["limit"] == 10
    assert captured["offset"] == 20


def test_obter_404_quando_inexistente(auth_como_admin):
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch("App.database.obter_jurisprudencia", return_value=None),
    ):
        resp = client.get("/api/admin/jurisprudencia/9999")
    assert resp.status_code == 404


def test_obter_200_quando_existe(auth_como_admin):
    item = {
        "id": 42,
        "tribunal": "TST",
        "numero_processo": "Sumula 437",
        "ementa": "x" * 100,
        "peso_relevancia": 10,
    }
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch("App.database.obter_jurisprudencia", return_value=item),
    ):
        resp = client.get("/api/admin/jurisprudencia/42")
    assert resp.status_code == 200
    assert resp.json()["id"] == 42


def test_patch_404_quando_inexistente(auth_como_admin):
    # PR31: a rota PATCH (desde PR27) NAO chama mais obter_jurisprudencia;
    # confia no atualizar_jurisprudencia retornar False (UPDATE ... RETURNING).
    # Mock correto: atualizar retorna False + embedding mockado (nao carrega modelo).
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch(
            "App.routes.jurisprudencia_admin.gerar_embedding",
            return_value=[0.1] * 384,
        ),
        patch("App.database.atualizar_jurisprudencia", return_value=False),
    ):
        resp = client.patch(
            "/api/admin/jurisprudencia/9999",
            json=_payload_minimo(),
        )
    assert resp.status_code == 404


def test_patch_200_atualiza_existente(auth_como_admin):
    existente = {
        "id": 42,
        "tribunal": "TST",
        "numero_processo": "X",
        "ementa": "y" * 100,
        "peso_relevancia": 5,
    }
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch("App.database.obter_jurisprudencia", return_value=existente),
        patch(
            "App.routes.jurisprudencia_admin.gerar_embedding",
            return_value=[0.1] * 384,
        ),
        patch("App.database.atualizar_jurisprudencia", return_value=True) as upd,
    ):
        resp = client.patch(
            "/api/admin/jurisprudencia/42",
            json=_payload_minimo(peso_relevancia=8),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 42
    assert data["embedding_gerado"] is True
    upd.assert_called_once()
    kwargs = upd.call_args.kwargs
    assert kwargs["campos"]["peso_relevancia"] == 8


def test_patch_payload_invalido_422(auth_como_admin):
    with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}):
        resp = client.patch(
            "/api/admin/jurisprudencia/42",
            json={"tribunal": "TST"},
        )
    assert resp.status_code == 422


def test_delete_404_quando_inexistente(auth_como_admin):
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch("App.database.deletar_jurisprudencia", return_value=False),
    ):
        resp = client.delete("/api/admin/jurisprudencia/9999")
    assert resp.status_code == 404


def test_texto_integral_opcional_no_criar(auth_como_admin):
    """PR24: payload SEM texto_integral segue funcionando (default None)."""
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch(
            "App.routes.jurisprudencia_admin.gerar_embedding", return_value=[0.0] * 384
        ),
        patch("App.database.upsert_jurisprudencia") as mock_upsert,
    ):
        resp = client.post(
            "/api/admin/jurisprudencia/criar",
            json=_payload_minimo(),  # sem texto_integral
        )
    assert resp.status_code == 201
    kwargs = mock_upsert.call_args.kwargs
    assert kwargs["texto_integral"] is None


def test_texto_integral_5kb_aceito(auth_como_admin):
    """PR24: texto de 5 KB passa validacao e chega ao upsert intacto."""
    texto = "conteudo do acordao " * 300  # ~6 KB
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch(
            "App.routes.jurisprudencia_admin.gerar_embedding", return_value=[0.0] * 384
        ),
        patch("App.database.upsert_jurisprudencia") as mock_upsert,
    ):
        resp = client.post(
            "/api/admin/jurisprudencia/criar",
            json=_payload_minimo(texto_integral=texto),
        )
    assert resp.status_code == 201
    kwargs = mock_upsert.call_args.kwargs
    assert kwargs["texto_integral"] == texto.strip()


def test_texto_integral_acima_do_limite_retorna_422(auth_como_admin):
    """PR24: 200_001 chars estoura Field(max_length=200000) e retorna 422."""
    with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}):
        resp = client.post(
            "/api/admin/jurisprudencia/criar",
            json=_payload_minimo(texto_integral="x" * 200_001),
        )
    assert resp.status_code == 422


def test_patch_atualiza_texto_integral(auth_como_admin):
    """PATCH aceita texto_integral e propaga pra atualizar_jurisprudencia."""
    existente = {
        "id": 42,
        "tribunal": "TST",
        "numero_processo": "X",
        "ementa": "y" * 100,
        "peso_relevancia": 5,
    }
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch("App.database.obter_jurisprudencia", return_value=existente),
        patch(
            "App.routes.jurisprudencia_admin.gerar_embedding", return_value=[0.1] * 384
        ),
        patch("App.database.atualizar_jurisprudencia", return_value=True) as upd,
    ):
        resp = client.patch(
            "/api/admin/jurisprudencia/42",
            json=_payload_minimo(texto_integral="Novo texto integral do acordao."),
        )
    assert resp.status_code == 200
    assert (
        upd.call_args.kwargs["campos"]["texto_integral"]
        == "Novo texto integral do acordao."
    )


def test_delete_200_quando_existia(auth_como_admin):
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch("App.database.deletar_jurisprudencia", return_value=True),
    ):
        resp = client.delete("/api/admin/jurisprudencia/42")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 42


# ─────────────────────────────────────────────────────────────────────────────
# PR34 — POST /admin/jurisprudencia/scrape (ingestao em lote agendada)
# ─────────────────────────────────────────────────────────────────────────────


def test_scrape_sem_auth_bloqueia():
    """Sem token, a dependency real rejeita (nao dispara ingestao)."""
    resp = client.post("/api/admin/jurisprudencia/scrape", json={"fonte": "tst"})
    assert resp.status_code in (401, 403)


def test_scrape_admin_202_agenda_background(auth_como_admin):
    """Admin -> 202 imediato e agenda o background com os parametros certos.

    O background e mockado: o teste NAO roda scraper/embedding/DB reais.
    """
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch("App.routes.jurisprudencia_admin._rodar_scrape_background") as mock_bg,
    ):
        resp = client.post(
            "/api/admin/jurisprudencia/scrape",
            json={"fonte": "todas", "max_por_tema": 3},
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["fonte"] == "todas"
    assert data["max_por_tema"] == 3
    # TestClient executa o background apos a resposta -> mock chamado 1x
    mock_bg.assert_called_once_with("todas", 3)


def test_scrape_fonte_invalida_422(auth_como_admin):
    """Fonte fora de {tst, carf, todas} -> 422 antes de agendar nada."""
    with (
        patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}),
        patch("App.routes.jurisprudencia_admin._rodar_scrape_background") as mock_bg,
    ):
        resp = client.post(
            "/api/admin/jurisprudencia/scrape", json={"fonte": "supremo"}
        )
    assert resp.status_code == 422
    assert "fonte" in resp.json()["detail"].lower()
    mock_bg.assert_not_called()


def test_scrape_max_por_tema_fora_da_faixa_422(auth_como_admin):
    """max_por_tema > 20 barra na validacao Pydantic (le=20)."""
    with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@jurisflow.com"}):
        resp = client.post(
            "/api/admin/jurisprudencia/scrape",
            json={"fonte": "tst", "max_por_tema": 999},
        )
    assert resp.status_code == 422

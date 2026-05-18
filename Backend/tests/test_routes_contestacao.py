"""Testes unitarios da rota de contestacao."""

import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from App.models.processo import Processo
from App.routes import contestacao
from App.services.n8n_service import N8NServiceError


def _fake_request(
    method: str = "POST", path: str = "/api/gerar-contestacao"
) -> Request:
    """Request minimo para satisfazer o decorator @limiter.limit do slowapi."""
    return Request(
        scope={
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 0),
        }
    )


@pytest.fixture()
def processo_valido() -> Processo:
    return Processo(
        numero_processo="0001234-56.2026.8.00.0000",
        autor="Autor Teste",
        reu="Reu Teste",
        tipo_acao="Direito Civil",
        fatos="Fatos relevantes",
        pedido_autor="Pedido principal",
        texto_editado_ao_vivo="Minuta inicial",
    )


def test_gerar_contestacao_fluxo_feliz(monkeypatch, processo_valido):
    calls: dict = {}

    async def fake_enviar_para_n8n(payload):
        calls["payload_n8n"] = payload.copy()
        return {"workflow_id": "wf-123"}

    def fake_save_contestacao(payload, status, n8n_resposta):
        calls["save"] = {
            "payload": payload.copy(),
            "status": status,
            "n8n_resposta": n8n_resposta,
        }
        return 77

    monkeypatch.setattr(contestacao, "enviar_para_n8n", fake_enviar_para_n8n)
    monkeypatch.setattr(contestacao, "save_contestacao", fake_save_contestacao)

    response = asyncio.run(
        contestacao.gerar_contestacao(
            request=_fake_request(),
            processo=processo_valido,
            usuario={"id": "USR-ABC", "nome": "Ana", "email": "ana@teste.com"},
        )
    )

    assert response["status"] == "processando"
    assert response["id_registro"] == 77
    assert response["id_caso"].startswith("CTR-")
    assert response["workflow"] == {"workflow_id": "wf-123"}
    assert calls["payload_n8n"]["usuario_id"] == "USR-ABC"
    assert calls["payload_n8n"]["usuario_nome"] == "Ana"
    assert calls["payload_n8n"]["usuario_email"] == "ana@teste.com"
    assert calls["payload_n8n"]["auth_provider"] == "legacy"
    assert calls["save"]["status"] == "processando"


def test_gerar_contestacao_trata_erro_n8n(monkeypatch, processo_valido):
    calls: dict = {}

    async def fake_enviar_para_n8n(payload):
        raise N8NServiceError("workflow indisponivel")

    def fake_save_contestacao(payload, status, n8n_resposta):
        calls["save"] = {
            "status": status,
            "n8n_resposta": n8n_resposta,
        }
        return 12

    monkeypatch.setattr(contestacao, "enviar_para_n8n", fake_enviar_para_n8n)
    monkeypatch.setattr(contestacao, "save_contestacao", fake_save_contestacao)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            contestacao.gerar_contestacao(
                request=_fake_request(),
                processo=processo_valido,
                usuario={"id": "USR-ERR", "nome": "Ana", "email": "ana@teste.com"},
            )
        )

    assert exc_info.value.status_code == 502
    assert "workflow indisponivel" in str(exc_info.value.detail)
    assert calls["save"]["status"] == "erro"
    assert "workflow indisponivel" in calls["save"]["n8n_resposta"]["mensagem"]


def test_gerar_contestacao_retorna_422_em_erro_validacao(monkeypatch, processo_valido):
    calls: dict = {}

    async def fake_enviar_para_n8n(payload):
        return {
            "status": "erro_validacao",
            "mensagem": "Numero de processo invalido no workflow.",
            "erros": ["numero_processo"],
        }

    def fake_save_contestacao(payload, status, n8n_resposta):
        calls["save"] = {
            "status": status,
            "n8n_resposta": n8n_resposta,
        }
        return 45

    monkeypatch.setattr(contestacao, "enviar_para_n8n", fake_enviar_para_n8n)
    monkeypatch.setattr(contestacao, "save_contestacao", fake_save_contestacao)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            contestacao.gerar_contestacao(
                request=_fake_request(),
                processo=processo_valido,
                usuario={"id": "USR-VAL", "nome": "Ana", "email": "ana@teste.com"},
            )
        )

    assert exc_info.value.status_code == 422
    # Mensagem do n8n NAO deve vazar para o cliente — usuario recebe texto generico,
    # detalhes ficam no log estruturado e na coluna n8n_resposta da tabela contestacoes.
    detail = str(exc_info.value.detail).lower()
    assert "invalido" not in detail
    assert "revise" in detail
    assert calls["save"]["status"] == "erro_validacao"
    # Mensagem original do n8n permanece persistida para auditoria.
    assert (
        calls["save"]["n8n_resposta"]["mensagem"]
        == "Numero de processo invalido no workflow."
    )


def test_obter_resumo_contestacoes_retorna_cards_e_historico(monkeypatch):
    calls: dict = {}

    def fake_get_dashboard_cards_por_usuario(usuario_id):
        calls["cards_usuario_id"] = usuario_id
        return [{"label": "Total de casos", "value": "3"}]

    def fake_list_contestacoes_por_usuario(usuario_id, limit):
        calls["history_usuario_id"] = usuario_id
        calls["history_limit"] = limit
        return [
            {
                "id": "CTR-2026-000001",
                "naturezaCaso": "Direito Civil",
                "tipo": "Defesa editada",
                "data": "24/03/2026",
                "status": "Concluida",
                "numeroProcesso": "0001234-56.2026.8.00.0000",
            }
        ]

    monkeypatch.setattr(
        contestacao,
        "get_dashboard_cards_por_usuario",
        fake_get_dashboard_cards_por_usuario,
    )
    monkeypatch.setattr(
        contestacao, "list_contestacoes_por_usuario", fake_list_contestacoes_por_usuario
    )

    response = asyncio.run(
        contestacao.obter_resumo_contestacoes(
            request=_fake_request("GET", "/api/contestacoes/resumo"),
            limit=50,
            usuario={"id": "USR-DASH", "nome": "Ana", "email": "ana@teste.com"},
        )
    )

    assert response["cards"][0]["label"] == "Total de casos"
    assert response["history"][0]["id"] == "CTR-2026-000001"
    assert calls["cards_usuario_id"] == "USR-DASH"
    assert calls["history_usuario_id"] == "USR-DASH"
    assert calls["history_limit"] == 50


# ── PR8 P3.3 — GET /api/contestacoes/{id} ────────────────────────────────────


def test_obter_contestacao_retorna_registro_do_proprio_usuario(monkeypatch):
    """Usuario A consulta sua propria contestacao -> 200 OK com dados."""

    def fake_get_contestacao(contestacao_id, usuario_id):
        assert contestacao_id == 42
        assert usuario_id == "USR-A"
        return {
            "id": 42,
            "usuario_id": "USR-A",
            "numero_processo": "0001234-56.2026.8.00.0000",
            "autor": "Maria",
            "reu": "Empresa X",
            "tipo_acao": "Trabalhista",
            "status": "ok",
        }

    monkeypatch.setattr(contestacao, "get_contestacao", fake_get_contestacao)

    response = asyncio.run(
        contestacao.obter_contestacao(
            request=_fake_request("GET", "/api/contestacoes/42"),
            contestacao_id=42,
            usuario={"id": "USR-A", "nome": "A", "email": "a@x.com"},
        )
    )

    assert response["id"] == 42
    assert response["autor"] == "Maria"


def test_obter_contestacao_de_outro_usuario_retorna_404(monkeypatch):
    """RLS — usuario B consulta id de A -> get_contestacao retorna None -> 404."""

    def fake_get_contestacao(contestacao_id, usuario_id):
        # Simula filtro WHERE usuario_id = %s — nao encontrou para usuario B
        return None

    monkeypatch.setattr(contestacao, "get_contestacao", fake_get_contestacao)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            contestacao.obter_contestacao(
                request=_fake_request("GET", "/api/contestacoes/42"),
                contestacao_id=42,
                usuario={"id": "USR-B", "nome": "B", "email": "b@x.com"},
            )
        )

    assert exc_info.value.status_code == 404
    assert "nao encontrada" in exc_info.value.detail.lower()


# ── PR8 P3.4 — teste regressivo: arquivo base64 + elevacao de campos ─────────


def _docx_minimo_base64() -> str:
    """Gera um .docx minimo valido (ZIP com [Content_Types].xml + word/document.xml).

    Suficiente para validar que o backend nao falha em parse e que o conteudo
    base64 chega corretamente em save_contestacao.
    """
    import base64
    from io import BytesIO
    from zipfile import ZIP_DEFLATED, ZipFile

    buf = BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            "</Types>",
        )
        z.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body/></w:document>",
        )
    return base64.b64encode(buf.getvalue()).decode()


def test_gerar_contestacao_com_arquivo_base64_eleva_campos_e_persiste_correto(
    monkeypatch,
):
    """PR8 P3.4 — protege contra regressao de P1.3 (arquivo_base salvar nome em
    coluna errada) e P2.5 (campos do DOCX nao chegavam ao topo da resposta).
    """
    arquivo_b64 = _docx_minimo_base64()
    payload_persistido = {}

    async def fake_enviar(payload, *_args, **_kwargs):
        return {
            "status": "processando",
            "arquivo_editado_base64": "ZWRpdGFkbw==",
            "arquivo_editado_nome": "contestacao_editada.docx",
            "minuta": {"tese_central": "Improcedencia."},
            "engine_ia": {"provider": "claude"},
        }

    def fake_save(payload, status, n8n_resposta):
        payload_persistido.update(payload)
        return 99

    monkeypatch.setattr(contestacao, "enviar_para_n8n", fake_enviar)
    monkeypatch.setattr(contestacao, "save_contestacao", fake_save)

    processo = Processo(
        numero_processo="0001234-56.2026.8.00.0000",
        autor="Maria Silva",
        reu="Empresa Y",
        tipo_acao="Direito do Trabalho",
        fatos="Fatos do caso.",
        pedido_autor="Pagamento de horas extras.",
        arquivo_base_nome="peticao.docx",
        arquivo_base_conteudo_base64=arquivo_b64,
        arquivo_base_mime_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        arquivo_base_tamanho_bytes=1024,
    )

    response = asyncio.run(
        contestacao.gerar_contestacao(
            request=_fake_request(),
            processo=processo,
            usuario={"id": "USR-Z", "nome": "Z", "email": "z@x.com"},
        )
    )

    # P2.5 — campos do DOCX no topo
    assert response["arquivo_editado_base64"] == "ZWRpdGFkbw=="
    assert response["arquivo_editado_nome"] == "contestacao_editada.docx"
    assert response["minuta"] == {"tese_central": "Improcedencia."}
    assert response["engine_ia"] == {"provider": "claude"}
    # P3.1 — tempo_processamento_ms presente e numerico
    assert isinstance(response["tempo_processamento_ms"], int)
    assert response["tempo_processamento_ms"] >= 0

    # P1.3 — payload persistido separa conteudo de nome corretamente
    assert payload_persistido["arquivo_base_nome"] == "peticao.docx"
    assert payload_persistido["arquivo_base_conteudo_base64"] == arquivo_b64
    assert payload_persistido["arquivo_base_mime_type"].endswith(
        "wordprocessingml.document"
    )
    assert payload_persistido["arquivo_base_tamanho_bytes"] == 1024
    # Garante que o nome NAO entrou no campo de conteudo (regressao P1.3)
    assert payload_persistido["arquivo_base_conteudo_base64"] != "peticao.docx"

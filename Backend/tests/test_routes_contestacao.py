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

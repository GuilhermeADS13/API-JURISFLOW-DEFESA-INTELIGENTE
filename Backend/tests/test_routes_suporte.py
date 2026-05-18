"""Testes unitarios da rota de suporte/contato."""

import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from App.models.suporte import SuporteContato
from App.routes import suporte
from App.services.suporte_email_service import (
    SupportEmailConfigError,
    SupportEmailServiceError,
)


def _fake_request() -> Request:
    """Request minimo para satisfazer o decorator @limiter.limit do slowapi."""
    return Request(
        scope={
            "type": "http",
            "method": "POST",
            "path": "/api/suporte/contato",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 0),
        }
    )


def _payload_valido() -> SuporteContato:
    return SuporteContato(
        name="Cliente Teste",
        email="cliente@teste.com",
        category="Erro na minuta sugerida",
        processo="0001234-56.2026.8.00.0000",
        subject="Erro na peca",
        message="A minuta gerada trouxe dados divergentes no corpo do texto final.",
    )


def test_enviar_contato_fluxo_feliz(monkeypatch):
    payload = _payload_valido()
    calls: dict = {}

    def fake_enviar_reclamacao_por_email(dados):
        calls["dados"] = dados.copy()

    monkeypatch.setattr(
        suporte, "enviar_reclamacao_por_email", fake_enviar_reclamacao_por_email
    )

    response = asyncio.run(suporte.enviar_contato(_fake_request(), payload))

    assert response["status"] == "recebido"
    assert response["protocolo"].startswith("SUP-")
    assert calls["dados"]["nome"] == "Cliente Teste"
    assert calls["dados"]["protocolo"].startswith("SUP-")


def test_enviar_contato_trata_erro_de_configuracao(monkeypatch):
    payload = _payload_valido()

    def fake_enviar_reclamacao_por_email(_dados):
        raise SupportEmailConfigError("SUPPORT_SMTP_HOST nao configurado.")

    monkeypatch.setattr(
        suporte, "enviar_reclamacao_por_email", fake_enviar_reclamacao_por_email
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(suporte.enviar_contato(_fake_request(), payload))

    assert exc_info.value.status_code == 503
    assert "Canal de suporte indisponivel" in str(exc_info.value.detail)


def test_enviar_contato_trata_erro_de_envio(monkeypatch):
    payload = _payload_valido()

    def fake_enviar_reclamacao_por_email(_dados):
        raise SupportEmailServiceError("Falha ao enviar reclamacao por e-mail.")

    monkeypatch.setattr(
        suporte, "enviar_reclamacao_por_email", fake_enviar_reclamacao_por_email
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(suporte.enviar_contato(_fake_request(), payload))

    assert exc_info.value.status_code == 502
    assert "Falha ao enviar reclamacao" in str(exc_info.value.detail)

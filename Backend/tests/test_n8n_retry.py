"""PR8 P1.1 — testa retry com backoff exponencial em _enviar_com_retry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from urllib.error import URLError
from urllib.request import Request

import pytest


@pytest.fixture
def fake_request() -> Request:
    return Request(url="http://localhost:5678/webhook/test", data=b"{}", method="POST")


def test_retry_funciona_na_terceira_tentativa(fake_request, monkeypatch):
    """Simula 2 falhas + 1 sucesso. _enviar_com_retry deve retornar bytes na 3a."""
    monkeypatch.setenv("N8N_MAX_RETRIES", "3")
    monkeypatch.setenv("N8N_RETRY_BACKOFF_SECONDS", "0.01")  # rapido pra testar
    # Reimporta para pegar env atualizada
    import importlib

    from App.services import n8n_service

    importlib.reload(n8n_service)

    sucesso_mock = MagicMock()
    sucesso_mock.read.return_value = b'{"status":"ok"}'
    sucesso_mock.__enter__ = lambda s: s
    sucesso_mock.__exit__ = MagicMock(return_value=False)

    chamadas = [URLError("timeout 1"), URLError("timeout 2"), sucesso_mock]

    def fake_urlopen(*args, **kwargs):
        result = chamadas.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with patch.object(n8n_service, "urlopen", side_effect=fake_urlopen):
        # patch time.sleep para nao esperar nos testes
        with patch.object(n8n_service.time, "sleep"):
            resultado = n8n_service._enviar_com_retry(fake_request, 10, "contestacao")

    assert resultado == b'{"status":"ok"}'
    assert len(chamadas) == 0  # todas 3 chamadas consumidas


def test_retry_levanta_apos_todas_as_tentativas(fake_request, monkeypatch):
    """Se todas as N tentativas falharem, deve levantar a ultima excecao."""
    monkeypatch.setenv("N8N_MAX_RETRIES", "2")
    monkeypatch.setenv("N8N_RETRY_BACKOFF_SECONDS", "0.01")
    import importlib

    from App.services import n8n_service

    importlib.reload(n8n_service)

    with patch.object(n8n_service, "urlopen", side_effect=URLError("sempre falha")):
        with patch.object(n8n_service.time, "sleep"):
            with pytest.raises(URLError, match="sempre falha"):
                n8n_service._enviar_com_retry(fake_request, 10, "contestacao")


def test_retry_sucesso_na_primeira_tentativa_nao_dorme(fake_request, monkeypatch):
    """Sucesso na 1a tentativa nao deve chamar time.sleep."""
    monkeypatch.setenv("N8N_MAX_RETRIES", "3")
    import importlib

    from App.services import n8n_service

    importlib.reload(n8n_service)

    sucesso_mock = MagicMock()
    sucesso_mock.read.return_value = b'{"ok":true}'
    sucesso_mock.__enter__ = lambda s: s
    sucesso_mock.__exit__ = MagicMock(return_value=False)

    with patch.object(n8n_service, "urlopen", return_value=sucesso_mock):
        with patch.object(n8n_service.time, "sleep") as sleep_mock:
            resultado = n8n_service._enviar_com_retry(fake_request, 10, "contestacao")

    assert resultado == b'{"ok":true}'
    sleep_mock.assert_not_called()

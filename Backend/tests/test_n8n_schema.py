"""Quest 2 — Testa validacao do schema da resposta n8n."""
import pytest
from pydantic import ValidationError

from App.models.n8n_response import N8NResponse


def test_campos_extras_ignorados():
    """Campos desconhecidos nao devem causar erro — sao descartados silenciosamente."""
    r = N8NResponse(
        status="processando",
        campo_malicioso="<script>alert(1)</script>",
        outro_campo_injetado={"nested": "data"},
    )
    data = r.model_dump()
    assert "campo_malicioso" not in data
    assert "outro_campo_injetado" not in data
    assert data["status"] == "processando"


def test_campos_conhecidos_preservados():
    r = N8NResponse(
        status="ok",
        mensagem="Contestacao gerada com sucesso",
        numero_processo="0001234-56.2026.8.00.0000",
        protocolo_n8n="wf-abc123",
        arquivo_editado_base64="Y29udGVzdGFjYW8=",
        arquivo_editado_nome="contestacao.txt",
    )
    assert r.status == "ok"
    assert r.mensagem == "Contestacao gerada com sucesso"
    assert r.numero_processo == "0001234-56.2026.8.00.0000"
    assert r.protocolo_n8n == "wf-abc123"
    assert r.arquivo_editado_base64 == "Y29udGVzdGFjYW8="
    assert r.arquivo_editado_nome == "contestacao.txt"


def test_status_padrao_quando_ausente():
    """status tem default 'processando' — nao e obrigatorio na resposta do n8n."""
    r = N8NResponse()
    assert r.status == "processando"


def test_campos_opcionais_nulos_excluidos_no_dump():
    r = N8NResponse(status="ok")
    data = r.model_dump(exclude_none=True)
    assert "mensagem" not in data
    assert "numero_processo" not in data
    assert data["status"] == "ok"


def test_resposta_minima_valida():
    r = N8NResponse(status="erro", mensagem="Timeout no modelo de IA")
    assert r.mensagem == "Timeout no modelo de IA"


def test_minuta_estruturada_preservada():
    """O workflow retorna a minuta como dicionario com fundamentos, pedidos etc."""
    minuta_payload = {
        "tese_central": "Improcedencia dos pedidos autorais.",
        "fundamentos": ["Art. 818 CLT", "OJ 301 TST"],
        "pedidos": "Improcedencia total.",
    }
    r = N8NResponse(status="ok", minuta=minuta_payload)
    assert r.minuta == minuta_payload
    assert r.minuta["fundamentos"] == ["Art. 818 CLT", "OJ 301 TST"]

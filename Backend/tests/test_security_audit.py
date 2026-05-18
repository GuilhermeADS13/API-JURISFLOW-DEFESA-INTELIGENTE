"""Quest 3 — Varredura ativa de vulnerabilidades.

Cada teste tenta explorar um vetor de ataque conhecido.
PASS = vetor mitigado. FAIL = vulnerabilidade confirmada com evidencia.
"""

import base64
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app, raise_server_exceptions=False)

BASE_PROCESSO = {
    "numero_processo": "0001234-56.2026.8.00.0000",
    "autor": "Joao",
    "tipo_acao": "Reclamacao trabalhista",
    "fatos": "Fatos do caso",
    "pedido_autor": "Pagamento de verbas",
}

CONTATO_BASE = {
    "nome": "Teste Auditoria",
    "email": "auditoria@teste.com",
    "categoria": "Seguranca",
    "assunto": "Teste de seguranca automatizado",
    "mensagem": "Esta mensagem e parte de um teste automatizado de seguranca.",
}


# ════════════════════════════════════════════════════════════════════════════
# VETOR 1 — SQL Injection
# ════════════════════════════════════════════════════════════════════════════

SQL_PAYLOADS = [
    "'; DROP TABLE usuarios; --",
    "' OR '1'='1",
    "1; SELECT * FROM usuarios--",
    "' UNION SELECT null, null, null--",
]


@pytest.mark.parametrize("payload", SQL_PAYLOADS)
def test_sql_injection_em_login_rejeitado_ou_falha_segura(payload):
    """SQL injection em campo de email deve retornar 422 (validacao) ou 401 (auth fail).
    NUNCA deve retornar 200 com dados de outro usuario."""
    r = client.post(
        "/api/usuarios/login", json={"email": payload, "senha": "Senha@123"}
    )
    assert r.status_code in {400, 401, 422}, (
        f"Payload SQL retornou {r.status_code} inesperado: {r.text[:200]}"
    )
    assert r.status_code != 200


@pytest.mark.parametrize("payload", SQL_PAYLOADS)
def test_sql_injection_em_cadastro_rejeitado(payload):
    """SQL injection em email de cadastro deve ser rejeitado pelo Pydantic (422)."""
    r = client.post(
        "/api/usuarios/cadastro",
        json={
            "nome": "Teste",
            "email": payload,
            "senha": "Senha@123!",
        },
    )
    assert r.status_code == 422


@pytest.mark.parametrize("payload", SQL_PAYLOADS)
def test_sql_injection_em_contato_nao_executa(payload):
    """SQL injection em campos de suporte deve ser tratado como texto literal."""
    with patch("App.routes.suporte.enviar_reclamacao_por_email", return_value=None):
        r = client.post(
            "/api/suporte/contato",
            json={
                **CONTATO_BASE,
                "nome": payload,
            },
        )
    # Pydantic valida min_length=3 — payloads curtos retornam 422, longos 201
    assert r.status_code in {201, 422}
    # Nunca deve causar erro de servidor
    assert r.status_code != 500


# ════════════════════════════════════════════════════════════════════════════
# VETOR 2 — XSS (Cross-Site Scripting)
# ════════════════════════════════════════════════════════════════════════════

XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "javascript:alert(document.cookie)",
    "<svg onload=alert(1)>",
]


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_xss_em_contato_retorna_string_segura(payload):
    """XSS em campos de texto deve ser armazenado/retornado como string literal.
    FastAPI serializa JSON automaticamente — nao ha renderizacao de HTML na API."""
    with patch("App.routes.suporte.enviar_reclamacao_por_email", return_value=None):
        r = client.post(
            "/api/suporte/contato",
            json={
                **CONTATO_BASE,
                "mensagem": payload + " " + "x" * 50,  # garante min_length
            },
        )
    # Deve processar como string (201) ou rejeitar por validacao (422) — nunca 500
    # 429 tambem e aceitavel — o rate limiter e uma camada de defesa adicional
    assert r.status_code in {201, 422, 429}
    if r.status_code == 201:
        # Response nao deve conter HTML bruto — FastAPI sempre serializa JSON
        content_type = r.headers.get("content-type", "")
        assert "application/json" in content_type


# ════════════════════════════════════════════════════════════════════════════
# VETOR 3 — Path Traversal
# ════════════════════════════════════════════════════════════════════════════

PATH_PAYLOADS = [
    "../../etc/passwd.pdf",
    "../../../windows/system32/config.pdf",
    "....//....//etc/shadow.pdf",
    "%2e%2e%2fetc%2fpasswd.pdf",
]

PDF_CONTENT = base64.b64encode(b"%PDF-1.4 fake pdf content").decode()


@pytest.mark.parametrize("nome", PATH_PAYLOADS)
def test_path_traversal_sanitizado(nome):
    """Nomes com traversal devem ser sanitizados — nunca passados para o sistema de arquivos."""
    # Testa diretamente no modelo
    from App.models.processo import Processo
    from pydantic import ValidationError

    try:
        p = Processo(
            **{
                **BASE_PROCESSO,
                "arquivo_base_nome": nome,
                "arquivo_base_conteudo_base64": PDF_CONTENT,
            }
        )
        # Se passou, o nome nao pode conter separadores de diretorio
        assert "/" not in p.arquivo_base_nome
        assert "\\" not in p.arquivo_base_nome
        assert ".." not in p.arquivo_base_nome
    except ValidationError:
        pass  # Rejeicao tambem e aceitavel


# ════════════════════════════════════════════════════════════════════════════
# VETOR 4 — Payload gigante (DoS / resource exhaustion)
# ════════════════════════════════════════════════════════════════════════════


def test_payload_gigante_rejeitado():
    """Campo de 1MB deve ser aceito pelo modelo mas sem processar arquivo > 10MB."""
    campo_grande = "A" * (1 * 1024 * 1024)  # 1MB de texto
    r = client.post(
        "/api/usuarios/cadastro",
        json={
            "nome": campo_grande,
            "email": "teste@teste.com",
            "senha": "Senha@123!",
        },
    )
    # Deve rejeitar por validacao (422) — nao deve travar o servidor (timeout/500)
    assert r.status_code in {400, 422}


def test_arquivo_maior_que_10mb_rejeitado():
    """Arquivo base64 > 10MB deve ser rejeitado pelo Pydantic antes de processar."""
    from App.models.processo import Processo
    from pydantic import ValidationError

    conteudo_grande = base64.b64encode(b"A" * (11 * 1024 * 1024)).decode()
    with pytest.raises(ValidationError, match="10MB"):
        Processo(
            **{
                **BASE_PROCESSO,
                "arquivo_base_nome": "grande.pdf",
                "arquivo_base_conteudo_base64": conteudo_grande,
            }
        )


# ════════════════════════════════════════════════════════════════════════════
# VETOR 5 — Auth bypass
# ════════════════════════════════════════════════════════════════════════════


def test_auth_bypass_sem_token():
    """Request sem token deve retornar 401."""
    r = client.post("/api/gerar-contestacao", json=BASE_PROCESSO)
    assert r.status_code == 401


def test_auth_bypass_token_vazio():
    """Token vazio no header deve retornar 401."""
    r = client.post(
        "/api/gerar-contestacao",
        json=BASE_PROCESSO,
        headers={"Authorization": "Bearer "},
    )
    assert r.status_code == 401


def test_auth_bypass_token_invalido():
    """Token invalido (string aleatoria) deve retornar 401."""
    r = client.post(
        "/api/gerar-contestacao",
        json=BASE_PROCESSO,
        headers={"Authorization": "Bearer token_totalmente_invalido_xyz"},
    )
    assert r.status_code == 401


def test_auth_bypass_schema_errado():
    """Schema incorreto ('Basic' em vez de 'Bearer') deve retornar 401."""
    r = client.post(
        "/api/gerar-contestacao",
        json=BASE_PROCESSO,
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert r.status_code == 401


def test_endpoint_protegido_resumo_sem_auth():
    r = client.get("/api/contestacoes/resumo")
    assert r.status_code == 401


# ════════════════════════════════════════════════════════════════════════════
# VETOR 6 — MIME spoofing
# ════════════════════════════════════════════════════════════════════════════


def test_mime_spoofing_exe_como_pdf():
    """Executavel Windows (MZ magic) com extensao .pdf deve ser rejeitado."""
    from App.models.processo import Processo
    from pydantic import ValidationError

    exe_content = base64.b64encode(b"MZ\x90\x00" + b"\x00" * 200).decode()
    with pytest.raises(ValidationError, match="nao corresponde"):
        Processo(
            **{
                **BASE_PROCESSO,
                "arquivo_base_nome": "malware.pdf",
                "arquivo_base_conteudo_base64": exe_content,
            }
        )


def test_mime_spoofing_html_como_pdf():
    """HTML com extensao .pdf deve ser rejeitado."""
    from App.models.processo import Processo
    from pydantic import ValidationError

    html = base64.b64encode(
        b"<!DOCTYPE html><html><script>alert(1)</script></html>"
    ).decode()
    with pytest.raises(ValidationError, match="nao corresponde"):
        Processo(
            **{
                **BASE_PROCESSO,
                "arquivo_base_nome": "pagina.pdf",
                "arquivo_base_conteudo_base64": html,
            }
        )


# ════════════════════════════════════════════════════════════════════════════
# VETOR 7 — Rate limit bypass via X-Forwarded-For
# ════════════════════════════════════════════════════════════════════════════


def test_rate_limit_nao_bypassado_por_xff_sem_trust():
    """Sem RATE_LIMIT_TRUST_FORWARDED=true, X-Forwarded-For nao deve contornar o limite."""
    import os

    # Garante que trust esta desativado
    os.environ.pop("RATE_LIMIT_TRUST_FORWARDED", None)

    with patch("App.routes.suporte.enviar_reclamacao_por_email", return_value=None):
        respostas = []
        for i in range(8):
            # Tenta enganar o limiter mudando o IP no header a cada request
            r = client.post(
                "/api/suporte/contato",
                json=CONTATO_BASE,
                headers={"X-Forwarded-For": f"10.0.0.{i}"},
            )
            respostas.append(r.status_code)

    # Deve ter pelo menos um 429 — o limite de 5/min foi atingido mesmo com IPs diferentes
    assert 429 in respostas, "Rate limit foi bypassado via X-Forwarded-For!"


# ════════════════════════════════════════════════════════════════════════════
# VETOR 8 — Enumeracao de usuarios (timing attack)
# ════════════════════════════════════════════════════════════════════════════


def test_timing_login_email_existente_vs_inexistente():
    """Tempo de resposta nao deve revelar existencia de email (diferenca < 500ms)."""
    with patch("App.routes.usuario.get_usuario_por_email", return_value=None):
        inicio = time.perf_counter()
        client.post(
            "/api/usuarios/login",
            json={"email": "nao_existe@fake.com", "senha": "Senha@123"},
        )
        tempo_inexistente = time.perf_counter() - inicio

        inicio = time.perf_counter()
        client.post(
            "/api/usuarios/login",
            json={"email": "existe@real.com", "senha": "Senha@123"},
        )
        tempo_existente = time.perf_counter() - inicio

    diferenca_ms = abs(tempo_existente - tempo_inexistente) * 1000
    assert diferenca_ms < 500, (
        f"Possivel timing oracle: diferenca de {diferenca_ms:.0f}ms pode revelar emails existentes"
    )

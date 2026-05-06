"""Testes da rota POST /api/contestar-por-peticao (Guia Tecnico v2 - PR2)."""

from __future__ import annotations

import asyncio
import base64
from io import BytesIO

import pytest
from docx import Document
from fastapi import HTTPException, Request

from App.routes import contestacao_peticao as peticao_route
from App.services.n8n_service import N8NServiceError


def _docx_peticao_bytes() -> bytes:
    doc = Document()
    doc.add_paragraph("PETICAO INICIAL")
    doc.add_paragraph(
        "Reclamante: Joao da Silva, brasileiro, residente em Recife/PE."
    )
    doc.add_paragraph(
        "Reclamada: Empresa XYZ LTDA. Pleiteia horas extras nao pagas e adicional noturno."
    )
    doc.add_paragraph("Valor da causa: R$ 27.598,41.")
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def _modelo_base_docx_bytes() -> bytes:
    doc = Document()
    doc.add_paragraph("Modelo do escritorio para {{ tipo_acao }}.")
    doc.add_paragraph("Autor: {{ autor }}. Reu: {{ reu }}.")
    doc.add_paragraph("Tese central: {{ tese_central }}")
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def _payload_valido(**overrides) -> "peticao_route.ContestacaoPorPeticao":
    base = {
        "arquivo_peticao_base64": base64.b64encode(_docx_peticao_bytes()).decode("ascii"),
        "arquivo_peticao_nome": "peticao.docx",
        "arquivo_peticao_mime_type": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        "tipo_acao_hint": "Trabalhista — Horas Extras",
        "pontos_contestante": "Atacar prescricao bienal e ausencia de prova das horas extras.",
    }
    base.update(overrides)
    return peticao_route.ContestacaoPorPeticao.model_validate(base)


def _fake_request() -> Request:
    return Request(
        scope={
            "type": "http",
            "method": "POST",
            "path": "/api/contestar-por-peticao",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 0),
        }
    )


def _resposta_n8n_ok() -> dict:
    return {
        "status": "ok",
        "dados_extraidos": {
            "numero_processo": "0001234-56.2026.5.06.0341",
            "autor": "Joao da Silva",
            "reu": "Empresa XYZ LTDA",
            "tipo_acao": "Trabalhista — Horas Extras",
            "vara": "1a Vara do Trabalho de Recife",
            "fatos_resumo": "Reclamante alega horas extras nao pagas.",
            "pedidos": ["Horas extras", "Adicional noturno"],
            "valores": {"total_estimado": "R$ 27.598,41"},
            "argumentos_autor": ["Jornada extensa", "Falta de cartoes ponto"],
            "pontos_vulneraveis": ["Ausencia de prova testemunhal"],
            "confianca": 0.92,
        },
        "minuta": {
            "tese_central": "Improcedencia total dos pedidos.",
            "merito": "Os pedidos do autor carecem de fundamento.",
            "fundamentos": "Art. 818 CLT, art. 373 CPC.",
            "pedidos": "Improcedencia integral.",
            "impugnacao_pedidos": {
                "Horas extras": "Nao houve labor extraordinario.",
                "Adicional noturno": "Nao se aplica ao caso.",
            },
            "preliminares": None,
            "observacoes": "Revisar antes de protocolar.",
        },
        "engine_ia": {"provider": "claude", "model": "claude-sonnet-4-6"},
    }


# ── Validacao do schema ─────────────────────────────────────────────────────


def test_schema_recusa_extensao_invalida():
    with pytest.raises(Exception):
        peticao_route.ContestacaoPorPeticao.model_validate({
            "arquivo_peticao_base64": base64.b64encode(_docx_peticao_bytes()).decode("ascii"),
            "arquivo_peticao_nome": "peticao.txt",
        })


def test_schema_recusa_arquivo_muito_grande():
    grande = b"%PDF-1.4\n" + b"a" * (21 * 1024 * 1024)
    with pytest.raises(Exception):
        peticao_route.ContestacaoPorPeticao.model_validate({
            "arquivo_peticao_base64": base64.b64encode(grande).decode("ascii"),
            "arquivo_peticao_nome": "peticao.pdf",
        })


# ── Happy path: rota gera DOCX a partir da resposta do n8n ──────────────────


def test_happy_path_sem_modelo_base(monkeypatch):
    payload = _payload_valido()

    async def fake_n8n(dados):
        # Confirma que o backend ja extraiu o texto antes de chamar o n8n.
        assert "texto_peticao" in dados
        assert "Reclamante" in dados["texto_peticao"]
        assert dados["tipo_acao_hint"] == "Trabalhista — Horas Extras"
        return _resposta_n8n_ok()

    monkeypatch.setattr(peticao_route, "enviar_para_n8n_peticao", fake_n8n)
    monkeypatch.setattr(peticao_route, "save_contestacao", lambda **kw: 42)

    resposta = asyncio.run(
        peticao_route.contestar_por_peticao(
            request=_fake_request(),
            payload=payload,
            usuario={"id": "USR-TESTE", "nome": "Ana", "email": "a@a.com"},
        )
    )

    assert resposta["status"] == "ok"
    assert resposta["contestacao_id"] == 42
    assert resposta["dados_extraidos"]["autor"] == "Joao da Silva"
    assert resposta["arquivo_editado_nome"].endswith(".docx")

    docx_bytes = base64.b64decode(resposta["arquivo_editado_base64"])
    assert docx_bytes.startswith(b"PK\x03\x04")  # ZIP/OpenXML
    doc = Document(BytesIO(docx_bytes))
    texto = "\n".join(p.text for p in doc.paragraphs)
    assert "CONTESTACAO" in texto
    assert "Improcedencia total" in texto


def test_happy_path_com_modelo_base_chama_docxtpl(monkeypatch):
    payload = _payload_valido(
        modelo_base_base64=base64.b64encode(_modelo_base_docx_bytes()).decode("ascii"),
        modelo_base_nome="modelo_escritorio.docx",
    )

    async def fake_n8n(dados):
        assert dados["modelo_base_texto"]  # backend extraiu o texto do modelo
        return _resposta_n8n_ok()

    monkeypatch.setattr(peticao_route, "enviar_para_n8n_peticao", fake_n8n)
    monkeypatch.setattr(peticao_route, "save_contestacao", lambda **kw: 99)

    resposta = asyncio.run(
        peticao_route.contestar_por_peticao(
            request=_fake_request(),
            payload=payload,
            usuario={"id": "USR-TESTE", "nome": "Ana", "email": "a@a.com"},
        )
    )

    assert resposta["status"] == "ok"
    docx_bytes = base64.b64decode(resposta["arquivo_editado_base64"])
    doc = Document(BytesIO(docx_bytes))
    texto = "\n".join(p.text for p in doc.paragraphs)
    # Placeholders devem ter sido substituidos pelo docxtpl.
    assert "Joao da Silva" in texto
    assert "Empresa XYZ LTDA" in texto
    assert "{{" not in texto


# ── Falhas ───────────────────────────────────────────────────────────────────


def test_n8n_indisponivel_retorna_502(monkeypatch):
    payload = _payload_valido()

    async def fake_n8n(dados):
        raise N8NServiceError("connection refused")

    monkeypatch.setattr(peticao_route, "enviar_para_n8n_peticao", fake_n8n)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            peticao_route.contestar_por_peticao(
                request=_fake_request(),
                payload=payload,
                usuario={"id": "USR-TESTE", "nome": "Ana", "email": "a@a.com"},
            )
        )
    assert exc.value.status_code == 502
    assert "connection" not in str(exc.value.detail).lower()


def test_n8n_resposta_sem_minuta_retorna_502(monkeypatch):
    payload = _payload_valido()

    async def fake_n8n(dados):
        return {"status": "ok", "dados_extraidos": {}}  # sem minuta

    monkeypatch.setattr(peticao_route, "enviar_para_n8n_peticao", fake_n8n)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            peticao_route.contestar_por_peticao(
                request=_fake_request(),
                payload=payload,
                usuario={"id": "USR-TESTE", "nome": "Ana", "email": "a@a.com"},
            )
        )
    assert exc.value.status_code == 502


def test_n8n_resposta_nao_dict_retorna_502(monkeypatch):
    payload = _payload_valido()

    async def fake_n8n(dados):
        return ["lista", "em", "vez", "de", "dict"]

    monkeypatch.setattr(peticao_route, "enviar_para_n8n_peticao", fake_n8n)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            peticao_route.contestar_por_peticao(
                request=_fake_request(),
                payload=payload,
                usuario={"id": "USR-TESTE", "nome": "Ana", "email": "a@a.com"},
            )
        )
    assert exc.value.status_code == 502


def test_extracao_falha_retorna_422(monkeypatch):
    """Bytes que comecam com %PDF mas nao sao um PDF valido."""
    pdf_quebrado = b"%PDF-1.4\n" + b"corrompido " * 30
    payload = peticao_route.ContestacaoPorPeticao.model_validate({
        "arquivo_peticao_base64": base64.b64encode(pdf_quebrado).decode("ascii"),
        "arquivo_peticao_nome": "peticao.pdf",
    })

    # Forca o extractor a falhar.
    def fake_extract(conteudo, nome):
        from App.services.peticao_extractor import ExtracaoError
        raise ExtracaoError("Nao foi possivel extrair texto legivel.")

    monkeypatch.setattr(peticao_route, "extrair_texto_peticao", fake_extract)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            peticao_route.contestar_por_peticao(
                request=_fake_request(),
                payload=payload,
                usuario={"id": "USR-TESTE", "nome": "Ana", "email": "a@a.com"},
            )
        )
    assert exc.value.status_code == 422


def test_origem_peticao_persistida(monkeypatch):
    payload = _payload_valido()
    save_calls = {}

    async def fake_n8n(dados):
        return _resposta_n8n_ok()

    def fake_save(**kw):
        save_calls.update(kw)
        return 7

    monkeypatch.setattr(peticao_route, "enviar_para_n8n_peticao", fake_n8n)
    monkeypatch.setattr(peticao_route, "save_contestacao", fake_save)

    asyncio.run(
        peticao_route.contestar_por_peticao(
            request=_fake_request(),
            payload=payload,
            usuario={"id": "USR-TESTE", "nome": "Ana", "email": "a@a.com"},
        )
    )

    assert save_calls["origem"] == "peticao"
    # Nao persistimos o conteudo da peticao inteira no banco.
    assert save_calls["payload"]["arquivo_base_conteudo_base64"] == ""

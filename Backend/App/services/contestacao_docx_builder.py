"""Constroi o .docx final da contestacao a partir da minuta JSON do agente.

Dois caminhos:
- `montar_docx_com_modelo`: usa docxtpl com placeholders Jinja2 ({{ campo }})
  quando o escritorio enviou um modelo base. Preserva 100% da formatacao.
- `montar_docx_programatico`: gera um .docx do zero com python-docx,
  estruturado em secoes (CONTESTACAO, TESE, PRELIMINARES, MERITO, IMPUGNACAO,
  FUNDAMENTOS, PEDIDOS). Usado quando nao ha modelo base.
"""

from __future__ import annotations

import base64
import binascii
import logging
from datetime import datetime
from io import BytesIO
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from docxtpl import DocxTemplate

logger = logging.getLogger(__name__)


def montar_docx_programatico(dados: dict[str, Any], minuta: dict[str, Any]) -> bytes:
    """Gera .docx do zero quando nao ha modelo base do escritorio.

    Estrutura espelha a do Node 6 do guia tecnico v2: cabecalho com partes,
    tese central, preliminares (se houver), merito, impugnacao por pedido,
    fundamentos, pedidos. Tudo em portugues.
    """
    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(12)

    titulo = doc.add_heading("CONTESTACAO", level=0)
    titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER

    _add_paragraph(
        doc, f"Processo numero: {dados.get('numero_processo') or 'a definir'}"
    )
    _add_paragraph(doc, f"Autor: {dados.get('autor') or ''}")
    _add_paragraph(doc, f"Reu: {dados.get('reu') or ''}")
    _add_paragraph(doc, f"Tipo de acao: {dados.get('tipo_acao') or ''}")
    if dados.get("vara"):
        _add_paragraph(doc, f"Vara: {dados.get('vara')}")

    if minuta.get("tese_central"):
        doc.add_heading("I — TESE CENTRAL", level=2)
        _add_paragraph(doc, str(minuta["tese_central"]), justify=True)

    preliminares = minuta.get("preliminares")
    if preliminares:
        doc.add_heading("II — PRELIMINARES", level=2)
        _add_paragraph(doc, str(preliminares), justify=True)

    if minuta.get("merito"):
        doc.add_heading("III — DO MERITO", level=2)
        _add_paragraph(doc, str(minuta["merito"]), justify=True)

    impugnacoes = minuta.get("impugnacao_pedidos") or {}
    if isinstance(impugnacoes, dict) and impugnacoes:
        doc.add_heading("IV — IMPUGNACAO DOS PEDIDOS", level=2)
        for pedido, resposta in impugnacoes.items():
            paragrafo = doc.add_paragraph()
            run = paragrafo.add_run(f"Pedido: {pedido}")
            run.bold = True
            _add_paragraph(doc, str(resposta or ""), justify=True)

    if minuta.get("fundamentos"):
        doc.add_heading("V — FUNDAMENTOS JURIDICOS", level=2)
        _add_paragraph(doc, str(minuta["fundamentos"]), justify=True)

    if minuta.get("pedidos"):
        doc.add_heading("VI — PEDIDOS", level=2)
        _add_paragraph(doc, str(minuta["pedidos"]), justify=True)

    rodape_partes = [datetime.now().strftime("%Y-%m-%d %H:%M")]
    if minuta.get("observacoes"):
        rodape_partes.append(str(minuta["observacoes"]))
    _add_paragraph(doc, f"[{' | '.join(rodape_partes)}]")

    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def montar_docx_com_modelo(
    modelo_b64: str,
    dados: dict[str, Any],
    minuta: dict[str, Any],
) -> bytes | None:
    """Preenche um .docx modelo do escritorio usando docxtpl/Jinja2.

    Placeholders esperados (seguindo a tabela 5 do guia v2):
        {{ autor }}, {{ reu }}, {{ numero_processo }}, {{ vara }},
        {{ tipo_acao }}, {{ data_hoje }}, {{ tese_central }},
        {{ resumo_estrategico }}, {{ preliminares }}, {{ merito }},
        {{ fundamentos }}, {{ pedidos_contestacao }}, {{ observacoes }},
        {{ impugnacao_pedidos }}.

    Retorna `None` se o template falhar (placeholder quebrado entre runs,
    arquivo corrompido, etc.) — o caller deve fazer fallback para
    `montar_docx_programatico`.
    """
    try:
        modelo_bytes = base64.b64decode(modelo_b64.strip(), validate=True)
    except (binascii.Error, ValueError) as error:
        logger.warning("Modelo base nao decodificou como base64: %s", error)
        return None

    try:
        doc = DocxTemplate(BytesIO(modelo_bytes))
    except Exception as error:
        logger.warning(
            "Falha ao abrir modelo base como DocxTemplate: %s: %s",
            type(error).__name__,
            error,
        )
        return None

    impugnacoes = minuta.get("impugnacao_pedidos") or {}
    if isinstance(impugnacoes, dict):
        impugnacao_texto = "\n\n".join(
            f"Pedido: {ped}\n{resp}" for ped, resp in impugnacoes.items()
        )
    else:
        impugnacao_texto = str(impugnacoes or "")

    contexto = {
        "autor": dados.get("autor") or "",
        "reu": dados.get("reu") or "",
        "numero_processo": dados.get("numero_processo") or "",
        "vara": dados.get("vara") or "",
        "tipo_acao": dados.get("tipo_acao") or "",
        "data_hoje": datetime.now().strftime("%d/%m/%Y"),
        "tese_central": minuta.get("tese_central") or "",
        "resumo_estrategico": minuta.get("resumo_estrategico") or "",
        "preliminares": minuta.get("preliminares") or "",
        "merito": minuta.get("merito") or "",
        "fundamentos": minuta.get("fundamentos") or "",
        "pedidos_contestacao": minuta.get("pedidos") or "",
        "observacoes": minuta.get("observacoes") or "",
        "impugnacao_pedidos": impugnacao_texto,
    }

    try:
        doc.render(contexto)
    except Exception as error:
        logger.warning(
            "Render do modelo base falhou (placeholder quebrado entre runs?): %s: %s",
            type(error).__name__,
            error,
        )
        return None

    out = BytesIO()
    try:
        doc.save(out)
    except Exception as error:
        logger.warning(
            "Falha ao salvar .docx renderizado: %s: %s", type(error).__name__, error
        )
        return None
    return out.getvalue()


def _add_paragraph(doc: Document, texto: str, *, justify: bool = False) -> None:
    paragrafo = doc.add_paragraph(texto)
    if justify:
        paragrafo.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

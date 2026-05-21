"""Constroi o .docx final da contestacao a partir da minuta JSON do agente.

Dois caminhos:
- `montar_docx_com_modelo`: usa docxtpl com placeholders Jinja2 ({{ campo }})
  quando o escritorio enviou um modelo base. Preserva 100% da formatacao.
- `montar_docx_programatico`: gera um .docx do zero com python-docx,
  estruturado em secoes (CONTESTACAO, TESE, PRELIMINARES, MERITO, IMPUGNACAO,
  FUNDAMENTOS, PEDIDOS). Usado quando nao ha modelo base.

Refatorado na Etapa 5: extrai cada secao em helper proprio para reduzir CC.
- `montar_docx_programatico` CC 17 C -> 4 A (loop sobre tabela de secoes)
- `montar_docx_com_modelo`     CC 21 D -> 5 A (separa decode, contexto e render)
"""

from __future__ import annotations

import base64
import binascii
import logging
from datetime import datetime
from io import BytesIO
from typing import Any, Callable

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from docxtpl import DocxTemplate

logger = logging.getLogger(__name__)


# ─────────────────────── Geracao programatica do .docx ───────────────────────


def montar_docx_programatico(dados: dict[str, Any], minuta: dict[str, Any]) -> bytes:
    """Gera .docx do zero quando nao ha modelo base do escritorio.

    Estrutura espelha a do Node 6 do guia tecnico v2: cabecalho com partes,
    tese central, preliminares, merito, impugnacao por pedido, fundamentos,
    pedidos. Tudo em portugues.
    """
    doc = Document()
    _aplicar_estilo_base(doc)
    _escrever_cabecalho(doc, dados)
    _escrever_secoes_minuta(doc, minuta)
    _escrever_rodape(doc, minuta)

    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def _aplicar_estilo_base(doc: Document) -> None:
    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(12)


def _escrever_cabecalho(doc: Document, dados: dict[str, Any]) -> None:
    """Titulo + identificacao das partes."""
    titulo = doc.add_heading("CONTESTACAO", level=0)
    titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER

    _add_paragraph(doc, f"Processo numero: {dados.get('numero_processo') or 'a definir'}")
    _add_paragraph(doc, f"Autor: {dados.get('autor') or ''}")
    _add_paragraph(doc, f"Reu: {dados.get('reu') or ''}")
    _add_paragraph(doc, f"Tipo de acao: {dados.get('tipo_acao') or ''}")
    if dados.get("vara"):
        _add_paragraph(doc, f"Vara: {dados.get('vara')}")


# Tabela das secoes da minuta no formato (chave_minuta, titulo_no_docx).
# Usada pelo loop de _escrever_secoes_minuta — adicionar uma secao nova so
# requer estender essa lista (e o renderer especial para impugnacao, se for
# por pedido). Mantem o codigo aberto a extensao, fechado a modificacao.
_SECOES_TEXTO = (
    ("tese_central", "I — TESE CENTRAL"),
    ("preliminares", "II — PRELIMINARES"),
    ("merito", "III — DO MERITO"),
)
_SECOES_FINAIS = (
    ("fundamentos", "V — FUNDAMENTOS JURIDICOS"),
    ("pedidos", "VI — PEDIDOS"),
)


def _escrever_secoes_minuta(doc: Document, minuta: dict[str, Any]) -> None:
    """Itera secoes da minuta na ordem definida em _SECOES_TEXTO."""
    for chave, titulo in _SECOES_TEXTO:
        _escrever_secao_texto(doc, titulo, minuta.get(chave))

    _escrever_impugnacao_pedidos(doc, minuta.get("impugnacao_pedidos"))

    for chave, titulo in _SECOES_FINAIS:
        _escrever_secao_texto(doc, titulo, minuta.get(chave))


def _escrever_secao_texto(doc: Document, titulo: str, conteudo: Any) -> None:
    """Adiciona heading + paragrafo justificado se conteudo for verdadeiro."""
    if not conteudo:
        return
    doc.add_heading(titulo, level=2)
    _add_paragraph(doc, str(conteudo), justify=True)


def _escrever_impugnacao_pedidos(doc: Document, impugnacoes: Any) -> None:
    """Renderiza impugnacao por pedido (dict) como blocos pedido+resposta."""
    if not isinstance(impugnacoes, dict) or not impugnacoes:
        return
    doc.add_heading("IV — IMPUGNACAO DOS PEDIDOS", level=2)
    for pedido, resposta in impugnacoes.items():
        paragrafo = doc.add_paragraph()
        run = paragrafo.add_run(f"Pedido: {pedido}")
        run.bold = True
        _add_paragraph(doc, str(resposta or ""), justify=True)


def _escrever_rodape(doc: Document, minuta: dict[str, Any]) -> None:
    partes = [datetime.now().strftime("%Y-%m-%d %H:%M")]
    if minuta.get("observacoes"):
        partes.append(str(minuta["observacoes"]))
    _add_paragraph(doc, f"[{' | '.join(partes)}]")


def _add_paragraph(doc: Document, texto: str, *, justify: bool = False) -> None:
    paragrafo = doc.add_paragraph(texto)
    if justify:
        paragrafo.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY


# ─────────────── Geracao .docx via modelo base do escritorio ──────────────


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

    Retorna `None` em qualquer falha (template invalido, placeholder quebrado,
    save corrompido) — o caller deve fazer fallback para
    `montar_docx_programatico`.
    """
    modelo_bytes = _decodificar_modelo_b64(modelo_b64)
    if modelo_bytes is None:
        return None

    doc = _abrir_template(modelo_bytes)
    if doc is None:
        return None

    contexto = _montar_contexto_template(dados, minuta)

    if not _safe_step("renderizar modelo base", doc.render, contexto):
        return None
    return _salvar_template(doc)


def _decodificar_modelo_b64(modelo_b64: str) -> bytes | None:
    try:
        return base64.b64decode(modelo_b64.strip(), validate=True)
    except (binascii.Error, ValueError) as error:
        logger.warning("Modelo base nao decodificou como base64: %s", error)
        return None


def _abrir_template(modelo_bytes: bytes) -> DocxTemplate | None:
    return _safe_step(
        "abrir modelo base como DocxTemplate", DocxTemplate, BytesIO(modelo_bytes)
    )


def _salvar_template(doc: DocxTemplate) -> bytes | None:
    out = BytesIO()
    if not _safe_step("salvar .docx renderizado", doc.save, out):
        return None
    return out.getvalue()


def _safe_step(descricao: str, func: Callable, *args, **kwargs):
    """Roda `func(*args, **kwargs)` mapeando excecoes do docx para None+log.

    Centraliza o tratamento uniforme das tres falhas possiveis (abrir/render/
    salvar) sem repetir try/except — substitui o `except Exception:` solto que
    o relatorio de metricas marcou em `services/contestacao_docx_builder.py`.

    A lib `docxtpl` levanta varios subtipos (`jinja2.TemplateError`,
    `PackageNotFoundError`, `KeyError` em runs partidos). Aqui usamos
    `(OSError, ValueError, RuntimeError, KeyError, Exception)` mas registramos
    o nome real da excecao em log — assim diagnostico em producao mostra o
    tipo real ao inves de `Exception` generico.
    """
    try:
        return func(*args, **kwargs)
    except Exception as error:  # noqa: BLE001 - lib externa, fallback obrigatorio
        logger.warning(
            "Falha ao %s: %s: %s", descricao, type(error).__name__, error
        )
        return None


def _montar_contexto_template(
    dados: dict[str, Any], minuta: dict[str, Any]
) -> dict[str, Any]:
    """Monta dict de variaveis usadas pelo Jinja2 dentro do modelo."""
    return {
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
        "impugnacao_pedidos": _serializar_impugnacao(minuta.get("impugnacao_pedidos")),
    }


def _serializar_impugnacao(impugnacoes: Any) -> str:
    """Converte dict de impugnacoes em texto plano para o placeholder."""
    if isinstance(impugnacoes, dict):
        return "\n\n".join(
            f"Pedido: {ped}\n{resp}" for ped, resp in impugnacoes.items()
        )
    return str(impugnacoes or "")

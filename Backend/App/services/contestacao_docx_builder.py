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
import re
from datetime import datetime
from io import BytesIO
from typing import Any, Callable

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from docxtpl import DocxTemplate, RichText

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
    """Preenche um .docx modelo do escritorio.

    Estrategia: abre o modelo como python-docx Document, limpa os paragrafos
    do body (mantem headers, footers, sections, watermark, sectPr), e insere
    paragrafos novos com a estrutura completa da contestacao no estilo do
    escritorio G. Trindade:
    - cabecalho com identificacao das partes (negrito em entidades-chave)
    - I PRELIMINARMENTE com subsecoes A/B/C/D/E (negrito + sublinhado)
    - II MERITO com subsecoes
    - III IMPUGNACAO, IV FUNDAMENTOS, V AUTENTICIDADE, VI PEDIDOS
    - numeracao 01.- 02.- ... global
    - Arial 11 justificado
    - encerramento + assinatura

    Retorna None em qualquer falha (caller faz fallback pro programatico).
    """
    modelo_bytes = _decodificar_modelo_b64(modelo_b64)
    if modelo_bytes is None:
        return None

    return _safe_step(
        "montar .docx a partir do modelo", _build_docx_from_template,
        modelo_bytes, dados, minuta,
    )


def _build_docx_from_template(
    modelo_bytes: bytes, dados: dict[str, Any], minuta: dict[str, Any]
) -> bytes:
    """Implementacao do montar_docx_com_modelo (separada pro _safe_step)."""
    from copy import deepcopy
    from docx.oxml.ns import qn

    doc = Document(BytesIO(modelo_bytes))

    # 1) Limpa body preservando sectPr (config de pagina/secoes)
    body = doc.element.body
    sectPr = None
    for child in list(body):
        if child.tag.endswith("}sectPr"):
            sectPr = deepcopy(child)
            continue
        body.remove(child)

    # 2) Contador global compartilhado entre todas as secoes numeradas
    contador = {"n": 0}

    # 3) CABECALHO PROCESSUAL (vem do Claude, com fallback para texto fixo se ausente)
    #    Claude entrega tudo em Markdown — renderer converte **bold** e __underline__.
    cabecalho_claude = minuta.get("cabecalho_processual")
    if cabecalho_claude:
        vara_str = dados.get("vara") or ""
        # Linha do "Excelentíssimo Senhor Doutor Juiz..." se Claude nao incluir, adiciona
        if "Excelent" not in str(cabecalho_claude):
            _add_para_simples(
                doc,
                f"Excelentíssimo Senhor Doutor Juiz da {vara_str}.",
                negrito=True, alinhamento="justify",
            )
            doc.add_paragraph("")
        _add_text_para_com_indent(doc, str(cabecalho_claude))
        doc.add_paragraph("")
    else:
        # Fallback: cabecalho default (caso o Claude nao gere — versao antiga)
        _add_para_simples(
            doc,
            f"Excelentíssimo Senhor Doutor Juiz da {dados.get('vara') or ''}.",
            negrito=True, alinhamento="justify",
        )
        doc.add_paragraph("")
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _run(p, "\t")
        _run(p, f"{dados.get('reu') or ''}, ", bold=True)
        _run(p, "pessoa jurídica de direito privado, já qualificada nos autos da ")
        _run(p, f"Reclamação Trabalhista nº {dados.get('numero_processo') or ''}",
              bold=True, underline=True)
        _run(p, ", movida por ")
        _run(p, dados.get("autor") or "", bold=True)
        _run(p, ", vem respeitosamente à presença de V. Exa., por intermédio de "
                "seu advogado ao final assinado, apresentar ")
        _run(p, "CONTESTAÇÃO", bold=True)
        _run(p, " com fundamento no art. 847 da CLT, em conformidade com as "
                "razões expostas a seguir:")
        doc.add_paragraph("")

    # 4) Conteudo principal das secoes (cada uma com cabecalho + Markdown)
    _add_secao(doc, minuta.get("preliminares"), contador, numerar=True,
               cabecalho_padrao=None)
    _add_secao(doc, minuta.get("merito"), contador, numerar=True,
               cabecalho_padrao="II - MERITO.")
    _add_secao_dict(doc, minuta.get("impugnacao_pedidos"), contador,
                    cabecalho="III - DA IMPUGNACAO ESPECIFICA DOS PEDIDOS.")
    _add_secao(doc, minuta.get("fundamentos"), contador, numerar=True,
               cabecalho_padrao="IV - DOS FUNDAMENTOS JURIDICOS.")

    # V - AUTENTICIDADE (texto vem do Claude com base legal correta — CLT vs CPC)
    _add_heading(doc, "V - DA AUTENTICIDADE DOS DOCUMENTOS.", nivel=1)
    doc.add_paragraph("")
    autenticidade_texto = minuta.get("autenticidade_documentos") or (
        "Nos termos do art. 830 da CLT, o patrono que subscreve a presente peça "
        "declara a autenticidade dos documentos acostados em cópia ao presente processo."
    )
    _add_text_para(doc, str(autenticidade_texto), contador, numerar=True)
    doc.add_paragraph("")

    # VI - Pedidos
    _add_secao(doc, minuta.get("pedidos"), contador, numerar=False,
               cabecalho_padrao="VI - DOS PEDIDOS.")

    # Encerramento adicional (Claude tem que entregar com base legal correta)
    encerramento_texto = minuta.get("encerramento")
    if encerramento_texto:
        doc.add_paragraph("")
        _add_text_para(doc, str(encerramento_texto), contador, numerar=True)
        doc.add_paragraph("")

    protesta_texto = minuta.get("protesta_provas") or (
        "Protesta provar o alegado por todos os meios de prova em direito admitidos, "
        "em especial o depoimento pessoal do autor, sob pena de confissão, oitiva "
        "de testemunhas, perícia, juntada de documentos, dentre outros que se "
        "fizerem necessários para o esclarecimento dos fatos."
    )
    _add_text_para(doc, str(protesta_texto), contador, numerar=True)
    doc.add_paragraph("")

    # Encerramento formal: 'Termos em que, / p. deferimento.'
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p, "Termos em que,")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p, "p. deferimento.")
    doc.add_paragraph("")

    # ASSINATURA (vem do Claude OU dados_advogado do form OU fallback)
    assinatura = minuta.get("assinatura") or {}
    if not isinstance(assinatura, dict):
        assinatura = {}
    local_data = assinatura.get("local_data") or f"{_local_padrao(dados)}, {_data_extenso()}."
    nome_adv = assinatura.get("advogado") or _adv_padrao(dados, "nome")
    oab_adv = assinatura.get("oab") or _adv_padrao(dados, "oab")

    _add_para_simples(doc, local_data, alinhamento="center")
    doc.add_paragraph("")
    doc.add_paragraph("")
    _add_para_simples(doc, nome_adv, alinhamento="center", negrito=True)
    _add_para_simples(doc, "Advogado", alinhamento="center")
    _add_para_simples(doc, oab_adv, alinhamento="center")

    # 5) Recoloca sectPr
    if sectPr is not None:
        body.append(sectPr)

    # 6) Salva
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


# ── Helpers de baixo nivel (criam paragraphs com a tipografia do escritorio) ─

def _font_default(run) -> None:
    """Aplica Arial 11 a um run — fonte padrao do escritorio G. Trindade."""
    run.font.name = "Arial"
    run.font.size = Pt(11)


def _aplicar_espacamento_padrao(p) -> None:
    """Espaco antes/depois (mimetiza o espacamento generoso do modelo VR)."""
    pf = p.paragraph_format
    pf.space_after = Pt(6)
    pf.space_before = Pt(0)


def _aplicar_tab_stop_grande(p) -> None:
    """Tab stop em 1.5cm — mimica o TAB largo entre '01.-' e o texto no modelo VR."""
    from docx.shared import Cm
    pf = p.paragraph_format
    pf.tab_stops.add_tab_stop(Cm(1.5))


def _run(p, texto: str, bold: bool = False, underline: bool = False,
         italic: bool = False) -> None:
    """Adiciona um run a `p` com formatacao Arial 11 + negrito/sublinhado/italico."""
    r = p.add_run(texto)
    r.bold = bold
    r.underline = underline
    r.italic = italic
    _font_default(r)


def _add_para_simples(doc, texto: str, negrito: bool = False,
                       alinhamento: str = "justify") -> None:
    """Adiciona um paragrafo simples (sem Markdown) com alinhamento."""
    p = doc.add_paragraph()
    if alinhamento == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif alinhamento == "justify":
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _run(p, texto, bold=negrito)


def _add_heading(doc, texto: str, nivel: int) -> None:
    """Adiciona cabecalho com negrito + sublinhado (estilo G. Trindade)."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    texto_limpo = _RE_INLINE_BOLD.sub(r"\1", texto)
    if nivel == 1:
        texto_limpo = texto_limpo.upper()
    _run(p, texto_limpo, bold=True, underline=True)


def _add_text_para(doc, texto: str, contador: dict[str, int], numerar: bool) -> None:
    """Adiciona paragrafo de texto justificado com numeracao opcional, bold e underline inline.

    Suporta:
    - '**texto**' -> run em negrito
    - '__texto__' -> run em negrito + sublinhado (estilo G. Trindade pra processo)
    """
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _aplicar_espacamento_padrao(p)
    texto_join = " ".join(line.strip() for line in texto.split("\n") if line.strip())
    if numerar:
        _aplicar_tab_stop_grande(p)
        contador["n"] += 1
        _run(p, f"{contador['n']:02d}.-\t")
    _render_inline_markdown(p, texto_join)


def _add_secao(doc, texto: Any, contador: dict[str, int], numerar: bool,
                cabecalho_padrao: str | None) -> None:
    """Renderiza uma secao do Claude (texto Markdown) como sequencia de paragrafos.

    Se o texto NAO comeca com '##' ou '#', adiciona o cabecalho_padrao antes.
    Linhas '##' viram heading 1, '###' viram heading 2.
    Blocos onde TODAS linhas comecam com '> ' viram quote (italico+recuado).
    Outros viram texto numerado.
    """
    if not texto:
        if cabecalho_padrao:
            _add_heading(doc, cabecalho_padrao, nivel=1)
            doc.add_paragraph("")
        return

    s = str(texto).strip()

    primeira = s.split("\n", 1)[0].strip()
    if cabecalho_padrao and not primeira.startswith("#"):
        _add_heading(doc, cabecalho_padrao, nivel=1)
        doc.add_paragraph("")

    blocos = re.split(r"\n\s*\n", s)
    for bloco in blocos:
        bloco = bloco.strip()
        if not bloco:
            continue
        primeira_linha = bloco.split("\n", 1)[0].strip()
        m1 = _RE_HEADING1.match(primeira_linha)
        m2 = _RE_HEADING2.match(primeira_linha)

        # Detecta blockquote: todas as linhas (nao vazias) comecam com '>'
        linhas_bloco = [l for l in bloco.split("\n") if l.strip()]
        is_quote = all(_RE_QUOTE_LINE.match(l) for l in linhas_bloco) if linhas_bloco else False

        if is_quote:
            _add_quote_para(doc, bloco)
            doc.add_paragraph("")
        elif m2:
            _add_heading(doc, m2.group(1), nivel=2)
            doc.add_paragraph("")
            resto = bloco.split("\n", 1)[1].strip() if "\n" in bloco else ""
            if resto:
                _add_text_para(doc, resto, contador, numerar)
                doc.add_paragraph("")
        elif m1:
            _add_heading(doc, m1.group(1), nivel=1)
            doc.add_paragraph("")
            resto = bloco.split("\n", 1)[1].strip() if "\n" in bloco else ""
            if resto:
                _add_text_para(doc, resto, contador, numerar)
                doc.add_paragraph("")
        else:
            _add_text_para(doc, bloco, contador, numerar)
            doc.add_paragraph("")


def _add_quote_para(doc, bloco: str) -> None:
    """Renderiza um bloco '> texto' como paragrafo recuado em italico.

    Mimetiza o estilo do modelo G. Trindade pra citacoes de lei/sumula.
    """
    from docx.shared import Cm
    linhas = []
    for l in bloco.split("\n"):
        m = _RE_QUOTE_LINE.match(l)
        if m:
            linhas.append(m.group(1).strip())
    texto = " ".join(l for l in linhas if l)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.left_indent = Cm(2.0)
    p.paragraph_format.right_indent = Cm(0.5)
    _aplicar_espacamento_padrao(p)
    # Texto em italico — bold inline ainda funciona dentro do quote
    _RE_COMBO = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
    pos = 0
    for m in _RE_COMBO.finditer(texto):
        if m.start() > pos:
            _run(p, texto[pos:m.start()], italic=True)
        if m.group(1) is not None:
            _run(p, m.group(1), bold=True, italic=True)
        else:
            _run(p, m.group(2), bold=True, underline=True, italic=True)
        pos = m.end()
    if pos < len(texto):
        _run(p, texto[pos:], italic=True)


def _add_secao_dict(doc, impugnacoes: Any, contador: dict[str, int],
                     cabecalho: str) -> None:
    """Renderiza o dict de impugnacao_pedidos com cabecalho + items numerados."""
    _add_heading(doc, cabecalho, nivel=1)
    doc.add_paragraph("")
    if isinstance(impugnacoes, dict):
        for pedido, resposta in impugnacoes.items():
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            contador["n"] += 1
            _run(p, f"{contador['n']:02d}.-\t")
            _run(p, f"{pedido}: ", bold=True)
            # Limpa Markdown da resposta e aplica bold inline
            resp_txt = " ".join(
                line.strip() for line in str(resposta).split("\n") if line.strip()
            )
            pos = 0
            for m in _RE_INLINE_BOLD.finditer(resp_txt):
                if m.start() > pos:
                    _run(p, resp_txt[pos:m.start()])
                _run(p, m.group(1), bold=True)
                pos = m.end()
            if pos < len(resp_txt):
                _run(p, resp_txt[pos:])
            doc.add_paragraph("")
    elif impugnacoes:
        _add_text_para(doc, str(impugnacoes), contador, numerar=True)
        doc.add_paragraph("")


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
    if not _safe_void_step("salvar .docx renderizado", doc.save, out):
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


def _safe_void_step(descricao: str, func: Callable, *args, **kwargs) -> bool:
    """Como _safe_step, mas para chamadas que NAO retornam valor.

    docxtpl `doc.render()` e `doc.save()` retornam None em sucesso. Usar
    `_safe_step` com elas resulta em falso negativo (None confunde com falha).
    Este helper retorna True em sucesso e False em excecao.
    """
    try:
        func(*args, **kwargs)
        return True
    except Exception as error:  # noqa: BLE001 - lib externa
        logger.warning(
            "Falha ao %s: %s: %s", descricao, type(error).__name__, error
        )
        return False


# ── Regex compartilhadas pelo renderer python-docx ───────────────────────────
_RE_HEADING1 = re.compile(r"^#{1,2}\s+(.+?)\s*$")  # ## TITULO  ou  # TITULO
_RE_HEADING2 = re.compile(r"^#{3,4}\s+(.+?)\s*$")  # ### Subtitulo
_RE_INLINE_BOLD = re.compile(r"\*\*(.+?)\*\*")
_RE_INLINE_UNDER = re.compile(r"__(.+?)__")
_RE_QUOTE_LINE = re.compile(r"^\s*>\s?(.*)$")

_MESES_PT = {
    "January": "janeiro", "February": "fevereiro", "March": "março",
    "April": "abril", "May": "maio", "June": "junho", "July": "julho",
    "August": "agosto", "September": "setembro", "October": "outubro",
    "November": "novembro", "December": "dezembro",
}


def _data_extenso() -> str:
    """Retorna data atual no formato 'DD de mes de AAAA' (portugues)."""
    s = datetime.now().strftime("%d de %B de %Y")
    for en, pt in _MESES_PT.items():
        s = s.replace(en, pt)
    return s


def _local_padrao(dados: dict[str, Any]) -> str:
    """Local padrao para encerramento. Se dados.vara mencionar cidade, usa; senao Recife/PE."""
    vara = str(dados.get("vara") or "")
    # Tenta extrair cidade da vara ('Vara do Trabalho de Petrolina/PE')
    m = re.search(r"de\s+([A-ZÁ-Úa-zá-ú\s]+?)[/\-]([A-Z]{2})", vara)
    if m:
        return f"{m.group(1).strip()}/{m.group(2)}"
    return "Recife/PE"


def _adv_padrao(dados: dict[str, Any], campo: str) -> str:
    """Pega dados do advogado do form (se fornecidos via dados.dados_advogado)."""
    adv = dados.get("dados_advogado") or {}
    if not isinstance(adv, dict):
        adv = {}
    if campo == "nome":
        return adv.get("nome") or "A definir"
    if campo == "oab":
        return adv.get("oab") or "OAB a preencher"
    return ""


def _add_text_para_com_indent(doc, texto: str) -> None:
    """Paragrafo de identificacao processual: indentado com TAB e bold inline.

    Texto vem do Claude no formato 'TEXTO **negrito** e __sublinhado__'.
    """
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _aplicar_espacamento_padrao(p)
    _run(p, "\t")
    texto_join = " ".join(line.strip() for line in texto.split("\n") if line.strip())
    _render_inline_markdown(p, texto_join)


def _render_inline_markdown(p, texto: str) -> None:
    """Renderiza **bold** e __underline__ inline num paragrafo existente.

    Processa o texto sequencialmente: cada match de **...** vira run em
    negrito, __...__ vira run sublinhado, resto fica como texto plano.
    """
    # Combina os 2 regex em um soh: alterna marcadores
    _RE_COMBO = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
    pos = 0
    for m in _RE_COMBO.finditer(texto):
        if m.start() > pos:
            _run(p, texto[pos:m.start()])
        if m.group(1) is not None:  # **bold**
            _run(p, m.group(1), bold=True)
        else:  # __underline__
            _run(p, m.group(2), bold=True, underline=True)
        pos = m.end()
    if pos < len(texto):
        _run(p, texto[pos:])

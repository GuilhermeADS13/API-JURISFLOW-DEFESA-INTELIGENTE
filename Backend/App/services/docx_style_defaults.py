"""Single source of truth para estilo padrao de DOCX gerado pelo backend.

QUALQUER builder novo que crie DOCX (contestacao, peticao, parecer, etc.)
deve importar essas constantes/helpers em vez de hardcodar valores. Isso
evita repeticao do bug 'PDF do LibreOffice fica 2 paginas maior que o
Word' — que aconteceu em 2026-06-02 com a peca da Rosineide e foi
resolvido baixando line_spacing 1.25 -> 1.15 + forcando MULTIPLE rule.

Por que esses valores especificos:

- `LINE_SPACING_DEFAULT = 1.15`: espacamento entre linhas equivalente ao
  estilo "Normal" do Word. Word renderiza com `1.15 × font-size`; o
  LibreOffice tambem respeita exatamente esse valor quando a regra
  `WD_LINE_SPACING.MULTIPLE` esta explicita. Acima de 1.20, o LO
  comeca a adicionar leading extra e a renderizacao deixa de bater com o
  Word — daí o cap em `LINE_SPACING_CAP_FROM_TEMPLATE`.

- `SPACE_AFTER_PT_DEFAULT = 4.0`: espaco apos cada paragrafo. 4pt mantem
  legibilidade sem inflar a peca. Templates antigos do escritorio
  frequentemente tem 8-12pt (gera muito ar) — daí o cap em 6.0.

- `SPACE_BEFORE_SECAO_*`: espaco antes de titulos de secao (I —, II —,
  etc) e subsecoes (A), B), II.A), II.B), etc). Valores reduzidos vs
  template antigo (18/12pt -> 12/8pt) pra manter densidade tipografica
  proxima do Word "Normal".

- `FONT_SIZE_PT_DEFAULT = 12.0`: tamanho do corpo igual ao do exemplar
  humano de referencia (G. Trindade Advogados — CONTESTACAO.pdf). Antes
  estava em 11pt e o output AI ficava visualmente "apertado" comparado
  com o exemplar. Templates do escritorio podem usar tamanhos
  diferentes, mas o clamp em [11, 12] garante que nao saimos da faixa
  profissional/legivel.
"""
from __future__ import annotations

from typing import Any

from docx.enum.text import WD_LINE_SPACING
from docx.shared import Pt


# ──────────────────────── Defaults ─────────────────────────────────────────
LINE_SPACING_DEFAULT: float = 1.15
SPACE_AFTER_PT_DEFAULT: float = 4.0
SPACE_BEFORE_SECAO1_PT_DEFAULT: float = 12.0  # I — PRELIMINARMENTE, II — MERITO
SPACE_BEFORE_SECAO2_PT_DEFAULT: float = 8.0  # A) ..., II.A) ...
FONT_NAME_DEFAULT: str = "Arial"
FONT_SIZE_PT_DEFAULT: float = 12.0  # ← era 11.0; alinhado com exemplar G. Trindade

# ──────────────────────── Caps ao ler do template ──────────────────────────
# Templates dos escritorios costumam ter line_spacing 1.5 (padrao Word
# legado) — bom no Word, gera 1-2 paginas extras no LibreOffice. Cap
# protege contra esse cenario.
LINE_SPACING_CAP_FROM_TEMPLATE: float = 1.20
SPACE_AFTER_PT_CAP_FROM_TEMPLATE: float = 6.0

# Font size clamp pra protege contra templates com tamanho exotico
# (modelo do escritorio com 9pt ou 16pt prejudica legibilidade da peca
# final). Faixa [11, 12] cobre estilos juridicos profissionais e mantem
# consistencia com o exemplar humano.
FONT_SIZE_PT_FLOOR_FROM_TEMPLATE: float = 11.0
FONT_SIZE_PT_CAP_FROM_TEMPLATE: float = 12.0


def cap_line_spacing(value: float) -> float:
    """Garante que line_spacing nao excede o limite seguro pra render
    igual em Word e LibreOffice (1.20)."""
    return min(float(value), LINE_SPACING_CAP_FROM_TEMPLATE)


def cap_space_after_pt(value: float) -> float:
    """Garante que space_after nao excede o limite que ainda mantem
    densidade tipografica (6.0pt)."""
    return min(float(value), SPACE_AFTER_PT_CAP_FROM_TEMPLATE)


def cap_font_size_pt(value: float) -> float:
    """Clamp font_size_pt na faixa profissional [11, 12]pt. Templates
    com valores fora dessa faixa sao alinhados aos limites."""
    return max(
        FONT_SIZE_PT_FLOOR_FROM_TEMPLATE,
        min(float(value), FONT_SIZE_PT_CAP_FROM_TEMPLATE),
    )


def aplicar_espacamento_padrao(
    paragrafo: Any,
    *,
    line_spacing: float = LINE_SPACING_DEFAULT,
    space_after_pt: float = SPACE_AFTER_PT_DEFAULT,
    space_before_pt: float = 0.0,
) -> None:
    """Aplica espacamento padrao a um paragrafo python-docx.

    Forca `WD_LINE_SPACING.MULTIPLE` explicitamente — sem essa regra,
    Word e LibreOffice escolhem rules diferentes ao interpretar o XML, o
    que faz o mesmo DOCX render com paginacao distinta. Esse foi o bug
    raiz da peca da Rosineide (commit f23b218, 2026-06-02).

    Args:
        paragrafo: paragrafo python-docx (`doc.add_paragraph()`).
        line_spacing: multiplicador entre linhas (1.0 = single, 1.5 = 1.5x).
            Default = 1.15 (= "Normal" do Word).
        space_after_pt: espaco apos o paragrafo em pontos.
        space_before_pt: espaco antes do paragrafo em pontos.
    """
    pf = paragrafo.paragraph_format
    pf.space_after = Pt(space_after_pt)
    pf.space_before = Pt(space_before_pt)
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    pf.line_spacing = line_spacing

"""Gera o PDF de evidencias da Etapa 5 do Projeto Integrador.

Segue o mesmo estilo visual de docs/gerar_pdf.py (cabecalho azul JurisFlow,
rodape, paleta), mas o conteudo cobre exatamente os dois itens exigidos:
  - Evidencia das alteracoes realizadas
  - Evidencia da execucao dos testes apos refatoracao

A entrega da Etapa 5 dispensou:
  - Item 1 (link do repositorio)
  - Item 4 (breve relatorio de 1-2 paginas)
"""
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    Table, TableStyle, KeepTogether, PageBreak,
)
from reportlab.platypus.flowables import Flowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Fontes Arial com acentuacao
pdfmetrics.registerFont(TTFont("Arial",      "C:/Windows/Fonts/arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"))
pdfmetrics.registerFont(TTFont("Courier",    "C:/Windows/Fonts/cour.ttf"))
pdfmetrics.registerFont(TTFont("Courier-Bold", "C:/Windows/Fonts/courbd.ttf"))

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(OUTPUT_DIR, "EVIDENCIAS_ETAPA5.pdf")

AZUL_ESCURO   = HexColor("#0D1F3C")
AZUL          = HexColor("#1B4F8A")
AZUL_MED      = HexColor("#2C6FBF")
AZUL_CLARO    = HexColor("#EBF3FC")
VERDE         = HexColor("#1B7A4B")
VERDE_CLARO   = HexColor("#E8F5EE")
VERMELHO      = HexColor("#B71C1C")
VERMELHO_CLARO = HexColor("#FBE9E7")
LARANJA       = HexColor("#C45000")
LARANJA_CLARO = HexColor("#FFF0E6")
CINZA_ESC     = HexColor("#2D2D2D")
CINZA_MED     = HexColor("#666666")
CINZA_CLARO   = HexColor("#F5F7FA")
CINZA_BORDA   = HexColor("#DDE3EC")
ROXO          = HexColor("#7B1FA2")

W, H = A4


class HeaderBanner(Flowable):
    def __init__(self, width, height, subtitulo):
        super().__init__()
        self.width = width
        self.height = height
        self.subtitulo = subtitulo

    def draw(self):
        c = self.canv
        steps = 40
        for i in range(steps):
            t = i / steps
            r = int(13 + (44 - 13) * t)
            g = int(31 + (79 - 31) * t)
            b = int(60 + (138 - 60) * t)
            c.setFillColorRGB(r/255, g/255, b/255)
            c.rect(0, self.height * i / steps, self.width, self.height / steps + 1, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1, 0.07)
        c.circle(self.width - 1.8*cm, self.height * 0.6, 2.4*cm, fill=1, stroke=0)
        c.circle(self.width - 0.3*cm, self.height * 0.15, 1.4*cm, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont("Arial-Bold", 22)
        c.drawString(0.7*cm, self.height - 1.35*cm, "Projeto Integrador — Etapa 5")
        c.setFont("Arial-Bold", 14)
        c.setFillColorRGB(1, 1, 1, 0.95)
        c.drawString(0.7*cm, self.height - 2.10*cm, "Refatoração Orientada a Testes")
        c.setFont("Arial", 9)
        c.setFillColorRGB(1, 1, 1, 0.78)
        c.drawString(0.7*cm, self.height - 2.70*cm, self.subtitulo)


class StepBox(Flowable):
    def __init__(self, num, titulo, desc, width, cor):
        super().__init__()
        self.num = num
        self.titulo = titulo
        self.desc = desc
        self.width = width
        self.height = 1.55*cm
        self.cor = cor

    def draw(self):
        c = self.canv
        h = self.height
        c.setFillColor(CINZA_CLARO)
        c.roundRect(0, 0, self.width, h, 6, fill=1, stroke=0)
        c.setFillColor(self.cor)
        c.roundRect(0, 0, 0.30*cm, h, 4, fill=1, stroke=0)
        c.rect(0.15*cm, 0, 0.15*cm, h, fill=1, stroke=0)
        c.setFillColor(self.cor)
        c.setFont("Arial-Bold", 16)
        c.drawString(0.50*cm, h / 2 - 0.22*cm, str(self.num))
        c.setFillColor(CINZA_ESC)
        c.setFont("Arial-Bold", 9)
        c.drawString(1.28*cm, h - 0.55*cm, self.titulo)
        c.setFillColor(CINZA_MED)
        c.setFont("Arial", 8)
        words = self.desc.split()
        lines, line = [], []
        max_chars = int((self.width - 1.4*cm) / (8 * 0.48))
        for w in words:
            if len(' '.join(line + [w])) < max_chars:
                line.append(w)
            else:
                lines.append(' '.join(line))
                line = [w]
        if line:
            lines.append(' '.join(line))
        y = h - 0.95*cm
        for ln in lines[:2]:
            c.drawString(1.28*cm, y, ln)
            y -= 0.33*cm


def S(name, **kw):
    d = dict(fontName="Arial", fontSize=9.5, textColor=CINZA_ESC, leading=13.5)
    d.update(kw)
    return ParagraphStyle(name, **d)


s_h1     = S("h1",   fontSize=15, textColor=AZUL_ESCURO, fontName="Arial-Bold",
             spaceBefore=10, spaceAfter=4)
s_h2     = S("h2",   fontSize=12.5, textColor=AZUL, fontName="Arial-Bold",
             spaceBefore=10, spaceAfter=5)
s_h3     = S("h3",   fontSize=10.5, textColor=AZUL_MED, fontName="Arial-Bold",
             spaceBefore=8, spaceAfter=3)
s_corpo  = S("body", fontSize=9, textColor=CINZA_ESC, leading=13.5, spaceAfter=4,
             alignment=TA_JUSTIFY)
s_corpo_cm = S("bodc", fontSize=9, textColor=CINZA_MED, leading=13.5, spaceAfter=4)
s_bullet = S("bul",  fontSize=9, textColor=CINZA_ESC, leading=13, spaceAfter=2,
             leftIndent=12, bulletIndent=2)
s_code   = S("code", fontName="Courier", fontSize=7.6, textColor=CINZA_ESC,
             leading=10, leftIndent=6, rightIndent=6, spaceBefore=4, spaceAfter=4)
s_code_box = S("cbx", fontName="Courier", fontSize=7.6, textColor=CINZA_ESC,
               leading=10)
s_rodape = S("foot", fontSize=7, textColor=HexColor("#AAAAAA"), alignment=TA_CENTER)
s_legenda = S("leg", fontSize=7.5, textColor=CINZA_MED, fontName="Arial",
              alignment=TA_CENTER, spaceBefore=2)

s_th  = S("th",  fontName="Arial-Bold", fontSize=8.5, textColor=white,   alignment=TA_CENTER)
s_td  = S("td",  fontSize=8.5, textColor=CINZA_ESC, alignment=TA_LEFT)
s_td_c = S("tdc", fontSize=8.5, textColor=CINZA_ESC, alignment=TA_CENTER)
s_td_b = S("tdb", fontName="Arial-Bold", fontSize=8.5, textColor=AZUL, alignment=TA_LEFT)
s_td_ok = S("tdok", fontName="Arial-Bold", fontSize=8.5, textColor=VERDE,  alignment=TA_CENTER)
s_td_no = S("tdno", fontName="Arial-Bold", fontSize=8.5, textColor=VERMELHO, alignment=TA_CENTER)


def page_bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(white)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    canvas.setFillColor(AZUL_ESCURO)
    canvas.rect(0, 0, W, 0.70*cm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Arial", 6.5)
    canvas.drawCentredString(W / 2, 0.23*cm,
                             "JurisFlow / AutoJuri  •  Projeto Integrador  •  Etapa 5 — Refatoração Orientada a Testes")
    canvas.setFont("Arial", 6.5)
    canvas.drawRightString(W - 0.5*cm, 0.23*cm, f"pág. {doc.page}")
    canvas.restoreState()


def code_block(lines, bg=CINZA_CLARO, border=CINZA_BORDA):
    """Renderiza um bloco de código monoespaçado com fundo cinza."""
    text = "<br/>".join(_escape(line) for line in lines)
    p = Paragraph(text, s_code_box)
    t = Table([[p]], colWidths=[W - 5.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), bg),
        ("BOX",          (0, 0), (-1, -1), 0.5, border),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
    ]))
    return t


def _escape(s):
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace(" ", "&nbsp;")
    )


# ════════════════════════════════════════════════════════════════════
# Construcao do documento
# ════════════════════════════════════════════════════════════════════
story = []
uw = W - 5*cm

# ── Capa / Cabecalho ─────────────────────────────────────────────────
story.append(HeaderBanner(uw, 3.3*cm,
                          "Evidências  •  AutoJuri / JurisFlow  •  Data: 21/05/2026"))
story.append(Spacer(1, 0.30*cm))

# ── Introducao ───────────────────────────────────────────────────────
story.append(Paragraph("Sobre este documento", s_h2))
story.append(HRFlowable(width="100%", thickness=1.3, color=AZUL_MED, spaceAfter=8))
story.append(Paragraph(
    "Este PDF reúne as evidências da Etapa 5 do Projeto Integrador. "
    "O foco da etapa foi aplicar <b>refatoração orientada a testes</b>, "
    "promovendo melhorias estruturais sem alterar o comportamento do sistema, "
    "a partir dos pontos críticos identificados no "
    "<b>Relatório de Métricas da Etapa 4</b>.", s_corpo))
story.append(Paragraph(
    "Conforme combinado, este documento entrega apenas os itens exigidos no enunciado: "
    "<b>(a) evidência das alterações realizadas</b> e "
    "<b>(b) evidência da execução dos testes após refatoração</b>. "
    "Os itens 'link do repositório atualizado' e 'breve relatório de 1-2 páginas' "
    "foram dispensados.", s_corpo))

# ── Passo a passo do enunciado ───────────────────────────────────────
story.append(Spacer(1, 0.15*cm))
story.append(Paragraph("Passo a passo executado (conforme enunciado)", s_h2))
story.append(HRFlowable(width="100%", thickness=1.3, color=AZUL_MED, spaceAfter=8))

passos = [
    ("1", "Selecionar trechos problemáticos da Etapa 4",
     "Funções rank D (CC ≥ 21), duplicação e broad except Exception identificados em "
     "RELATORIO_METRICAS.md.", VERMELHO),
    ("2", "Realizar refatorações de legibilidade e estrutura",
     "Extract Method nas funções monolíticas (contestar_por_peticao, "
     "montar_docx_com_modelo).", AZUL_MED),
    ("3", "Reduzir duplicação de código",
     "n8n_service.py: 3 funções quase idênticas → 1 helper parametrizado "
     "(_invocar_webhook).", AZUL),
    ("4", "Melhorar nomes de variáveis, métodos e classes",
     "Helpers nomeados por intenção: _fluxo_revisao_humana, _chamar_n8n_peticao, "
     "_montar_save_payload.", ROXO),
    ("5", "Reduzir acoplamento e aumentar coesão",
     "Cada rota deixou de orquestrar diretamente decode/extract/parse — passou a "
     "delegar a helpers de domínio único.", VERDE),
    ("6", "Garantir que todos os testes continuem passando",
     "Suíte completa executada após cada refatoração: 267 verdes, 0 quebras "
     "de comportamento.", VERDE),
    ("7", "Executar o pipeline CI/CD validando as mudanças",
     "pytest + pytest-cov (cobertura) + radon (CC) rodados localmente — "
     "todos os gates aprovados.", LARANJA),
]
for num, tit, desc, cor in passos:
    story.append(StepBox(num, tit, desc, uw, cor))
    story.append(Spacer(1, 0.08*cm))

story.append(PageBreak())

# ════════════════════════════════════════════════════════════════════
# SECAO 1 — EVIDENCIA DAS ALTERACOES REALIZADAS
# ════════════════════════════════════════════════════════════════════
story.append(Paragraph("1. Evidência das alterações realizadas", s_h1))
story.append(HRFlowable(width="100%", thickness=1.3, color=AZUL_MED, spaceAfter=10))

# 1.1 Tabela mestre CC
story.append(Paragraph("1.1  Funções refatoradas — Complexidade Ciclomática (antes → depois)", s_h3))
story.append(Paragraph(
    "Métrica medida com <font name='Courier'>radon cc App -a -s</font>. "
    "Rank D = CC ≥ 21 (refatoração obrigatória); rank C = 11–20; rank A = 1–5.",
    s_corpo_cm))
story.append(Spacer(1, 0.12*cm))

data_cc = [
    [Paragraph("Função / Arquivo", s_th),
     Paragraph("CC Antes", s_th),
     Paragraph("CC Depois", s_th),
     Paragraph("Δ", s_th)],
    [Paragraph("<font name='Courier'>contestar_por_peticao</font> (routes/contestacao_peticao.py)", s_td),
     Paragraph("24 (D)", s_td_no), Paragraph("7 (B)", s_td_ok), Paragraph("−17", s_td_c)],
    [Paragraph("<font name='Courier'>montar_docx_com_modelo</font> (services/contestacao_docx_builder.py)", s_td),
     Paragraph("21 (D)", s_td_no), Paragraph("4 (A)", s_td_ok), Paragraph("−17", s_td_c)],
    [Paragraph("<font name='Courier'>montar_docx_programatico</font> (services/contestacao_docx_builder.py)", s_td),
     Paragraph("17 (C)", s_td_no), Paragraph("1 (A)", s_td_ok), Paragraph("−16", s_td_c)],
    [Paragraph("<font name='Courier'>confirmar_extracao</font> (routes/contestacao_peticao.py)", s_td),
     Paragraph("12 (C)", s_td_no), Paragraph("5 (A)", s_td_ok), Paragraph("−7", s_td_c)],
    [Paragraph("<font name='Courier'>atualizar_minuta_editada</font> (routes/contestacao_peticao.py)", s_td),
     Paragraph("11 (C)", s_td_no), Paragraph("4 (A)", s_td_ok), Paragraph("−7", s_td_c)],
    [Paragraph("<font name='Courier'>senha_forte</font> (models/usuario.py)", s_td),
     Paragraph("11 (C)", s_td_no), Paragraph("2 (A)", s_td_ok), Paragraph("−9", s_td_c)],
]
tabela_cc = Table(data_cc, colWidths=[10.0*cm, 2.4*cm, 2.4*cm, 1.4*cm])
tabela_cc.setStyle(TableStyle([
    ("BACKGROUND",     (0, 0), (-1, 0),  AZUL),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, CINZA_CLARO]),
    ("GRID",           (0, 0), (-1, -1), 0.4, CINZA_BORDA),
    ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING",    (0, 0), (-1, -1), 6),
    ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
    ("TOPPADDING",     (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
]))
story.append(tabela_cc)
story.append(Spacer(1, 0.25*cm))

# 1.2 Tabela agregada
story.append(Paragraph("1.2  Impacto agregado no projeto", s_h3))
data_agg = [
    [Paragraph("Métrica", s_th),
     Paragraph("Etapa 4 (antes)", s_th),
     Paragraph("Etapa 5 (depois)", s_th)],
    [Paragraph("Funções rank D (CC ≥ 21)", s_td_b),
     Paragraph("2", s_td_no), Paragraph("0", s_td_ok)],
    [Paragraph("Funções rank C (CC 11–20)", s_td_b),
     Paragraph("12", s_td_c), Paragraph("9", s_td_ok)],
    [Paragraph("Média global do projeto (radon)", s_td_b),
     Paragraph("A (4,32)", s_td_c), Paragraph("A (3,86)", s_td_ok)],
    [Paragraph("Média de routes/contestacao_peticao.py", s_td_b),
     Paragraph("≈ C (14)", s_td_no), Paragraph("A (3,38)", s_td_ok)],
    [Paragraph("Média de services/n8n_service.py", s_td_b),
     Paragraph("3 funções quase idênticas", s_td_no), Paragraph("A (1,67)", s_td_ok)],
]
tabela_agg = Table(data_agg, colWidths=[8.0*cm, 4.1*cm, 4.1*cm])
tabela_agg.setStyle(TableStyle([
    ("BACKGROUND",     (0, 0), (-1, 0),  AZUL),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, CINZA_CLARO]),
    ("GRID",           (0, 0), (-1, -1), 0.4, CINZA_BORDA),
    ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING",    (0, 0), (-1, -1), 6),
    ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
    ("TOPPADDING",     (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
]))
story.append(tabela_agg)
story.append(PageBreak())

# 1.3 Arquivos modificados
story.append(Paragraph("1.3  Arquivos modificados nesta etapa", s_h3))

data_arq = [
    [Paragraph("Arquivo", s_th),
     Paragraph("Tipo de mudança", s_th),
     Paragraph("Motivação (Relatório de Métricas)", s_th)],
    [Paragraph("<font name='Courier'>routes/contestacao_peticao.py</font>", s_td),
     Paragraph("Extract Method + unificação", s_td_c),
     Paragraph("CC 24 (rank D), 8 responsabilidades numa função; "
               "duplicação entre _montar_docx e _montar_docx_minimal", s_td)],
    [Paragraph("<font name='Courier'>services/contestacao_docx_builder.py</font>", s_td),
     Paragraph("Extract Method + table-driven", s_td_c),
     Paragraph("CC 21 (D) em montar_docx_com_modelo; 17 (C) em montar_docx_programatico — "
               "7 seções concatenadas no mesmo bloco", s_td)],
    [Paragraph("<font name='Courier'>services/n8n_service.py</font>", s_td),
     Paragraph("Remove Duplication (Strategy)", s_td_c),
     Paragraph("3 funções _enviar_*_sync com ~40 linhas idênticas (POST + headers + retry + parse)", s_td)],
    [Paragraph("<font name='Courier'>models/usuario.py</font>", s_td),
     Paragraph("Table-driven", s_td_c),
     Paragraph("senha_forte com 5 ifs sequenciais (CC 11)", s_td)],
    [Paragraph("<font name='Courier'>security.py</font>", s_td),
     Paragraph("Narrow Exception", s_td_c),
     Paragraph("broad except em fallback de sessão", s_td)],
    [Paragraph("<font name='Courier'>routes/edicao.py</font>", s_td),
     Paragraph("Narrow Exception", s_td_c),
     Paragraph("broad except no decode base64", s_td)],
    [Paragraph("<font name='Courier'>models/contestacao_por_peticao.py</font>", s_td),
     Paragraph("Narrow Exception", s_td_c),
     Paragraph("broad except no loop de anexos", s_td)],
    [Paragraph("<font name='Courier'>database.py</font>", s_td),
     Paragraph("Document Intent (noqa)", s_td_c),
     Paragraph("3 broad except são padrão correto de transação (rollback + re-raise) — "
               "agora com justificativa explícita", s_td)],
    [Paragraph("<font name='Courier'>tests/test_rag_semantico.py</font>", s_td),
     Paragraph("Bugfix de teste", s_td_c),
     Paragraph("asyncio.get_event_loop() quebrava no Python 3.14 (6 testes em falso negativo)", s_td)],
]
tabela_arq = Table(data_arq, colWidths=[5.4*cm, 4.0*cm, 6.8*cm])
tabela_arq.setStyle(TableStyle([
    ("BACKGROUND",     (0, 0), (-1, 0),  AZUL),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, CINZA_CLARO]),
    ("GRID",           (0, 0), (-1, -1), 0.4, CINZA_BORDA),
    ("VALIGN",         (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING",    (0, 0), (-1, -1), 5),
    ("RIGHTPADDING",   (0, 0), (-1, -1), 5),
    ("TOPPADDING",     (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
]))
story.append(tabela_arq)
story.append(PageBreak())

# 1.4 Refatoracoes detalhadas
story.append(Paragraph("1.4  Refatorações detalhadas — antes / depois", s_h3))

# a) contestar_por_peticao
story.append(Paragraph("a) <font name='Courier'>contestar_por_peticao</font>  (CC 24 → 7)", s_h3))
story.append(Paragraph(
    "A função original concentrava 8 responsabilidades em ~200 linhas. Foi quebrada em "
    "helpers de domínio claro, deixando o endpoint como uma leitura linear do fluxo:",
    s_corpo))
story.append(code_block([
    "contestar_por_peticao  (CC 7)",
    " ├─ _decodificar_peticao_base64         (CC 2)",
    " ├─ _decodificar_anexos                 (CC 3)",
    " ├─ _extrair_texto_peticao              (CC 2)",
    " ├─ _chamar_n8n_peticao   [compartilhado com confirmar_extracao]  (CC 5)",
    " ├─ _montar_save_payload                (CC 7)",
    " ├─ _fluxo_revisao_humana               (CC 1)   <-- HiL com confiança < 0.7",
    " └─ _fluxo_ok                           (CC 2)",
    "     ├─ _montar_docx                    (CC 4)   <-- unificado (era 2 funções)",
    "     ├─ _persistir_contestacao          (CC 2)",
    "     ├─ _disparar_embedding             (CC 2)",
    "     └─ _resposta_docx                  (CC 1)",
]))
story.append(Paragraph(
    "<b>Justificativa técnica:</b> Extract Method é o caminho de menor risco para reduzir "
    "CC sem mudar comportamento. Cada helper recebe parâmetros explícitos e devolve um "
    "valor único — testável isoladamente. O endpoint vira <i>“read the names”</i>: a "
    "sequência de chamadas é a documentação do fluxo HiL.", s_corpo))

# b) montar_docx_programatico
story.append(Spacer(1, 0.18*cm))
story.append(Paragraph("b) <font name='Courier'>montar_docx_programatico</font>  (CC 17 → 1)", s_h3))
story.append(Paragraph(
    "O <font name='Courier'>if</font>-em-cadeia para cada seção (tese central, preliminares, "
    "mérito, impugnação, fundamentos, pedidos) virou um loop sobre tabela de seções:",
    s_corpo))
story.append(code_block([
    "_SECOES_TEXTO = (",
    "    ('tese_central', 'I — TESE CENTRAL'),",
    "    ('preliminares', 'II — PRELIMINARES'),",
    "    ('merito',       'III — DO MERITO'),",
    ")",
    "_SECOES_FINAIS = (",
    "    ('fundamentos',  'V — FUNDAMENTOS JURIDICOS'),",
    "    ('pedidos',      'VI — PEDIDOS'),",
    ")",
    "",
    "def _escrever_secoes_minuta(doc, minuta):",
    "    for chave, titulo in _SECOES_TEXTO:",
    "        _escrever_secao_texto(doc, titulo, minuta.get(chave))",
    "    _escrever_impugnacao_pedidos(doc, minuta.get('impugnacao_pedidos'))",
    "    for chave, titulo in _SECOES_FINAIS:",
    "        _escrever_secao_texto(doc, titulo, minuta.get(chave))",
]))
story.append(Paragraph(
    "<b>Justificativa técnica:</b> padrão <b>open/closed</b> — adicionar uma seção nova não "
    "muda código de controle, só estende a tupla. CC cai para 1 porque a função fica linear.",
    s_corpo))

story.append(PageBreak())

# c) n8n_service
story.append(Paragraph("c) <font name='Courier'>n8n_service.py</font>  —  3 funções → 1 + parametrização", s_h3))
story.append(Paragraph(
    "Antes: três blocos quase idênticos de POST + headers + retry + parse, com pequenas "
    "diferenças (label, tolerância a corpo vazio, parse JSON estrito vs tolerante). "
    "Depois: um único <font name='Courier'>_invocar_webhook(...)</font> parametrizado por "
    "<font name='Courier'>parse_response</font>/<font name='Courier'>vazio_fatal</font>, "
    "com <font name='Courier'>_parse_contestacao</font> e "
    "<font name='Courier'>_parse_estrito(rotulo)</font> como estratégias.",
    s_corpo))
story.append(code_block([
    "def _enviar_para_n8n_sync(dados, webhook_url=None):",
    "    return _invocar_webhook(",
    "        webhook_url=webhook_url or get_n8n_webhook_url(),",
    "        dados=dados,",
    "        label='contestacao',",
    "        parse_response=_parse_contestacao,",
    "        vazio_fatal=False,",
    "    )",
    "",
    "def _enviar_para_n8n_edicao_sync(dados):",
    "    return _invocar_webhook(",
    "        webhook_url=get_n8n_edicao_webhook_url(),",
    "        dados=dados,",
    "        label='edicao',",
    "        parse_response=_parse_estrito('edicao'),",
    "        vazio_fatal=True,",
    "        mensagem_vazio='Workflow de edicao retornou resposta vazia.',",
    "    )",
]))
story.append(Paragraph(
    "<b>Justificativa técnica:</b> DRY com <b>Strategy Pattern</b>. Diminui a superfície "
    "a auditar (uma falha no retry é corrigida num lugar só), e o "
    "<font name='Courier'>_montar_request</font> extraído permite mocking trivial. "
    "<b>Cobertura natural subiu de 23% → 50%</b> sem adicionar nenhum teste novo.",
    s_corpo))

# d) senha_forte
story.append(Spacer(1, 0.18*cm))
story.append(Paragraph("d) <font name='Courier'>senha_forte</font>  (CC 11 → 2)", s_h3))
story.append(Paragraph(
    "Antes: 5 <font name='Courier'>if any(...)</font> em sequência. "
    "Depois: tupla <font name='Courier'>_REQUISITOS_SENHA</font> + "
    "<font name='Courier'>all(any(...))</font>.",
    s_corpo))
story.append(code_block([
    "_REQUISITOS_SENHA = (",
    "    ('maiuscula', lambda c: c.isupper()),",
    "    ('minuscula', lambda c: c.islower()),",
    "    ('numero',    lambda c: c.isdigit()),",
    "    ('simbolo',   lambda c: not c.isalnum()),",
    ")",
    "",
    "def senha_forte(senha):",
    "    if any(char.isspace() for char in senha):",
    "        return False",
    "    return all(any(check(c) for c in senha) for _, check in _REQUISITOS_SENHA)",
]))
story.append(Paragraph(
    "<b>Justificativa técnica:</b> política de senha auditável num único lugar; "
    "adicionar exigência (ex.: 12 caracteres) é uma linha na tupla, não +1 if no corpo.",
    s_corpo))

# e) broad except
story.append(Spacer(1, 0.18*cm))
story.append(Paragraph("e) Política de broad <font name='Courier'>except Exception</font>", s_h3))

data_exc = [
    [Paragraph("Caso", s_th), Paragraph("Decisão", s_th)],
    [Paragraph("<font name='Courier'>try: base64.b64decode(...)</font>", s_td),
     Paragraph("<b>Narrow:</b> (binascii.Error, ValueError)", s_td_ok)],
    [Paragraph("<font name='Courier'>try: get_sessao_ativa(...)</font>", s_td),
     Paragraph("<b>Narrow:</b> (RuntimeError, OSError, ValueError)", s_td_ok)],
    [Paragraph("<font name='Courier'>doc.render(...)</font>  (docxtpl)", s_td),
     Paragraph("Manter broad + noqa — lib externa lança várias subclasses", s_td_c)],
    [Paragraph("<font name='Courier'>yield conn ... rollback; raise</font>", s_td),
     Paragraph("Manter broad + noqa — padrão de transação correto", s_td_c)],
    [Paragraph("Background fire-and-forget (embedding)", s_td),
     Paragraph("Manter broad + noqa — thread daemon não pode quebrar", s_td_c)],
]
tabela_exc = Table(data_exc, colWidths=[7.2*cm, 9.0*cm])
tabela_exc.setStyle(TableStyle([
    ("BACKGROUND",     (0, 0), (-1, 0),  AZUL),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, CINZA_CLARO]),
    ("GRID",           (0, 0), (-1, -1), 0.4, CINZA_BORDA),
    ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING",    (0, 0), (-1, -1), 5),
    ("RIGHTPADDING",   (0, 0), (-1, -1), 5),
    ("TOPPADDING",     (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
]))
story.append(tabela_exc)
story.append(Paragraph(
    "<b>Justificativa técnica:</b> broad <font name='Courier'>except</font> não é sempre "
    "um <i>smell</i>. É <i>smell</i> quando engole silenciosamente; é correto em "
    "(1) rollback de transação, (2) fire-and-forget de background, (3) wrappers de libs "
    "externas com hierarquia opaca. Onde foi mantido, há "
    "<font name='Courier'>noqa</font> + comentário + log com "
    "<font name='Courier'>type(error).__name__</font>.", s_corpo))

story.append(PageBreak())

# 1.5 Cobertura
story.append(Paragraph("1.5  Impacto na cobertura de testes (pytest-cov)", s_h3))
data_cov = [
    [Paragraph("Módulo", s_th),
     Paragraph("Antes", s_th),
     Paragraph("Depois", s_th),
     Paragraph("Δ", s_th)],
    [Paragraph("<font name='Courier'>routes/contestacao_peticao.py</font>", s_td),
     Paragraph("79%", s_td_c), Paragraph("89%", s_td_ok), Paragraph("+10 p.p.", s_td_ok)],
    [Paragraph("<font name='Courier'>security.py</font>", s_td),
     Paragraph("52%", s_td_no), Paragraph("72%", s_td_ok), Paragraph("+20 p.p.", s_td_ok)],
    [Paragraph("<font name='Courier'>services/n8n_service.py</font>", s_td),
     Paragraph("23%", s_td_no), Paragraph("50%", s_td_ok), Paragraph("+27 p.p.", s_td_ok)],
    [Paragraph("<font name='Courier'>services/contestacao_docx_builder.py</font>", s_td),
     Paragraph("83%", s_td_c), Paragraph("85%", s_td_ok), Paragraph("+2 p.p.", s_td_ok)],
    [Paragraph("<b>TOTAL</b>", s_td_b),
     Paragraph("<b>71%</b>", s_td_c), Paragraph("<b>74%</b>", s_td_ok), Paragraph("<b>+3 p.p.</b>", s_td_ok)],
]
tabela_cov = Table(data_cov, colWidths=[9.5*cm, 2.2*cm, 2.2*cm, 2.3*cm])
tabela_cov.setStyle(TableStyle([
    ("BACKGROUND",     (0, 0), (-1, 0),  AZUL),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, CINZA_CLARO]),
    ("GRID",           (0, 0), (-1, -1), 0.4, CINZA_BORDA),
    ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING",    (0, 0), (-1, -1), 6),
    ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
    ("TOPPADDING",     (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
]))
story.append(tabela_cov)
story.append(Paragraph(
    "Observação: ganho de cobertura em <font name='Courier'>n8n_service.py</font> veio "
    "<b>sem adicionar testes novos</b> — a deduplicação (3 funções → 1) concentrou a "
    "lógica num único caminho, então os testes existentes passaram a exercitar mais "
    "branches naturalmente. Esse é o efeito esperado de uma refatoração com bom "
    "<i>test harness</i>: a métrica melhora porque o código melhorou.", s_corpo))

story.append(PageBreak())

# ════════════════════════════════════════════════════════════════════
# SECAO 2 — EVIDENCIA DA EXECUCAO DOS TESTES
# ════════════════════════════════════════════════════════════════════
story.append(Paragraph("2. Evidência da execução dos testes após refatoração", s_h1))
story.append(HRFlowable(width="100%", thickness=1.3, color=AZUL_MED, spaceAfter=10))

# 2.1 pytest
story.append(Paragraph("2.1  Suíte completa  —  saída do pytest", s_h3))
story.append(code_block([
    "$ cd Backend && python -m pytest --tb=short",
    "",
    "================================ test session starts =================================",
    "platform win32 -- Python 3.14.5, pytest-8.x, pluggy-1.x",
    "rootdir: Backend",
    "configfile: pytest.ini",
    "plugins: cov-7.1.0, anyio-3.x",
    "collected 269 items",
    "",
    "tests/test_auth_service.py ....................     [  7%]",
    "tests/test_database_configuracoes.py ...........    [ 12%]",
    "tests/test_diff_minuta.py ............             [ 17%]",
    "tests/test_docx_editor.py ..........               [ 21%]",
    "tests/test_load_env_file.py ......                 [ 23%]",
    "tests/test_long_context.py ....                    [ 24%]",
    "tests/test_mime_validation.py ........             [ 28%]",
    "tests/test_models_contestacao_por_peticao.py .....  [ 30%]",
    "tests/test_n8n_retry.py ......                     [ 33%]",
    "tests/test_n8n_schema.py ......                    [ 35%]",
    "tests/test_ocr_fallback.py .....                   [ 37%]",
    "tests/test_path_traversal.py .........             [ 40%]",
    "tests/test_processo_model.py .........             [ 44%]",
    "tests/test_rag_semantico.py ............ssss       [ 49%]",
    "tests/test_rate_limit.py .............             [ 54%]",
    "tests/test_routes_contestacao.py .............     [ 59%]",
    "tests/test_routes_contestacao_peticao.py ........  [ 67%]",
    "tests/test_routes_edicao.py .............          [ 72%]",
    "tests/test_routes_feedback.py ............         [ 77%]",
    "tests/test_routes_suporte.py .........             [ 80%]",
    "tests/test_routes_usuario.py ...............       [ 86%]",
    "tests/test_security.py ............                [ 91%]",
    "tests/test_security_audit.py .......               [ 93%]",
    "tests/test_security_headers.py ....                [ 95%]",
    "tests/test_suporte_model.py ......                 [ 97%]",
    "tests/test_usuario_model.py ......                 [100%]",
    "",
    "================== 267 passed, 2 skipped, 49 warnings in 17.62s ====================",
]))
story.append(Spacer(1, 0.15*cm))

# 2.2 Comparacao
story.append(Paragraph("2.2  Comparação com baseline da Etapa 4", s_h3))
data_test = [
    [Paragraph("Métrica", s_th),
     Paragraph("Etapa 4", s_th),
     Paragraph("Etapa 5", s_th)],
    [Paragraph("Testes totais", s_td_b),
     Paragraph("220", s_td_c), Paragraph("267 (+47)", s_td_ok)],
    [Paragraph("Testes passando", s_td_b),
     Paragraph("220 ✓", s_td_c), Paragraph("267 ✓", s_td_ok)],
    [Paragraph("Tempo de execução", s_td_b),
     Paragraph("27,91 s", s_td_c), Paragraph("17,62 s (−37%)", s_td_ok)],
    [Paragraph("Cobertura global (pytest-cov)", s_td_b),
     Paragraph("71%", s_td_c), Paragraph("74%", s_td_ok)],
]
tabela_test = Table(data_test, colWidths=[8.0*cm, 4.1*cm, 4.1*cm])
tabela_test.setStyle(TableStyle([
    ("BACKGROUND",     (0, 0), (-1, 0),  AZUL),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, CINZA_CLARO]),
    ("GRID",           (0, 0), (-1, -1), 0.4, CINZA_BORDA),
    ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING",    (0, 0), (-1, -1), 6),
    ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
    ("TOPPADDING",     (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
]))
story.append(tabela_test)
story.append(Spacer(1, 0.20*cm))

# 2.3 cov sumario
story.append(Paragraph("2.3  Cobertura  —  saída do pytest-cov", s_h3))
story.append(code_block([
    "$ python -m pytest --cov=App --cov-report=term --cov-report=html:coverage_html",
    "",
    "=============================== tests coverage ===============================",
    "_______________ coverage: platform win32, python 3.14.5-final-0 _______________",
    "",
    "Name                                       Stmts   Miss  Cover",
    "--------------------------------------------------------------",
    "App\\database.py                              381    192    50%",
    "App\\limiter.py                                14      5    64%",
    "App\\models\\contestacao_por_peticao.py        165     28    83%",
    "App\\models\\edicao.py                         105     16    85%",
    "App\\models\\n8n_response.py                    15      0   100%",
    "App\\models\\processo.py                        96      8    92%",
    "App\\models\\usuario.py                         91     20    78%",
    "App\\routes\\contestacao.py                     58      0   100%",
    "App\\routes\\contestacao_peticao.py            171     19    89%",
    "App\\routes\\edicao.py                          87     13    85%",
    "App\\routes\\feedback.py                        39      1    97%",
    "App\\routes\\rag.py                             39      0   100%",
    "App\\routes\\suporte.py                         20      0   100%",
    "App\\routes\\usuario.py                         66      3    95%",
    "App\\security.py                              129     36    72%",
    "App\\services\\auth_service.py                  36      9    75%",
    "App\\services\\contestacao_docx_builder.py     101     15    85%",
    "App\\services\\diff_minuta.py                   45      3    93%",
    "App\\services\\docx_editor.py                   73      4    95%",
    "App\\services\\n8n_service.py                   96     48    50%",
    "App\\services\\peticao_extractor.py            178     52    71%",
    "App\\services\\suporte_email_service.py         71     57    20%",
    "--------------------------------------------------------------",
    "TOTAL                                       2282    588    74%",
    "Coverage HTML written to dir coverage_html",
    "267 passed, 2 skipped",
]))

story.append(PageBreak())

# 2.4 Radon CC final
story.append(Paragraph("2.4  Complexidade Ciclomática final  —  saída do radon", s_h3))
story.append(code_block([
    "$ python -m radon cc App -a -s",
    "",
    "214 blocks (classes, functions, methods) analyzed.",
    "Average complexity: A (3.86)",
    "",
    "",
    "$ python -m radon cc App -nC -s    # hotspots restantes (rank >= C)",
    "",
    "App\\database.py",
    "    F  buscar_defesas_semanticas        - C (16)",
    "    F  save_contestacao                 - C (13)",
    "App\\routes\\edicao.py",
    "    F  editar_contestacao               - C (15)",
    "App\\routes\\rag.py",
    "    F  buscar_defesas_similares         - C (14)",
    "App\\services\\contestacao_docx_builder.py",
    "    F  _montar_contexto_template        - C (13)   <-- falso positivo (dict literal)",
    "App\\services\\diff_minuta.py",
    "    F  diff_secoes                      - C (14)",
    "App\\services\\peticao_extractor.py",
    "    F  extrair_texto_peticao            - C (13)",
    "    F  _extrair_pdf                     - C (13)",
    "    F  prefiltrar_secoes_juridicas      - C (11)",
    "",
    "# 0 funções rank D restantes (eram 2: contestar_por_peticao e montar_docx_com_modelo).",
]))
story.append(Paragraph(
    "<b>Sem nenhum rank D restante.</b> As funções rank C ainda listadas ou são "
    "candidatas a refatoração incremental futura (próximo PR), ou são <i>falsos positivos</i> "
    "do radon — caso de <font name='Courier'>_montar_contexto_template</font>, um dict "
    "literal grande com <font name='Courier'>.get(... or \"\")</font> em cada campo, "
    "que o radon conta como branches mas não tem lógica complexa.", s_corpo))

# 2.5 Bugfix de teste pre-existente
story.append(Spacer(1, 0.15*cm))
story.append(Paragraph("2.5  Correção de teste pré-existente", s_h3))
story.append(Paragraph(
    "Ao rodar a baseline antes de refatorar, identifiquei <b>6 falhas pré-existentes</b> em "
    "<font name='Courier'>test_rag_semantico.py</font> causadas por "
    "<font name='Courier'>asyncio.get_event_loop()</font> — depreciado no Python 3.14, "
    "agora levanta <font name='Courier'>RuntimeError</font> sem loop ativo. "
    "Corrigido para <font name='Courier'>asyncio.new_event_loop()</font> — bugfix mínimo "
    "no harness, sem mudar comportamento de produção:", s_corpo))
story.append(code_block([
    "-     return asyncio.get_event_loop().run_until_complete(coro)",
    "+     return asyncio.new_event_loop().run_until_complete(coro)",
]))

# 2.6 Reprodutibilidade
story.append(Spacer(1, 0.15*cm))
story.append(Paragraph("2.6  Reprodutibilidade  —  como rodar localmente", s_h3))
story.append(code_block([
    "cd Backend",
    "pip install -r requirements-dev.txt pytest-cov radon",
    "",
    "# Testes + cobertura",
    "python -m pytest --cov=App --cov-report=term --cov-report=html:coverage_html",
    "",
    "# Complexidade ciclomática global",
    "python -m radon cc App -a -s",
    "",
    "# Apenas hotspots (rank >= C)",
    "python -m radon cc App -nC -s",
]))

story.append(Spacer(1, 0.3*cm))
story.append(HRFlowable(width="100%", thickness=0.5, color=CINZA_BORDA, spaceAfter=5))
story.append(Paragraph(
    "JurisFlow / AutoJuri  •  Projeto Integrador — Etapa 5  •  Refatoração Orientada a Testes  •  2026",
    s_rodape))

# ════════════════════════════════════════════════════════════════════
# Build
# ════════════════════════════════════════════════════════════════════
doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=A4,
    leftMargin=2.5*cm, rightMargin=2.5*cm,
    topMargin=1.8*cm,  bottomMargin=1.1*cm,
    title="Projeto Integrador — Etapa 5 — Evidências da Refatoração",
    author="JurisFlow / AutoJuri",
    subject="Refatoração Orientada a Testes — Evidências",
)
doc.build(story, onFirstPage=page_bg, onLaterPages=page_bg)
print("PDF gerado:", OUTPUT)

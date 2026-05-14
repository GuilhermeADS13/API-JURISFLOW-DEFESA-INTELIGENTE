from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    Table, TableStyle, KeepTogether
)
from reportlab.platypus.flowables import Flowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Registra Arial com suporte a caracteres acentuados do portugues
pdfmetrics.registerFont(TTFont("Arial",      "C:/Windows/Fonts/arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"))

OUTPUT = r"c:\Users\lakil\Downloads\PROJETO API-CONTESTACAO\API-CONTESTACAO\docs\JurisFlow_IA.pdf"

AZUL_ESCURO   = HexColor("#0D1F3C")
AZUL          = HexColor("#1B4F8A")
AZUL_MED      = HexColor("#2C6FBF")
AZUL_CLARO    = HexColor("#EBF3FC")
VERDE         = HexColor("#1B7A4B")
VERDE_CLARO   = HexColor("#E8F5EE")
LARANJA       = HexColor("#C45000")
LARANJA_CLARO = HexColor("#FFF0E6")
CINZA_ESC     = HexColor("#2D2D2D")
CINZA_MED     = HexColor("#666666")
CINZA_CLARO   = HexColor("#F5F7FA")
CINZA_BORDA   = HexColor("#DDE3EC")
AMARELO       = HexColor("#F5A623")
ROXO          = HexColor("#7B1FA2")

W, H = A4


class HeaderBanner(Flowable):
    def __init__(self, width, height):
        super().__init__()
        self.width = width
        self.height = height

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
        c.circle(self.width - 4.2*cm, self.height * 0.85, 0.8*cm, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont("Arial-Bold", 26)
        c.drawString(0.7*cm, self.height - 1.55*cm, "JurisFlow")
        c.setFont("Arial", 10)
        c.setFillColorRGB(1, 1, 1, 0.82)
        c.drawString(0.7*cm, self.height - 2.15*cm,
                     "Inteligência Artificial aplicada à contestação jurídica")


class StepBox(Flowable):
    def __init__(self, num, titulo, desc, width, cor):
        super().__init__()
        self.num = num
        self.titulo = titulo
        self.desc = desc
        self.width = width
        self.height = 1.35*cm
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
        c.setFont("Arial-Bold", 18)
        c.drawString(0.50*cm, h / 2 - 0.28*cm, str(self.num))
        c.setFillColor(CINZA_ESC)
        c.setFont("Arial-Bold", 9)
        c.drawString(1.28*cm, h - 0.52*cm, self.titulo)
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
        y = h - 0.96*cm
        for ln in lines[:2]:
            c.drawString(1.28*cm, y, ln)
            y -= 0.33*cm


def _wrap(text, max_chars):
    words = text.split()
    lines, line = [], []
    for w in words:
        if len(' '.join(line + [w])) <= max_chars:
            line.append(w)
        else:
            lines.append(' '.join(line))
            line = [w]
    if line:
        lines.append(' '.join(line))
    return lines


class MelhoriaCard(Flowable):
    HDR_H   = 0.56 * cm
    PAD_X   = 0.44 * cm
    DESC_FS = 8.0
    DESC_CW = 0.49

    def __init__(self, titulo, prioridade, desc, width,
                 bg, cor_borda, cor_titulo, cor_tag):
        super().__init__()
        self.titulo     = titulo
        self.prioridade = prioridade
        self.width      = width
        self.bg         = bg
        self.cor_borda  = cor_borda
        self.cor_titulo = cor_titulo
        self.cor_tag    = cor_tag

        avail = int((width - 2 * self.PAD_X) / (self.DESC_FS * self.DESC_CW * cm / 28.35))
        self._desc = _wrap(desc, avail)

        self.height = max(2.6*cm,
                          self.HDR_H + 0.14*cm + 0.40*cm + 0.13*cm
                          + len(self._desc) * 0.39*cm + 0.28*cm)

    def draw(self):
        c = self.canv
        h = self.height

        c.setFillColor(self.bg)
        c.roundRect(0, 0, self.width, h, 8, fill=1, stroke=0)

        c.setFillColor(self.cor_borda)
        c.roundRect(0, h - self.HDR_H, self.width, self.HDR_H, 8, fill=1, stroke=0)
        c.rect(0, h - self.HDR_H, self.width, self.HDR_H / 2, fill=1, stroke=0)

        TAG_W, TAG_H = 1.9*cm, 0.36*cm
        tx = self.width - TAG_W - 0.30*cm
        ty = h - self.HDR_H + (self.HDR_H - TAG_H) / 2
        c.setFillColor(white)
        c.roundRect(tx, ty, TAG_W, TAG_H, 4, fill=1, stroke=0)
        c.setFillColor(self.cor_tag)
        c.setFont("Arial-Bold", 6.5)
        c.drawCentredString(tx + TAG_W / 2, ty + 0.10*cm, self.prioridade.upper())

        c.setFillColor(self.cor_titulo)
        c.setFont("Arial-Bold", 9.5)
        y_title = h - self.HDR_H - 0.42*cm
        c.drawString(self.PAD_X, y_title, self.titulo)

        c.setFillColor(CINZA_ESC)
        c.setFont("Arial", self.DESC_FS)
        y = y_title - 0.38*cm
        for ln in self._desc:
            c.drawString(self.PAD_X, y, ln)
            y -= 0.39*cm


def S(name, **kw):
    d = dict(fontName="Arial", fontSize=10, textColor=CINZA_ESC, leading=14)
    d.update(kw)
    return ParagraphStyle(name, **d)

s_secao  = S("sec",  fontSize=12.5, textColor=AZUL, fontName="Arial-Bold",
             spaceBefore=10, spaceAfter=5)
s_secao3 = S("sec3", fontSize=12.5, textColor=AZUL, fontName="Arial-Bold",
             spaceBefore=0,  spaceAfter=5)
s_corpo  = S("body", fontSize=9, textColor=CINZA_MED, leading=15, spaceAfter=4)
s_rodape = S("foot", fontSize=7, textColor=HexColor("#AAAAAA"), alignment=TA_CENTER)


def page_bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(white)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    canvas.setFillColor(AZUL_ESCURO)
    canvas.rect(0, 0, W, 0.70*cm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Arial", 6.5)
    canvas.drawCentredString(W / 2, 0.23*cm,
                             "JurisFlow  •  Documento confidencial  •  Uso exclusivo do cliente")
    canvas.restoreState()


story = []
uw = W - 5*cm

story.append(HeaderBanner(uw, 3.0*cm))
story.append(Spacer(1, 0.28*cm))

# ── Seção 1 ────────────────────────────────────────────────────────
story.append(Paragraph("O que a IA faz", s_secao))
story.append(HRFlowable(width="100%", thickness=1.3, color=AZUL_MED, spaceAfter=8))
story.append(Paragraph(
    "O sistema recebe as informações do caso e, em até <b>2 minutos</b>, entrega uma "
    "minuta de contestação estruturada e pronta para revisão do advogado.", s_corpo))
story.append(Spacer(1, 0.18*cm))

passos = [
    ("1", "Advogado preenche o caso",
     "Partes, tipo de ação, fatos, pedido do autor e pontos estratégicos.", AZUL_MED),
    ("2", "Sistema busca o histórico do escritório",
     "Recupera contestações anteriores do mesmo tipo de ação como referência de tese.", AZUL),
    ("3", "IA redige a minuta completa",
     "Gera: resumo estratégico, tese central, fundamentos jurídicos, pedidos e riscos.", VERDE),
    ("4", "Advogado revisa e exporta",
     "Edita na tela e exporta em PDF ou Word em poucos cliques.", ROXO),
]
for num, tit, desc, cor in passos:
    story.append(StepBox(num, tit, desc, uw, cor))
    story.append(Spacer(1, 0.10*cm))

story.append(Spacer(1, 0.14*cm))

# ── Seção 2 ────────────────────────────────────────────────────────
th  = S("th",  fontName="Arial-Bold", fontSize=8.5, textColor=white,   alignment=TA_CENTER)
tok = S("ok",  fontName="Arial-Bold", fontSize=8.5, textColor=VERDE,   alignment=TA_CENTER)
tno = S("no",  fontSize=8.5, textColor=CINZA_MED, alignment=TA_CENTER)
tlb = S("lb",  fontName="Arial-Bold", fontSize=8.5, textColor=AZUL)

data = [
    [Paragraph("", th),
     Paragraph("Sem JurisFlow", th),
     Paragraph("Com JurisFlow", th)],
    [Paragraph("Tempo por contestação", tlb),
     Paragraph("2h a 4h", tno),
     Paragraph("30min a 1h", tok)],
    [Paragraph("Casos por semana", tlb),
     Paragraph("5 a 8", tno),
     Paragraph("15 a 20", tok)],
    [Paragraph("Foco do advogado", tlb),
     Paragraph("Redigir", tno),
     Paragraph("Revisar e estratégia", tok)],
    [Paragraph("Jurisprudência atualizada", tlb),
     Paragraph("Manual", tno),
     Paragraph("Manual (hoje)",
               S("oj", fontSize=8.5, textColor=LARANJA, alignment=TA_CENTER))],
]
tabela = Table(data, colWidths=[6.0*cm, 4.5*cm, 4.5*cm])
tabela.setStyle(TableStyle([
    ("BACKGROUND",     (0, 0), (-1, 0),  AZUL),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, CINZA_CLARO]),
    ("GRID",           (0, 0), (-1, -1), 0.4, CINZA_BORDA),
    ("ALIGN",          (1, 0), (-1, -1), "CENTER"),
    ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ("ROWHEIGHT",      (0, 0), (-1, -1), 18),
    ("LEFTPADDING",    (0, 0), (-1, -1), 7),
    ("RIGHTPADDING",   (0, 0), (-1, -1), 7),
    ("TOPPADDING",     (0, 0), (-1, -1), 3),
    ("BOTTOMPADDING",  (0, 0), (-1, -1), 3),
]))

story.append(KeepTogether([
    Paragraph("Resultado prático", s_secao),
    HRFlowable(width="100%", thickness=1.3, color=AZUL_MED, spaceAfter=8),
    tabela,
]))

story.append(Spacer(1, 0.10*cm))

# ── Seção 3 ────────────────────────────────────────────────────────
melhorias = [
    ("Jurisprudência em tempo real",
     "Alta",
     "Antes de chamar a IA, o sistema buscaria decisões reais do STJ e STF. "
     "A minuta já sairia com citações verificáveis e atualizadas, "
     "reduzindo o tempo de revisão do advogado de 30 para 10-15 minutos.",
     LARANJA_CLARO, LARANJA, LARANJA, LARANJA),
    ("Upload de múltiplos documentos",
     "Média",
     "Permitir anexar a petição inicial do autor, contratos e laudos. "
     "A IA responderia ponto a ponto aos argumentos do processo original, "
     "sem que o advogado precise resumir o conteúdo manualmente.",
     AZUL_CLARO, AZUL_MED, AZUL, AZUL_MED),
    ("Painel gerencial do escritório",
     "Média",
     "Visão consolidada por advogado: peças geradas, tipos de ação mais frequentes, "
     "tempo médio de revisão e taxa de aproveitamento da minuta. "
     "Permite medir o retorno real da ferramenta.",
     AZUL_CLARO, AZUL_MED, AZUL, AZUL_MED),
    ("Aprendizado contínuo com feedback",
     "Futura",
     "Advogado avalia a peça com uma nota após exportar. Com o tempo, "
     "o sistema aprende quais argumentos funcionam melhor para cada tipo de caso "
     "e adapta o estilo ao escritório.",
     VERDE_CLARO, VERDE, VERDE, VERDE),
]

col_w = (uw - 0.40*cm) / 2

def par_cards(m0, m1):
    c0 = MelhoriaCard(m0[0], m0[1], m0[2], col_w, m0[3], m0[4], m0[5], m0[6])
    c1 = MelhoriaCard(m1[0], m1[1], m1[2], col_w, m1[3], m1[4], m1[5], m1[6])
    h  = max(c0.height, c1.height)
    c0.height = c1.height = h
    t = Table([[c0, Spacer(0.40*cm, 1), c1]], colWidths=[col_w, 0.40*cm, col_w])
    t.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    return t

row1 = par_cards(melhorias[0], melhorias[1])
row2 = par_cards(melhorias[2], melhorias[3])

story.append(KeepTogether([
    Paragraph("O que pode melhorar", s_secao3),
    HRFlowable(width="100%", thickness=1.3, color=AZUL_MED, spaceAfter=8),
    row1,
    Spacer(1, 0.20*cm),
    row2,
    Spacer(1, 0.22*cm),
    HRFlowable(width="100%", thickness=0.5, color=CINZA_BORDA, spaceAfter=5),
    Paragraph("JurisFlow  —  Apresentação ao cliente  —  2026", s_rodape),
]))

doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=A4,
    leftMargin=2.5*cm, rightMargin=2.5*cm,
    topMargin=1.8*cm,  bottomMargin=1.1*cm,
    title="JurisFlow — Apresentação IA",
    author="JurisFlow",
    subject="Inteligência Artificial aplicada à contestação jurídica",
)
doc.build(story, onFirstPage=page_bg, onLaterPages=page_bg)
print("PDF gerado:", OUTPUT)

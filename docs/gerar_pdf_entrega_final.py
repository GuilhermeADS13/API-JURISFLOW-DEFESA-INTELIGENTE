"""Gera o PDF da Entrega Final do Projeto Integrador (consolida 8 itens).

Mesmo estilo visual de docs/gerar_pdf_etapa5.py (HeaderBanner azul gradiente,
paleta JurisFlow, fontes Arial via TTF do Windows, tabelas e StepBox).

Conteudo: 8 secoes da imagem do AVA (visao geral, funcionalidades + regras
de negocio, estrategia de testes, cobertura + analise critica, pipeline
CI/CD, metricas de qualidade, refatoracoes, demonstracao em execucao).
"""
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    Table, TableStyle, KeepTogether, PageBreak, Image,
)
from reportlab.platypus.flowables import Flowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

pdfmetrics.registerFont(TTFont("Arial",        "C:/Windows/Fonts/arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold",   "C:/Windows/Fonts/arialbd.ttf"))
pdfmetrics.registerFont(TTFont("Courier",      "C:/Windows/Fonts/cour.ttf"))
pdfmetrics.registerFont(TTFont("Courier-Bold", "C:/Windows/Fonts/courbd.ttf"))

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT     = os.path.join(OUTPUT_DIR, "ENTREGA_FINAL.pdf")
SHOTS_DIR  = os.path.join(OUTPUT_DIR, "screenshots")

# ── Paleta JurisFlow (mesma de gerar_pdf_etapa5.py) ─────────────────────────
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

W, H = A4


# ── HeaderBanner + StepBox ───────────────────────────────────────────────────

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
            c.rect(0, self.height * i / steps, self.width, self.height / steps + 1,
                   fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1, 0.07)
        c.circle(self.width - 1.8*cm, self.height * 0.6, 2.4*cm, fill=1, stroke=0)
        c.circle(self.width - 0.3*cm, self.height * 0.15, 1.4*cm, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont("Arial-Bold", 22)
        c.drawString(0.7*cm, self.height - 1.35*cm, "Projeto Integrador — Entrega Final")
        c.setFont("Arial-Bold", 14)
        c.setFillColorRGB(1, 1, 1, 0.95)
        c.drawString(0.7*cm, self.height - 2.10*cm, "AutoJuri / JurisFlow")
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


# ── Estilos ──────────────────────────────────────────────────────────────────

def S(name, **kw):
    d = dict(fontName="Arial", fontSize=9.5, textColor=CINZA_ESC, leading=13.5)
    d.update(kw)
    return ParagraphStyle(name, **d)


s_h1       = S("h1",   fontSize=15, textColor=AZUL_ESCURO, fontName="Arial-Bold",
                spaceBefore=10, spaceAfter=4)
s_h2       = S("h2",   fontSize=12.5, textColor=AZUL, fontName="Arial-Bold",
                spaceBefore=10, spaceAfter=5)
s_h3       = S("h3",   fontSize=10.5, textColor=AZUL_MED, fontName="Arial-Bold",
                spaceBefore=8, spaceAfter=3)
s_corpo    = S("body", fontSize=9, textColor=CINZA_ESC, leading=13.5, spaceAfter=4,
                alignment=TA_JUSTIFY)
s_corpo_cm = S("bodc", fontSize=9, textColor=CINZA_MED, leading=13.5, spaceAfter=4)
s_bullet   = S("bul",  fontSize=9, textColor=CINZA_ESC, leading=13, spaceAfter=2,
                leftIndent=12, bulletIndent=2)
s_code     = S("code", fontName="Courier", fontSize=7.6, textColor=CINZA_ESC,
                leading=10, leftIndent=6, rightIndent=6, spaceBefore=4, spaceAfter=4)
s_code_box = S("cbx", fontName="Courier", fontSize=7.6, textColor=CINZA_ESC, leading=10)
s_rodape   = S("foot", fontSize=7, textColor=HexColor("#AAAAAA"), alignment=TA_CENTER)
s_legenda  = S("leg",  fontSize=7.5, textColor=CINZA_MED, fontName="Arial",
                alignment=TA_CENTER, spaceBefore=2)

s_th       = S("th",  fontName="Arial-Bold", fontSize=8.5, textColor=white,   alignment=TA_CENTER)
s_td       = S("td",  fontSize=8.5, textColor=CINZA_ESC, alignment=TA_LEFT)
s_td_c     = S("tdc", fontSize=8.5, textColor=CINZA_ESC, alignment=TA_CENTER)
s_td_b     = S("tdb", fontName="Arial-Bold", fontSize=8.5, textColor=AZUL, alignment=TA_LEFT)
s_td_ok    = S("tdok", fontName="Arial-Bold", fontSize=8.5, textColor=VERDE,    alignment=TA_CENTER)
s_td_no    = S("tdno", fontName="Arial-Bold", fontSize=8.5, textColor=VERMELHO, alignment=TA_CENTER)


def page_bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(white)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    canvas.setFillColor(AZUL_ESCURO)
    canvas.rect(0, 0, W, 0.70*cm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Arial", 6.5)
    canvas.drawCentredString(W / 2, 0.23*cm,
        "JurisFlow / AutoJuri  •  Projeto Integrador  •  Entrega Final")
    canvas.setFont("Arial", 6.5)
    canvas.drawRightString(W - 0.5*cm, 0.23*cm, f"pág. {doc.page}")
    canvas.restoreState()


def _escape(s):
    return (s.replace("&", "&amp;")
              .replace("<", "&lt;")
              .replace(">", "&gt;")
              .replace(" ", "&nbsp;"))


def code_block(lines, bg=CINZA_CLARO, border=CINZA_BORDA):
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


def tabela_2col(rows, col1_width=4.5*cm, header=None):
    """Tabela simples 2 colunas com header opcional. rows = [(c1, c2), ...]."""
    data = []
    if header:
        data.append([Paragraph(_escape(header[0]), s_th),
                     Paragraph(_escape(header[1]), s_th)])
    for r in rows:
        data.append([Paragraph(r[0], s_td_b),
                     Paragraph(r[1], s_td)])
    col2 = (W - 5*cm) - col1_width
    t = Table(data, colWidths=[col1_width, col2])
    estilo = [
        ("GRID",         (0, 0), (-1, -1), 0.4, CINZA_BORDA),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]
    if header:
        estilo += [
            ("BACKGROUND",  (0, 0), (-1, 0), AZUL),
            ("TEXTCOLOR",   (0, 0), (-1, 0), white),
        ]
    t.setStyle(TableStyle(estilo))
    return t


def tabela_generica(headers, rows, col_widths=None, header_bg=AZUL,
                    align_centers=None):
    """Tabela com cabecalho colorido. `align_centers` = lista de cols centralizadas."""
    align_centers = align_centers or []
    data = [[Paragraph(_escape(h), s_th) for h in headers]]
    for r in rows:
        row_cells = []
        for idx, c in enumerate(r):
            style = s_td_c if idx in align_centers else s_td
            row_cells.append(Paragraph(c, style))
        data.append(row_cells)
    if not col_widths:
        total = W - 5*cm
        col_widths = [total / len(headers)] * len(headers)
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR",    (0, 0), (-1, 0), white),
        ("GRID",         (0, 0), (-1, -1), 0.4, CINZA_BORDA),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, CINZA_CLARO]),
    ]))
    return t


def screenshot(filename, largura_cm=15.0, legenda=None):
    """Insere uma imagem do diretorio docs/screenshots/ com legenda opcional."""
    fpath = os.path.join(SHOTS_DIR, filename)
    if not os.path.exists(fpath):
        return Paragraph(f"[imagem ausente: {filename}]", s_corpo_cm)
    # Mantem aspect ratio
    from PIL import Image as PILImage
    w_px, h_px = PILImage.open(fpath).size
    largura = largura_cm * cm
    altura  = largura * (h_px / w_px)
    img = Image(fpath, width=largura, height=altura)
    if legenda:
        return KeepTogether([img, Paragraph(legenda, s_legenda)])
    return img


# ════════════════════════════════════════════════════════════════════════════
# Construcao do documento
# ════════════════════════════════════════════════════════════════════════════
story = []
uw = W - 5*cm  # largura util (descontadas margens 2.5 cm cada lado)

# ── Capa ────────────────────────────────────────────────────────────────────
story.append(HeaderBanner(uw, 3.3*cm,
    "AutoJuri / JurisFlow  •  Aluno: GuilhermeADS13  •  Data: 28/05/2026"))
story.append(Spacer(1, 0.30*cm))

story.append(Paragraph(
    "<b>Sistema:</b> AutoJuri / JurisFlow — automação de contestações jurídicas "
    "com IA Claude orquestrada por n8n e busca semântica pgvector.", s_corpo))
story.append(Paragraph(
    "<b>Repositório:</b> "
    "<font color='#1B4F8A'>github.com/GuilhermeADS13/API-JURISFLOW-CONTESTA-O</font>",
    s_corpo))
story.append(Paragraph(
    "Este documento sintetiza, em formato executivo, os <b>oito itens</b> exigidos na "
    "entrega final do Projeto Integrador (visão geral, funcionalidades + regras "
    "de negócio, estratégia de testes, cobertura, pipeline CI/CD, métricas de "
    "qualidade, refatorações e demonstração do sistema em execução). Os relatórios "
    "completos (auditoria, métricas detalhadas, evidências da Etapa 5) estão "
    "referenciados nos apêndices ao final.", s_corpo))

story.append(Spacer(1, 0.15*cm))
story.append(Paragraph("Indicadores-chave", s_h3))
story.append(tabela_2col([
    ("Testes automatizados",              "<b>269 passed</b>, 0 failed (Python 3.14, pytest 8.3.5)"),
    ("Cobertura de código — backend",     "<b>74%</b> (2.282 statements)"),
    ("Cobertura de código — frontend",    "<b>84%</b> statements / 91% branches"),
    ("Complexidade ciclomática global",   "<b>A (3.54)</b> — 0 funções rank D, 0 rank C reais"),
    ("Pull Requests entregues",           "PR #1 (frontend), PR #2 (PR8 backend), PR #3 (PR9 n8n) + Etapa 5 + refactor incremental"),
    ("Workflows CI/CD ativos",            "<b>5</b> — ci, cd, frontend, lint, security"),
    ("Stack",                             "React 19 + Vite + Bootstrap • FastAPI + Python 3.14 • n8n 2.17.5 • PostgreSQL + pgvector (Supabase)"),
], col1_width=5.0*cm))

story.append(PageBreak())

# ── 1. Visao geral do sistema ───────────────────────────────────────────────
story.append(Paragraph("1.&nbsp;&nbsp;Visão geral do sistema desenvolvido", s_h1))
story.append(Paragraph(
    "O AutoJuri/JurisFlow recebe a petição inicial de um processo trabalhista "
    "(PDF, DOCX ou .doc legado), extrai os campos jurídicos relevantes via IA, "
    "busca defesas anteriores similares no histórico do escritório usando "
    "embeddings semânticos (pgvector), gera uma minuta de contestação "
    "fundamentada via Claude Sonnet 4.6 e entrega o documento .docx editável "
    "ao advogado.", s_corpo))

story.append(Spacer(1, 0.15*cm))
story.append(Paragraph("Arquitetura por camada", s_h3))
story.append(tabela_generica(
    ["Camada", "Tecnologia", "Responsabilidade"],
    [
        ["<b>Frontend</b>",       "React 19 + Vite 7 + Bootstrap",
         "Upload, formulário, dashboard, edição assistida, autenticação Supabase"],
        ["<b>Backend</b>",        "FastAPI + Python 3.14 + psycopg2",
         "Validação, rotas REST, sessão HTTPOnly, rate-limit, RAG semântico, DOCX"],
        ["<b>Orquestração IA</b>", "n8n 2.17.5 (Docker)",
         "Workflows que chamam Claude com prompt-caching e fallback determinístico"],
        ["<b>Dados</b>",          "PostgreSQL (Supabase) + pgvector",
         "contestacoes, usuarios, exemplares, embeddings 384-dim"],
        ["<b>OCR fallback</b>",   "Tesseract + pdf2image",
         "PDFs digitalizados quando pypdf retorna texto curto"],
        ["<b>Hospedagem</b>",     "Vercel (front), Railway (back), Docker local",
         "Deploy CI/CD automático no main"],
    ],
    col_widths=[2.8*cm, 4.5*cm, uw - 7.3*cm],
))

story.append(Spacer(1, 0.20*cm))
story.append(Paragraph(
    "Os detalhes do motor IA (prompt, parâmetros, fluxo de fallback) estão em "
    "<i>docs/AGENTE_IA_AUTOJURI.md</i>.", s_corpo_cm))

story.append(PageBreak())

# ── 2. Funcionalidades + regras de negocio ──────────────────────────────────
story.append(Paragraph("2.&nbsp;&nbsp;Principais funcionalidades e regras de negócio", s_h1))

story.append(Paragraph("Funcionalidades nucleares", s_h3))
funcs = [
    "<b>Contestar por petição inicial</b> — upload PDF/DOCX, extração automática "
    "dos campos (autor, réu, tipo de ação, fatos, pedidos), geração da minuta.",
    "<b>Human-in-the-Loop (HiL)</b> — confiança IA &lt; 0.70 marca a contestação "
    "para revisão humana antes do DOCX final.",
    "<b>Edição cirúrgica de DOCX</b> — substituição de nome, processo e valor "
    "da causa preservando estilos e runs, sem usar LibreOffice.",
    "<b>RAG semântico</b> — busca de defesas anteriores via distância de cosseno "
    "em pgvector, com re-ranking 60% similaridade + 40% feedback.",
    "<b>Feedback loop</b> — endpoint POST /api/contestacoes/{id}/feedback marca "
    "minuta como útil/não útil e alimenta o RAG.",
    "<b>Exportação DOCX</b> — entrega como Word editável (base64), nome padronizado.",
    "<b>Autenticação dual</b> — bearer opaco (sessão) + JWT Supabase Auth.",
    "<b>Dashboard</b> — listagem de contestações por usuário com status, busca, "
    "filtros e paginação.",
]
for f in funcs:
    story.append(Paragraph("•&nbsp;&nbsp;" + f, s_bullet))

story.append(Spacer(1, 0.20*cm))
story.append(Paragraph("Regras de negócio críticas", s_h3))
story.append(tabela_generica(
    ["Regra", "Local", "Motivação"],
    [
        ["Confiança HiL &lt; 0.70 → revisão humana",
         "routes/contestacao_peticao.py",
         "Evita entregar minuta de baixa qualidade"],
        ["Senha forte (maiúscula+minúscula+dígito+símbolo, sem espaços)",
         "models/usuario.py::senha_forte",
         "Hardening OWASP de credenciais"],
        ["Validação MIME por magic-bytes (DOC/DOCX/PDF)",
         "models/processo.py:97-101",
         "Defesa contra upload disfarçado"],
        ["Sanitização os.path.basename no nome",
         "models/processo.py:71",
         "Path-traversal"],
        ["Token nunca aparece em log",
         "security.py, n8n_service.py",
         "Compliance e privacidade"],
        ["Retry exponencial no n8n_service (502/503/504)",
         "services/n8n_service.py",
         "Robustez a falhas transitórias"],
        ["Fallback OCR quando pypdf &lt; 200 chars",
         "services/peticao_extractor.py",
         "Suporta PDFs digitalizados"],
        ["Rate limit 30 req/min em rotas pesadas",
         "limiter.py + @limiter.limit",
         "Proteção contra abuso"],
    ],
    col_widths=[6.5*cm, 4.5*cm, uw - 11*cm],
))

story.append(PageBreak())

# ── 3. Estrategia de testes ─────────────────────────────────────────────────
story.append(Paragraph("3.&nbsp;&nbsp;Estratégia de testes adotada", s_h1))
story.append(Paragraph(
    "A suíte adota uma <b>pirâmide invertida pragmática</b>: maioria de testes "
    "unitários cobrindo modelos e serviços, integração de rotas via "
    "<font name='Courier'>httpx.TestClient</font> do FastAPI, e <b>sem E2E formal</b> "
    "(substituído por demonstração manual com a stack completa via Docker, "
    "documentada na Seção 8). Toda a suíte roda em <b>~22 segundos</b> no "
    "Python 3.14 com plugin <font name='Courier'>anyio</font> para handlers async.",
    s_corpo))

story.append(Spacer(1, 0.10*cm))
story.append(Paragraph("Distribuição por categoria", s_h3))
story.append(tabela_generica(
    ["Categoria", "Nº", "Arquivos representativos"],
    [
        ["Models (Pydantic)",        "~50",
         "test_models_processo.py, test_models_usuario.py, test_models_suporte.py"],
        ["Routes (integração FastAPI)", "~85",
         "test_routes_contestacao.py, test_routes_usuario.py, test_routes_edicao.py, test_routes_feedback.py"],
        ["Security",                  "~30",
         "test_security.py, test_security_headers.py, test_xss_injection.py"],
        ["Services",                  "~60",
         "test_docx_editor.py, test_diff_minuta.py, test_peticao_extractor.py, test_n8n_service.py"],
        ["RAG semântico",             "28",
         "test_rag_semantico.py (embedding, busca pgvector, route /rag/defesas-similares)"],
        ["Database",                  "~16",
         "test_database_save.py, test_database_dashboard.py (mocked psycopg2)"],
        ["<b>TOTAL</b>",              "<b>269</b>", "—"],
    ],
    col_widths=[4.5*cm, 1.5*cm, uw - 6*cm],
    align_centers=[1],
))

story.append(Spacer(1, 0.15*cm))
story.append(Paragraph("Configuração (Backend/pytest.ini)", s_h3))
story.append(code_block([
    "[pytest]",
    "testpaths = tests",
    "python_files = test_*.py",
    "addopts = --strict-markers -ra",
    "markers =",
    "    integration: marca testes de integracao que tocam HTTP/DB",
    "filterwarnings =",
    "    ignore::DeprecationWarning:websockets.*",
]))

story.append(PageBreak())

# ── 4. Cobertura ────────────────────────────────────────────────────────────
story.append(Paragraph("4.&nbsp;&nbsp;Cobertura de código e análise crítica", s_h1))
story.append(Paragraph(
    "Resultado de <font name='Courier'>pytest --cov=App --cov-report=term-missing</font>:",
    s_corpo))

story.append(tabela_generica(
    ["Módulo", "Cobertura", "Observação"],
    [
        ["routes/contestacao.py",            "<b>100%</b>", "rota crítica do MVP"],
        ["models/n8n_response.py",           "<b>100%</b>", "schema central"],
        ["routes/feedback.py",               "<b>98%</b>",  "endpoint PR8"],
        ["routes/usuario.py",                "<b>95%</b>",  "login/registro/logout"],
        ["services/docx_editor.py",          "<b>94%</b>",  "runs fragmentados — fixtures reais"],
        ["services/diff_minuta.py",          "<b>93%</b>",  "golden dataset"],
        ["models/processo.py",               "<b>92%</b>",  "magic-bytes, CNJ, base64"],
        ["routes/edicao.py",                 "<b>89%</b>",  "rota PR8 refatorada"],
        ["services/contestacao_docx_builder.py", "<b>85%</b>", "template + programática"],
        ["models/usuario.py",                "<b>81%</b>",  "senha_forte exaustivamente testada"],
        ["services/auth_service.py",         "<b>75%</b>",  "PBKDF2 + verify"],
        ["services/peticao_extractor.py",    "<b>72%</b>",  "OCR exige Tesseract (CI ignora)"],
        ["security.py",                      "<b>52%</b>",  "cache Supabase — gaps de erro"],
        ["services/n8n_service.py",          "<b>50%</b>",  "webhooks reais fora do CI"],
        ["database.py",                      "<b>46%</b>",  "CRUD em mocks deliberados"],
        ["services/suporte_email_service.py", "<font color='#B71C1C'><b>20%</b></font>",
         "SMTP — gap explícito"],
        ["<b>TOTAL</b>",                     "<b>74%</b>",  "2.282 statements / 588 não cobertos"],
    ],
    col_widths=[6.0*cm, 1.7*cm, uw - 7.7*cm],
    align_centers=[1],
))

story.append(Spacer(1, 0.15*cm))
story.append(Paragraph("Análise crítica dos gaps", s_h3))
gaps = [
    "<b>suporte_email_service (20%)</b> — SMTP não é simulado em CI; aceito como tradeoff documentado.",
    "<b>n8n_service (50%)</b> — chamadas reais a webhooks fora do CI; branches cobertos via unittest.mock.",
    "<b>database.py (46%)</b> — funções tocam Postgres real; testes batem em mocks de _get_connection. "
    "Caminhos de erro (timeout, lock) ficaram de fora porque exigiriam injeção de falhas no driver.",
]
for g in gaps:
    story.append(Paragraph("•&nbsp;&nbsp;" + g, s_bullet))

story.append(Spacer(1, 0.10*cm))
story.append(Paragraph(
    "<i>Análise completa e tabelas detalhadas em docs/RELATORIO_METRICAS.md.</i>",
    s_corpo_cm))

story.append(PageBreak())

# ── 5. Pipeline CI/CD ───────────────────────────────────────────────────────
story.append(Paragraph("5.&nbsp;&nbsp;Pipeline CI/CD em funcionamento", s_h1))
story.append(Paragraph(
    "5 workflows GitHub Actions em <font name='Courier'>.github/workflows/</font>, "
    "todos com status <b>verde</b>:", s_corpo))

story.append(tabela_generica(
    ["Workflow", "Trigger", "O que valida"],
    [
        ["<b>ci.yml</b>", "push / PR em main/master",
         "Roda pytest da suíte completa + build da imagem Docker"],
        ["<b>cd.yml</b>", "push em main",
         "Deploy automático do frontend no Vercel (production)"],
        ["<b>frontend.yml</b>", "push / PR em main/master",
         "npm ci → npm run lint (ESLint) → npm run build (Vite)"],
        ["<b>lint.yml</b>", "push / PR em main/master",
         "ruff check . + ruff format --check . no Backend"],
        ["<b>security.yml</b>", "push/PR + cron seg 08:00",
         "pip-audit sobre as deps Python — alerta sobre CVEs"],
    ],
    col_widths=[2.6*cm, 4.0*cm, uw - 6.6*cm],
))

story.append(Spacer(1, 0.20*cm))
story.append(Paragraph(
    "<b>Fluxo:</b> todo push em main dispara em paralelo ci, lint, frontend e security; "
    "em caso de sucesso, cd é encadeado e publica no Vercel.", s_corpo))

story.append(Spacer(1, 0.20*cm))
story.append(screenshot("01_github_actions.png", largura_cm=15.0,
                        legenda="Página de Actions no GitHub com workflows verdes"))

story.append(PageBreak())

# ── 6. Métricas + 7. Refatorações ───────────────────────────────────────────
story.append(Paragraph("6.&nbsp;&nbsp;Principais métricas de qualidade", s_h1))

story.append(tabela_generica(
    ["Métrica", "Etapa 4", "Etapa 5 (d210bf2)", "Atual (c138fb3)"],
    [
        ["Funções rank D (CC ≥ 21)",   "2",    "0",     "<b>0</b>"],
        ["Funções rank C (CC 11–20)",  "12",   "9",     "<b>1</b> (false-positive)"],
        ["CC média global (radon)",    "A (4.32)", "A (3.86)", "<b>A (3.54)</b>"],
        ["Blocos analisados",          "168",  "214",   "<b>239</b>"],
        ["Testes verdes",              "124",  "267",   "<b>269</b>"],
        ["Cobertura global",           "71%",  "74%",   "<b>74%</b>"],
        ["Tempo total da suíte",       "27,91 s", "17,62 s", "<b>~22 s</b>"],
    ],
    col_widths=[6.0*cm, 2.8*cm, 3.5*cm, uw - 12.3*cm],
    align_centers=[1, 2, 3],
))

story.append(Spacer(1, 0.20*cm))
story.append(Paragraph("7.&nbsp;&nbsp;Refatorações e justificativas técnicas", s_h1))

padroes = [
    ("Extract Method",
     "funções monolíticas viraram leitura linear; helpers de domínio claro, "
     "testáveis isoladamente."),
    ("Strategy Pattern",
     "n8n_service: 3 funções _enviar_*_sync (40 linhas idênticas) consolidadas em "
     "_invocar_webhook(...) parametrizado."),
    ("Table-Driven Design",
     "montar_docx_programatico (7 ifs → loop sobre tupla); senha_forte (5 ifs → "
     "all(any(...) for _, check in _REQUISITOS_SENHA)); _despachar_extractor."),
    ("Narrow Exception",
     "except Exception genérico substituído por exceções específicas; casos "
     "legítimos (rollback, fire-and-forget, libs opacas) mantidos com noqa BLE001 "
     "e log de type(error).__name__."),
]
for nome, desc in padroes:
    story.append(Paragraph(f"•&nbsp;&nbsp;<b>{nome}</b> — {desc}", s_bullet))

story.append(Spacer(1, 0.20*cm))
story.append(Paragraph("Ganhos de CC consolidados (Etapa 5 + incremental)", s_h3))
story.append(tabela_generica(
    ["Função", "Arquivo", "CC Antes", "CC Depois", "Rank"],
    [
        ["contestar_por_peticao",         "routes/contestacao_peticao.py",       "24", "7", "D → B"],
        ["montar_docx_com_modelo",        "services/contestacao_docx_builder.py","21", "4", "D → A"],
        ["montar_docx_programatico",      "services/contestacao_docx_builder.py","17", "1", "C → A"],
        ["buscar_defesas_semanticas",     "database.py",                          "16", "2", "C → A"],
        ["editar_contestacao",            "routes/edicao.py",                     "15", "2", "C → A"],
        ["diff_secoes",                   "services/diff_minuta.py",              "14", "5", "C → A"],
        ["buscar_defesas_similares",      "routes/rag.py",                        "14", "6", "C → B"],
        ["save_contestacao",              "database.py",                          "13", "5", "C → A"],
        ["_extrair_pdf",                  "services/peticao_extractor.py",        "13", "4", "C → A"],
        ["extrair_texto_peticao",         "services/peticao_extractor.py",        "13", "4", "C → A"],
        ["senha_forte",                   "models/usuario.py",                    "11", "2", "C → A"],
        ["prefiltrar_secoes_juridicas",   "services/peticao_extractor.py",        "11", "9", "C → B"],
    ],
    col_widths=[4.5*cm, 5.0*cm, 1.8*cm, 1.8*cm, uw - 13.1*cm],
    align_centers=[2, 3, 4],
))

story.append(Spacer(1, 0.15*cm))
story.append(Paragraph(
    "<i>Evidência detalhada antes/depois por função em docs/EVIDENCIAS_ETAPA5.md "
    "e nos commits d210bf2 (Etapa 5 oficial) e c138fb3 (refactor incremental).</i>",
    s_corpo_cm))

story.append(PageBreak())

# ── 8. Demonstracao em execucao ─────────────────────────────────────────────
story.append(Paragraph("8.&nbsp;&nbsp;Demonstração do sistema em execução", s_h1))
story.append(Paragraph(
    "A stack foi subida localmente (Docker + n8n + backend FastAPI + frontend "
    "Vite) e os fluxos principais foram navegados via Playwright headless para "
    "captura de evidência visual real:", s_corpo))

story.append(Spacer(1, 0.20*cm))
story.append(screenshot("02_login.png", largura_cm=15.0,
                        legenda="8.1  Tela inicial / modal de autenticação Supabase"))

story.append(Spacer(1, 0.30*cm))
story.append(screenshot("03_dashboard.png", largura_cm=15.0,
                        legenda="8.2  Formulário de login preenchido (credenciais demo)"))

story.append(PageBreak())

story.append(screenshot("04_form_contestacao.png", largura_cm=15.0,
                        legenda="8.3  Painel principal — formulário de contestação"))

story.append(Spacer(1, 0.30*cm))
story.append(screenshot("06_n8n_workflow.png", largura_cm=15.0,
                        legenda="8.4  n8n — interface de gerenciamento de workflows ativos"))

story.append(PageBreak())

# ── Apêndices ───────────────────────────────────────────────────────────────
story.append(Paragraph("Apêndice A — Como rodar localmente", s_h1))
story.append(code_block([
    "# 1. Subir Docker + n8n + backend",
    "pwsh docs\\_dev\\start-stack.ps1",
    "",
    "# 2. Subir frontend Vite",
    'cd "Front end\\vite-project"',
    "npm run dev",
    "",
    "# 3. Acessar",
    "#   Frontend:  http://localhost:5173",
    "#   Backend:   http://localhost:8000/health",
    "#   n8n UI:    http://localhost:5678  (admin@autojuri.local / AutoJuri2026!)",
]))

story.append(Spacer(1, 0.20*cm))
story.append(Paragraph("Para regenerar este documento (Markdown + PDF + screenshots):", s_corpo))
story.append(code_block([
    "pwsh docs\\_dev\\gerar_entrega_final.ps1",
]))

story.append(Spacer(1, 0.30*cm))
story.append(Paragraph("Apêndice B — Referências cruzadas", s_h1))
story.append(tabela_2col([
    ("README.md",                          "Visão geral, arquitetura, comandos rápidos"),
    ("docs/AGENTE_IA_AUTOJURI.md",         "Detalhes do motor Claude (prompt, parâmetros, fluxo)"),
    ("docs/PLANO_IMPLEMENTACAO_2026-04-29.md", "Roadmap Fases 1 e 2 (edição DOCX + treinar agente)"),
    ("docs/REVISAO_2026-04-29.md",         "Auditoria de segurança/qualidade pré-PR8/PR9"),
    ("docs/RELATORIO_METRICAS.md",         "Métricas detalhadas de cobertura e complexidade"),
    ("docs/EVIDENCIAS_ETAPA5.md",          "Refactor orientado a testes — tabelas antes/depois"),
], col1_width=7.0*cm))

story.append(Spacer(1, 0.30*cm))
story.append(HRFlowable(width="100%", thickness=0.5, color=CINZA_BORDA, spaceAfter=5))
story.append(Paragraph(
    "JurisFlow / AutoJuri  •  Projeto Integrador — Entrega Final  •  2026",
    s_rodape))


# ════════════════════════════════════════════════════════════════════════════
# Build
# ════════════════════════════════════════════════════════════════════════════
doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=A4,
    leftMargin=2.5*cm, rightMargin=2.5*cm,
    topMargin=1.8*cm,  bottomMargin=1.1*cm,
    title="Projeto Integrador — Entrega Final — AutoJuri/JurisFlow",
    author="GuilhermeADS13",
    subject="Entrega final do Projeto Integrador 2026",
)
doc.build(story, onFirstPage=page_bg, onLaterPages=page_bg)
print(f"PDF gerado: {OUTPUT}")
print(f"Tamanho: {os.path.getsize(OUTPUT) / 1024:.1f} KB")

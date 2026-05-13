"""Gera RELATORIO_METRICAS.pdf a partir de RELATORIO_METRICAS.md.

Uso:
    python docs/_dev/gerar_relatorio_pdf.py
"""
from pathlib import Path

import markdown
from xhtml2pdf import pisa

ROOT = Path(__file__).resolve().parents[1]
MD_PATH = ROOT / "RELATORIO_METRICAS.md"
PDF_PATH = ROOT / "RELATORIO_METRICAS.pdf"

CSS = """
@page {
    size: A4;
    margin: 2.2cm 2.0cm 2.4cm 2.0cm;
    @frame footer {
        -pdf-frame-content: footerContent;
        bottom: 1.0cm;
        margin-left: 2.0cm;
        margin-right: 2.0cm;
        height: 0.8cm;
    }
}
body {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    color: #1f2937;
    line-height: 1.55;
}

/* ---------- Capa ---------- */
.cover {
    margin-top: 4cm;
    text-align: center;
    -pdf-keep-with-next: true;
}
.cover .badge {
    display: inline-block;
    background-color: #0b3d91;
    color: #ffffff;
    font-size: 9pt;
    letter-spacing: 2pt;
    padding: 4pt 14pt;
    border-radius: 3pt;
    margin-bottom: 18pt;
}
.cover h1 {
    font-size: 26pt;
    color: #0b3d91;
    margin: 0 0 6pt 0;
    border: none;
    padding: 0;
}
.cover .subtitle {
    font-size: 13pt;
    color: #475569;
    margin-bottom: 30pt;
}
.cover .meta {
    margin: 0 auto;
    width: 75%;
    text-align: left;
    font-size: 10pt;
    background: #f1f5f9;
    border-left: 4px solid #0b3d91;
    padding: 12pt 16pt;
}
.cover .meta p { margin: 3pt 0; }
.page-break { page-break-before: always; }

/* ---------- Tipografia ---------- */
h1 {
    font-size: 19pt;
    color: #0b3d91;
    margin: 0 0 10pt 0;
    border-bottom: 2.5px solid #0b3d91;
    padding-bottom: 5pt;
}
h2 {
    font-size: 14pt;
    color: #0b3d91;
    margin-top: 22pt;
    margin-bottom: 8pt;
    padding: 4pt 0 4pt 10pt;
    border-left: 4px solid #0b3d91;
    background-color: #eef2ff;
}
h3 {
    font-size: 11.5pt;
    color: #1e3a8a;
    margin-top: 14pt;
    margin-bottom: 6pt;
}
p {
    margin: 6pt 0;
    text-align: justify;
}
ul, ol {
    margin: 6pt 0 8pt 18pt;
}
li {
    margin: 3pt 0;
    line-height: 1.5;
}
strong { color: #0b3d91; }
hr {
    border: none;
    border-top: 1px dashed #cbd5e1;
    margin: 16pt 0;
}

/* ---------- Código ---------- */
code {
    font-family: "Courier New", Consolas, monospace;
    font-size: 9pt;
    background-color: #f1f5f9;
    color: #b91c1c;
    padding: 1pt 4pt;
    border-radius: 2pt;
}
pre {
    font-family: "Courier New", Consolas, monospace;
    font-size: 9pt;
    background-color: #0f172a;
    color: #e2e8f0;
    padding: 10pt 12pt;
    border-radius: 4pt;
    margin: 8pt 0;
    line-height: 1.45;
}
pre code {
    background: transparent;
    color: inherit;
    padding: 0;
}

/* ---------- Tabelas ---------- */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 10pt 0 14pt 0;
    font-size: 9.5pt;
}
th {
    background-color: #0b3d91;
    color: #ffffff;
    padding: 6pt 8pt;
    text-align: left;
    border: 1px solid #0b3d91;
    font-weight: bold;
}
td {
    padding: 5pt 8pt;
    border: 1px solid #e2e8f0;
    vertical-align: top;
}
tr:nth-child(even) td {
    background-color: #f8fafc;
}

/* ---------- Blockquotes / Callouts ---------- */
blockquote {
    border-left: 4px solid #f59e0b;
    background: #fffbeb;
    padding: 8pt 14pt;
    margin: 10pt 0;
    color: #78350f;
    font-style: italic;
}
blockquote p { margin: 3pt 0; }
"""

FOOTER_HTML = """
<div id="footerContent" style="text-align: center; font-size: 8.5pt; color: #64748b;">
    <span style="color:#0b3d91; font-weight:bold;">AutoJuri / JurisFlow</span>
    &nbsp;·&nbsp; Relatório de Métricas de Qualidade
    &nbsp;·&nbsp; Página <pdf:pagenumber/> de <pdf:pagecount/>
</div>
"""

COVER_HTML = """
<div class="cover">
    <div class="badge">QUALIDADE DE SOFTWARE</div>
    <h1>Relatório de Métricas</h1>
    <div class="subtitle">AutoJuri — Plataforma JurisFlow de Contestações</div>
    <div class="meta">
        <p><strong>Repositório:</strong> GuilhermeADS13/API-JURISFLOW-CONTESTA-O</p>
        <p><strong>Branch:</strong> main &nbsp;·&nbsp; <strong>Commit:</strong> 236bc09</p>
        <p><strong>Data da análise:</strong> 2026-05-13</p>
        <p><strong>Ferramentas:</strong> pytest-cov, radon, vitest (v8)</p>
        <p><strong>Escopo:</strong> Backend (Python/FastAPI) + Frontend (React/Vite)</p>
    </div>
</div>
<div class="page-break"></div>
"""


def main() -> None:
    md_text = MD_PATH.read_text(encoding="utf-8")

    # Remove o cabeçalho-bloco do markdown (linhas iniciais com metadados)
    # mantendo o resto como conteúdo. A capa é renderizada via COVER_HTML.
    lines = md_text.splitlines()
    cut = 0
    for idx, line in enumerate(lines):
        if line.startswith("## ") or line.startswith("---"):
            cut = idx
            break
    body_md = "\n".join(lines[cut:]).lstrip("-").lstrip()

    html_body = markdown.markdown(
        body_md,
        extensions=["tables", "fenced_code", "sane_lists"],
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{CSS}</style></head>
<body>
{COVER_HTML}
{html_body}
{FOOTER_HTML}
</body></html>"""

    with PDF_PATH.open("wb") as fh:
        result = pisa.CreatePDF(html, dest=fh, encoding="utf-8")

    if result.err:
        raise SystemExit(f"Erro ao gerar PDF: {result.err}")
    print(f"OK: {PDF_PATH}")


if __name__ == "__main__":
    main()

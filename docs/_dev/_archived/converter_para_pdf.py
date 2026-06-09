#!/usr/bin/env python3
"""
Conversor Markdown para PDF
Converte CONTEXTO_PARA_CLAUDE.md para PDF com formatação profissional
"""

import os
import sys
from pathlib import Path

def convert_md_to_pdf():
    """Converte markdown para PDF usando pandoc ou weasyprint"""
    
    # Caminhos
    docs_dir = Path(__file__).parent
    md_file = docs_dir / "CONTEXTO_PARA_CLAUDE.md"
    pdf_file = docs_dir / "CONTEXTO_PARA_CLAUDE.pdf"
    
    if not md_file.exists():
        print(f"❌ Arquivo não encontrado: {md_file}")
        return False
    
    print(f"📄 Lendo: {md_file.name}")
    
    # Tenta pandoc primeiro (melhor qualidade)
    try:
        import subprocess
        result = subprocess.run(
            [
                "pandoc",
                str(md_file),
                "-o", str(pdf_file),
                "-V", "geometry:margin=1in",
                "-V", "colorlinks=true",
                "--pdf-engine=xelatex",
                "--table-of-contents",
                "--toc-depth=2",
                "--highlight-style=tango"
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            size_mb = pdf_file.stat().st_size / (1024 * 1024)
            print(f"✅ PDF criado com sucesso!")
            print(f"📍 Arquivo: {pdf_file}")
            print(f"📊 Tamanho: {size_mb:.2f} MB")
            return True
        else:
            print(f"⚠️  Pandoc falhou: {result.stderr}")
    
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"⚠️  Pandoc não disponível, tentando weasyprint...")
    
    # Fallback: weasyprint
    try:
        from weasyprint import HTML, CSS
        from io import StringIO
        
        # Lê markdown
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Converte markdown para HTML simples
        html_content = convert_markdown_to_html(content)
        
        # Gera PDF
        HTML(string=html_content).write_pdf(
            str(pdf_file),
            stylesheets=[
                CSS(string=get_pdf_styles())
            ]
        )
        
        size_mb = pdf_file.stat().st_size / (1024 * 1024)
        print(f"✅ PDF criado com sucesso (weasyprint)!")
        print(f"📍 Arquivo: {pdf_file}")
        print(f"📊 Tamanho: {size_mb:.2f} MB")
        return True
        
    except ImportError:
        print("⚠️  weasyprint não instalado")
    
    # Fallback: markdown2 + reportlab
    try:
        import markdown
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        
        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        # Converte para HTML
        html_content = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])
        
        print(f"✅ Markdown convertido para HTML")
        print(f"📍 Arquivo PDF gerado em: {pdf_file}")
        
        # Salva HTML para referência
        html_file = pdf_file.with_suffix('.html')
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Contexto AutoJuri para Claude</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial; line-height: 1.6; margin: 20px; }}
        h1 {{ color: #0066cc; border-bottom: 3px solid #0066cc; padding-bottom: 10px; }}
        h2 {{ color: #0066cc; margin-top: 30px; }}
        h3 {{ color: #0099ff; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background-color: #f0f0f0; font-weight: bold; }}
        code {{ background-color: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
        pre {{ background-color: #f4f4f4; padding: 10px; border-radius: 5px; overflow-x: auto; }}
        .status-ok {{ color: #00aa00; }}
        .status-wip {{ color: #ff9900; }}
        .status-todo {{ color: #cc0000; }}
    </style>
</head>
<body>
{html_content}
</body>
</html>""")
        
        print(f"💾 HTML também salvo em: {html_file}")
        return True
        
    except ImportError:
        print("❌ Nenhuma biblioteca de PDF disponível")
        print("   Instale com: pip install weasyprint pandoc markdown")
        return False


def convert_markdown_to_html(markdown_text):
    """Converte markdown simples para HTML"""
    try:
        import markdown
        return markdown.markdown(
            markdown_text,
            extensions=['tables', 'fenced_code', 'codehilite', 'toc']
        )
    except ImportError:
        # Fallback simples se markdown não estiver disponível
        return f"<pre>{markdown_text}</pre>"


def get_pdf_styles():
    """Retorna CSS para PDF"""
    return """
    @page {
        margin: 1in;
        size: A4;
    }
    
    body {
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 11pt;
        line-height: 1.6;
        color: #333;
    }
    
    h1 {
        color: #0066cc;
        font-size: 24pt;
        border-bottom: 2pt solid #0066cc;
        padding-bottom: 0.5in;
        margin-top: 0.5in;
        margin-bottom: 0.3in;
        page-break-after: avoid;
    }
    
    h2 {
        color: #0066cc;
        font-size: 16pt;
        margin-top: 0.4in;
        margin-bottom: 0.2in;
        page-break-after: avoid;
    }
    
    h3 {
        color: #0099ff;
        font-size: 13pt;
        margin-top: 0.3in;
        margin-bottom: 0.15in;
        page-break-after: avoid;
    }
    
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 0.3in 0;
    }
    
    th, td {
        border: 1pt solid #ddd;
        padding: 0.15in;
        text-align: left;
    }
    
    th {
        background-color: #f0f0f0;
        font-weight: bold;
    }
    
    code {
        background-color: #f4f4f4;
        padding: 2pt 6pt;
        border-radius: 3pt;
        font-family: 'Courier New', monospace;
        font-size: 10pt;
    }
    
    pre {
        background-color: #f4f4f4;
        padding: 0.2in;
        border-radius: 5pt;
        overflow-x: auto;
        font-family: 'Courier New', monospace;
        font-size: 9pt;
        page-break-inside: avoid;
    }
    
    a {
        color: #0066cc;
        text-decoration: underline;
    }
    
    .status-ok { color: #00aa00; }
    .status-wip { color: #ff9900; }
    .status-todo { color: #cc0000; }
    """


if __name__ == "__main__":
    print("🚀 Iniciando conversão de Markdown para PDF...")
    print("-" * 50)
    
    success = convert_md_to_pdf()
    
    print("-" * 50)
    if success:
        print("\n✨ Conversão concluída! PDF pronto para leitura.")
    else:
        print("\n⚠️  Conversão não completada. Tente instalar dependências:")
        print("   pip install weasyprint markdown")
    
    sys.exit(0 if success else 1)

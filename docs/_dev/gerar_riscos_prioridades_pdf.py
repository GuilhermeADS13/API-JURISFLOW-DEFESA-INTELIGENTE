"""Gera RISCOS_E_PRIORIDADES.pdf — versão enxuta apenas com riscos
e prioridades de melhoria.

Uso:
    python docs/_dev/gerar_riscos_prioridades_pdf.py
"""
from pathlib import Path

from xhtml2pdf import pisa

ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "RISCOS_E_PRIORIDADES.pdf"

CSS = """
@page {
    size: A4;
    margin: 2.0cm 2.0cm 2.2cm 2.0cm;
    @frame footer {
        -pdf-frame-content: footerContent;
        bottom: 0.9cm;
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

/* ---------- Cabecalho ---------- */
.header {
    border-bottom: 3px solid #0b3d91;
    padding-bottom: 8pt;
    margin-bottom: 16pt;
}
.header .badge {
    display: inline-block;
    background-color: #0b3d91;
    color: #ffffff;
    font-size: 8.5pt;
    letter-spacing: 1.5pt;
    padding: 3pt 10pt;
    border-radius: 3pt;
    margin-bottom: 6pt;
}
.header h1 {
    font-size: 20pt;
    color: #0b3d91;
    margin: 0;
    border: none;
    padding: 0;
}
.header .subtitle {
    font-size: 10pt;
    color: #475569;
    margin-top: 4pt;
}

/* ---------- Secao Riscos ---------- */
.section-risk {
    margin-top: 14pt;
}
.section-risk h2 {
    font-size: 14pt;
    color: #b91c1c;
    margin: 0 0 10pt 0;
    padding: 6pt 12pt;
    background-color: #fef2f2;
    border-left: 5px solid #b91c1c;
}
.risk-card {
    background-color: #ffffff;
    border: 1px solid #fecaca;
    border-left: 4px solid #b91c1c;
    padding: 8pt 12pt;
    margin: 6pt 0;
}
.risk-card .num {
    display: inline-block;
    background-color: #b91c1c;
    color: white;
    width: 18pt;
    height: 18pt;
    text-align: center;
    border-radius: 9pt;
    font-weight: bold;
    font-size: 9.5pt;
    margin-right: 6pt;
}
.risk-card .title {
    font-weight: bold;
    color: #7f1d1d;
    font-size: 10.5pt;
}
.risk-card .desc {
    margin-top: 4pt;
    color: #374151;
    font-size: 10pt;
}

/* ---------- Secao Prioridades ---------- */
.section-priority {
    margin-top: 22pt;
}
.section-priority h2 {
    font-size: 14pt;
    color: #047857;
    margin: 0 0 10pt 0;
    padding: 6pt 12pt;
    background-color: #ecfdf5;
    border-left: 5px solid #047857;
}

table.priorities {
    border-collapse: collapse;
    width: 100%;
    font-size: 9.5pt;
    margin-top: 6pt;
}
table.priorities th {
    background-color: #0b3d91;
    color: white;
    padding: 6pt 8pt;
    text-align: left;
    border: 1px solid #0b3d91;
}
table.priorities td {
    padding: 7pt 8pt;
    border: 1px solid #e2e8f0;
    vertical-align: top;
}
table.priorities tr:nth-child(even) td {
    background-color: #f8fafc;
}
.pri-alta {
    background-color: #b91c1c;
    color: white;
    padding: 2pt 8pt;
    border-radius: 3pt;
    font-weight: bold;
    font-size: 9pt;
    text-align: center;
}
.pri-media {
    background-color: #d97706;
    color: white;
    padding: 2pt 8pt;
    border-radius: 3pt;
    font-weight: bold;
    font-size: 9pt;
    text-align: center;
}
.pri-baixa {
    background-color: #047857;
    color: white;
    padding: 2pt 8pt;
    border-radius: 3pt;
    font-weight: bold;
    font-size: 9pt;
    text-align: center;
}

strong { color: #0b3d91; }
code {
    font-family: "Courier New", Consolas, monospace;
    font-size: 9pt;
    background-color: #f1f5f9;
    color: #b91c1c;
    padding: 1pt 4pt;
    border-radius: 2pt;
}
"""

FOOTER_HTML = """
<div id="footerContent" style="text-align: center; font-size: 8.5pt; color: #64748b;">
    <span style="color:#0b3d91; font-weight:bold;">AutoJuri / JurisFlow</span>
    &nbsp;·&nbsp; Riscos &amp; Prioridades de Melhoria
    &nbsp;·&nbsp; Página <pdf:pagenumber/> de <pdf:pagecount/>
</div>
"""

BODY_HTML = """
<div class="header">
    <div class="badge">QUALIDADE DE SOFTWARE</div>
    <h1>Riscos &amp; Prioridades de Melhoria</h1>
    <div class="subtitle">
        AutoJuri / JurisFlow &nbsp;·&nbsp;
        Branch <strong>main</strong> &nbsp;·&nbsp;
        Commit <strong>744b6ef</strong> &nbsp;·&nbsp;
        2026-05-13
    </div>
</div>

<div class="section-risk">
    <h2>Riscos do código atual</h2>

    <div class="risk-card">
        <span class="num">1</span>
        <span class="title">Integrações externas pouco testadas</span>
        <div class="desc">
            <code>n8n_service.py</code> (23% de cobertura) e <code>suporte_email_service.py</code> (20%) são
            <em>single points of failure</em> do produto e estão praticamente sem rede de proteção.
            Cenários de erro (timeout, 5xx, schema inválido, falha SMTP) não são exercitados por nenhum teste.
        </div>
    </div>

    <div class="risk-card">
        <span class="num">2</span>
        <span class="title"><code>database.py</code> com 46% de cobertura e 978 linhas</span>
        <div class="desc">
            Módulo monolítico que concentra conexão, sessões, usuários, contestações, dashboard e exemplares.
            Qualquer refatoração nessa camada tem risco alto de regressão silenciosa em produção.
        </div>
    </div>

    <div class="risk-card">
        <span class="num">3</span>
        <span class="title"><code>security.py</code> com 52% de cobertura</span>
        <div class="desc">
            Funções de autenticação (<code>get_current_user</code>, helpers de hash legado) com baixa cobertura.
            Vetor de regressão silenciosa em segurança — mesmo havendo testes de segurança no nível de rota,
            caminhos internos do módulo permanecem não cobertos.
        </div>
    </div>

    <div class="risk-card">
        <span class="num">4</span>
        <span class="title">Frontend abaixo do threshold de 90%</span>
        <div class="desc">
            Cobertura atual em <strong>84,10%</strong> — 5,9 p.p. abaixo do gate configurado no vitest.
            Componentes-chave (<code>App.jsx</code>, <code>MainPanelSection</code>, <code>RevisaoHumanaModal</code>)
            não possuem specs, e o pipeline <code>npm run test:coverage</code> falha hoje no gate de qualidade.
        </div>
    </div>

    <div class="risk-card">
        <span class="num">5</span>
        <span class="title">Função <code>contestar_por_peticao</code> com complexidade ciclomática 24 (rank D)</span>
        <div class="desc">
            Concentra todo o fluxo crítico do MVP em uma única função: validação MIME, upload, extração
            de PDF, fallback OCR, persistência e disparo do orquestrador n8n.
            Complexidade alta + cobertura de rota em 79% deixa branches importantes não exercitados.
        </div>
    </div>
</div>

<div class="section-priority">
    <h2>Prioridades de melhoria</h2>
    <table class="priorities">
        <thead>
            <tr>
                <th style="width:5%">#</th>
                <th style="width:12%">Prioridade</th>
                <th style="width:40%">Ação</th>
                <th style="width:43%">Impacto</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>1</strong></td>
                <td><span class="pri-alta">ALTA</span></td>
                <td>Subir cobertura de <code>services/n8n_service.py</code> para ≥ 70% com testes que mocam
                    <code>httpx</code>/<code>requests</code> cobrindo timeout, 5xx e schema inválido.</td>
                <td>Destrava confiabilidade do orquestrador — é o módulo que dispara as chamadas Claude.</td>
            </tr>
            <tr>
                <td><strong>2</strong></td>
                <td><span class="pri-alta">ALTA</span></td>
                <td>Cobrir <code>services/suporte_email_service.py</code> (SMTP) nos caminhos felizes e nas três
                    principais exceções (<code>SupportEmailConfigError</code>, <code>SupportEmailServiceError</code>,
                    fallback).</td>
                <td>Garante que o canal de suporte ao usuário não falhe silenciosamente em produção.</td>
            </tr>
            <tr>
                <td><strong>3</strong></td>
                <td><span class="pri-alta">ALTA</span></td>
                <td>Refatorar <code>contestar_por_peticao</code> em ≥ 3 funções menores
                    (validação, extração, orquestração).</td>
                <td>Reduz CC de 24 para &lt; 10 por função e melhora drasticamente a testabilidade.</td>
            </tr>
            <tr>
                <td><strong>4</strong></td>
                <td><span class="pri-media">MÉDIA</span></td>
                <td>Quebrar <code>database.py</code> em módulos por agregado:
                    <code>db/usuario.py</code>, <code>db/sessao.py</code>, <code>db/contestacao.py</code>,
                    <code>db/dashboard.py</code>.</td>
                <td>Sobe MI, melhora cobertura natural e reduz risco de regressão em refatorações futuras.</td>
            </tr>
            <tr>
                <td><strong>5</strong></td>
                <td><span class="pri-media">MÉDIA</span></td>
                <td>Adicionar specs para <code>App.jsx</code> / <code>MainPanelSection.jsx</code>
                    cobrindo o <em>golden path</em> (login → envio de petição → exibição no dashboard).</td>
                <td>Coloca o frontend acima dos 90% de threshold e libera o gate de cobertura no CI.</td>
            </tr>
            <tr>
                <td><strong>6</strong></td>
                <td><span class="pri-media">MÉDIA</span></td>
                <td>Substituir <code>except Exception:</code> genéricos por exceções específicas + log estruturado
                    nos 6 arquivos identificados.</td>
                <td>Melhora drasticamente o diagnóstico de incidentes em produção.</td>
            </tr>
            <tr>
                <td><strong>7</strong></td>
                <td><span class="pri-baixa">BAIXA</span></td>
                <td>Extrair estado de <code>App.jsx</code> (47 <code>useState</code>) para hooks por domínio
                    (<code>useAuth</code>, <code>useCases</code>, <code>useDashboard</code>).</td>
                <td>Reduz acoplamento e abre caminho para testes unitários do componente raiz.</td>
            </tr>
        </tbody>
    </table>
</div>
"""


def main() -> None:
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{CSS}</style></head>
<body>
{BODY_HTML}
{FOOTER_HTML}
</body></html>"""

    with PDF_PATH.open("wb") as fh:
        result = pisa.CreatePDF(html, dest=fh, encoding="utf-8")

    if result.err:
        raise SystemExit(f"Erro ao gerar PDF: {result.err}")
    print(f"OK: {PDF_PATH}")


if __name__ == "__main__":
    main()

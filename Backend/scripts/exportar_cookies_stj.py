"""Exporta cookies pre-autenticados do STJ para uso no scraper (PR26).

Cloudflare Turnstile do portal SCON/STJ bloqueia Playwright headless em IP
de datacenter (confirmado no smoke real do PR20 em 2026-06-29). Este script
implementa o workflow alternativo:

    1. Abre Chromium HEADFUL (janela visivel)
    2. Navega pra https://scon.stj.jus.br/SCON/
    3. Dev resolve o Turnstile manualmente (~5 segundos)
    4. Digita ENTER no terminal
    5. Script exporta cookies pra Backend/data/stj_cookies.json
    6. Scraper reusa via `--cookies=data/stj_cookies.json` por ~30min

Uso:
    cd Backend
    .venv\\Scripts\\python.exe scripts/exportar_cookies_stj.py

Requisitos:
    - Playwright + Chromium instalados (`python -m playwright install chromium`)
    - Ambiente com display grafico (nao roda em servidor headless — por design)

Seguranca:
    - Cookies contem token de sessao. NUNCA commitar `stj_cookies.json`.
    - `Backend/data/.gitignore` cobre esse arquivo automaticamente.
    - Considere `chmod 600 stj_cookies.json` apos exportar em multi-user host.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(
        "ERRO: playwright nao instalado. Rode:\n"
        "  .venv\\Scripts\\python.exe -m pip install playwright\n"
        "  .venv\\Scripts\\python.exe -m playwright install chromium",
        file=sys.stderr,
    )
    sys.exit(1)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "data" / "stj_cookies.json"
HOME_URL = "https://scon.stj.jus.br/SCON/"


def main() -> int:
    output = DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("EXPORTAR COOKIES STJ (workflow anti-Cloudflare Turnstile)")
    print("=" * 60)
    print(f"Alvo: {HOME_URL}")
    print(f"Saida: {output}")
    print()

    with sync_playwright() as p:
        # Headful — dev precisa VER a pagina pra resolver o Turnstile
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
        )
        try:
            context = browser.new_context(
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)

            print(
                "1) A pagina do SCON/STJ foi aberta no navegador.\n"
                "2) Se aparecer 'Um momento...' (Cloudflare Turnstile), aguarde\n"
                "   resolver automatico OU clique no checkbox 'Nao sou robo'.\n"
                "3) Confirme que voce ve a pagina de pesquisa (form aberto).\n"
                "4) Digite ENTER aqui pra exportar os cookies.\n"
            )
            try:
                input("Pressione ENTER quando o Turnstile estiver resolvido... ")
            except (KeyboardInterrupt, EOFError):
                print("\nCancelado pelo usuario.")
                return 1

            cookies = context.cookies()
            if not cookies:
                print(
                    "AVISO: nenhum cookie capturado. Verifique se o navegador "
                    "carregou a pagina corretamente.",
                    file=sys.stderr,
                )
                return 1

            # Filtra so cookies do dominio STJ pra reduzir ruido
            cookies_stj = [
                c for c in cookies if "stj.jus.br" in (c.get("domain") or "")
            ]
            if not cookies_stj:
                print(
                    "AVISO: nenhum cookie do dominio stj.jus.br foi encontrado. "
                    "Salvando TODOS os cookies mesmo assim.",
                    file=sys.stderr,
                )
                cookies_stj = cookies

            output.write_text(
                json.dumps(cookies_stj, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            # Diagnostico: menor expires do bloco = validade real da sessao
            expires_epochs = [
                c.get("expires")
                for c in cookies_stj
                if isinstance(c.get("expires"), (int, float)) and c["expires"] > 0
            ]
            if expires_epochs:
                menor = min(expires_epochs)
                dt = datetime.fromtimestamp(menor, tz=timezone.utc).astimezone()
                validade = f" — 1o cookie expira em {dt.strftime('%H:%M:%S %d/%m/%Y')}"
            else:
                validade = " — cookies de sessao (expiram ao fechar o navegador)"

            print(f"\nOK: {len(cookies_stj)} cookies exportados pra {output}{validade}")
            print(
                "\nUso agora:\n"
                f"  .venv\\Scripts\\python.exe scripts/scrape_jurisprudencia.py \\\n"
                f'      --tribunal=stj --query="sua query" --max=10 \\\n'
                f"      --cookies={output.relative_to(ROOT)}\n"
            )
            print(
                "IMPORTANTE: NUNCA commitar stj_cookies.json — contem token "
                "da sessao. `Backend/data/.gitignore` ja cobre.\n"
            )
            return 0
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())

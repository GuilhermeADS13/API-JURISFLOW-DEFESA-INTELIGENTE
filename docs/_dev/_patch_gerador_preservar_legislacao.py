"""Patcha o node Claude Gerador de Contestacao (PR16 Bug #3): preserva
legislacao_aplicavel + defesas_anteriores no return final pra observabilidade.

Sintoma: a peca #43 tinha contradicoes + documentos_anexos preenchidos, mas
nao tinha legislacao_aplicavel nem defesas_anteriores nas chaves do envelope
salvo. Causa: o return do Gerador filtra explicitamente as chaves — descarta
o que veio do envelope. Como resultado:
- Nao da pra auditar quais leis o Gerador usou na peca
- Frontend nunca consegue mostrar 'Legislacao consultada' no modal de resultado

Idempotente: detecta marker PR16_PRESERVA_OBSERVABILIDADE.

Uso:
    python docs/_dev/_patch_gerador_preservar_legislacao.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKER = "PR16_PRESERVA_OBSERVABILIDADE"


def patch_gerador(js: str) -> tuple[str, bool]:
    """Substitui o return final do Gerador adicionando legislacao_aplicavel +
    defesas_anteriores + exemplares_fewshot vindas do envelope."""
    if MARKER in js:
        return js, False

    # O return atual tem essas keys (do meu PR12 #4 atualizado):
    old_return = (
        "return [{ json: {\n"
        "  status: provider === 'fallback' ? 'erro_ia' : 'ok',\n"
        "  dados_extraidos: dados,\n"
        "  minuta,\n"
        "  engine_ia: { provider, model: CLAUDE_MODEL, api_error: apiError,"
    )

    new_return = (
        f"// {MARKER}: preserva chaves do envelope pra observabilidade no frontend\n"
        "// e analise pos-geracao. Sem isso, RAG hibrido (PR12) e Legislacao\n"
        "// Verificada (PR13 B3) somem antes de chegar ao Responder.\n"
        "return [{ json: {\n"
        "  status: provider === 'fallback' ? 'erro_ia' : 'ok',\n"
        "  dados_extraidos: dados,\n"
        "  minuta,\n"
        "  defesas_anteriores: envelope.defesas_anteriores || null,\n"
        "  exemplares_fewshot: envelope.exemplares_fewshot || [],\n"
        "  legislacao_aplicavel: envelope.legislacao_aplicavel || [],\n"
        "  engine_ia: { provider, model: CLAUDE_MODEL, api_error: apiError,"
    )

    if old_return not in js:
        raise RuntimeError(
            "Bloco de return original nao encontrado — verifique se o template mudou. "
            "Procurando: 'return [{ json: { status: provider === ...'"
        )

    js = js.replace(old_return, new_return, 1)
    return js, True


def main() -> int:
    base = Path(__file__).resolve().parents[2]
    wf_path = base / "docs" / "n8n_workflow_contestar_por_peticao.json"
    wf = json.loads(wf_path.read_text(encoding="utf-8"))

    gerador = next(
        (n for n in wf["nodes"] if n.get("id") == "node-gerador-peticao"), None
    )
    if gerador is None:
        print("ERRO: node Gerador nao encontrado", file=sys.stderr)
        return 1

    js_novo, mudou = patch_gerador(gerador["parameters"]["jsCode"])
    if not mudou:
        print(f"Workflow ja contem marker {MARKER}. Nada a fazer.")
        return 0

    gerador["parameters"]["jsCode"] = js_novo
    wf["description"] = (
        wf.get("description", "")
        + " | PR16 Bug #3: Gerador preserva legislacao_aplicavel + defesas_anteriores."
    )
    wf["updatedAt"] = "2026-06-09T17:40:00.000Z"

    wf_path.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"OK: marker {MARKER} injetado no Gerador em {wf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

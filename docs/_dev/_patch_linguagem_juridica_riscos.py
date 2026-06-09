"""Patcha o Gerador (PR16 #1): substitui linguagem tecnica 'no input' pelo
equivalente juridico 'nos autos' nos riscos[] gerados pela IA.

Antes: 'folha de ponto nao consta no input — anexar antes da audiencia'
Depois: 'folha de ponto nao consta nos autos — anexar antes da audiencia'

+ adiciona regra geral no SYSTEM proibindo jargao tecnico em riscos[].

Idempotente: detecta marker `PR16_LINGUAGEM_JURIDICA` no SYSTEM.

Uso:
    python docs/_dev/_patch_linguagem_juridica_riscos.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKER = "PR16_LINGUAGEM_JURIDICA"

# Bloco a injetar no SYSTEM logo apos a regra LACUNAS FACTUAIS, reforcando
# que riscos[] deve usar linguagem juridica (que o advogado/juiz le).
NOVO_BLOCO = (
    f"\n- [{MARKER}] LINGUAGEM JURIDICA EM riscos[]: o array 'riscos[]' eh "
    "exibido ao ADVOGADO antes do protocolo. Use SEMPRE linguagem juridica formal. "
    "NUNCA use: 'input', 'documento de entrada', 'arquivo enviado', 'sistema', "
    "'usuario', 'banco de dados'. USE: 'os autos', 'documentos juntados', "
    "'documentos acostados', 'documentacao apresentada', 'instrucao processual', "
    "'a contestacao'. Exemplo CORRETO: 'folha de ponto nao consta nos autos — "
    "anexar antes da audiencia'. Exemplo INCORRETO: 'folha de ponto nao consta "
    "no input — anexar antes da audiencia'."
)


def patch_gerador(js: str) -> tuple[str, bool]:
    """Substitui 'no input' por 'nos autos' + injeta regra de linguagem juridica."""
    if MARKER in js:
        return js, False

    # 1. Substituicoes literais do prompt (NAO mexe em codigo JS — so strings dentro do SYSTEM).
    substitucoes = [
        # exemplo dos riscos da regra DOCUMENTOS PROBATORIOS
        ("folha de ponto/cartao de ponto nao consta no input",
         "folha de ponto/cartao de ponto nao consta nos autos"),
        # regra DOCUMENTOS DIGITALIZADOS
        ("Quando o input mencionar que algum documento eh digitalizado",
         "Quando os autos mencionarem que algum documento eh digitalizado"),
        # outras ocorrencias defensivas (caso surjam variacoes)
        (" no input ", " nos autos "),
        (" no input.", " nos autos."),
        (" no input,", " nos autos,"),
        (" no input —", " nos autos —"),
        (" no input -", " nos autos -"),
    ]

    mudou = False
    for old, new in substitucoes:
        if old in js:
            js = js.replace(old, new)
            mudou = True

    # 2. Injeta regra de linguagem juridica logo apos LACUNAS FACTUAIS.
    anchor = "LACUNAS FACTUAIS:"
    if anchor not in js:
        raise RuntimeError(
            "Anchor LACUNAS FACTUAIS nao encontrada — verifique o SYSTEM_GERACAO"
        )
    # Encontra o fim do paragrafo da regra (proxima quebra de bullet)
    idx_anchor = js.find(anchor)
    idx_next = js.find("\n- ", idx_anchor + len(anchor))
    if idx_next == -1:
        raise RuntimeError("Proximo bullet apos LACUNAS FACTUAIS nao encontrado")
    js = js[:idx_next] + NOVO_BLOCO + js[idx_next:]

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
        + " | PR16: linguagem juridica em riscos[] (no input -> nos autos)."
    )
    wf["updatedAt"] = "2026-06-09T17:30:00.000Z"

    wf_path.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"OK: marker {MARKER} injetado em {wf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

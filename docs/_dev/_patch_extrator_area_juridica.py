"""Patcha o workflow contestar-por-peticao.json (PR13 #B1):
- Extrator: SYSTEM pede area_juridica + USER inclui no template JSON
- Buscar Defesas: encaminha area_juridica no body do call ao backend

Idempotente: detecta marcador `area_juridica` no JS e nao reaplica.

Uso:
    python docs/_dev/_patch_extrator_area_juridica.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def patch_extrator(js: str) -> tuple[str, bool]:
    """Modifica o JS do node Extrator. Retorna (novo_js, mudou).

    Nota: o JS no JSON ja vem com newlines reais e aspas reais apos parse.
    """
    if "area_juridica" in js:
        return js, False

    # 1. Adiciona regra no SYSTEM_EXTRACAO sobre area_juridica canonica
    old_system = (
        "Voce eh um extrator de dados juridicos brasileiros.\n"
        "Sua unica funcao eh ler uma peticao inicial e retornar JSON estruturado.\n"
        "Nao invente dados. Se um campo nao estiver claro, use null.\n"
        "Retorne SOMENTE JSON valido, sem markdown, sem codeblock."
    )
    new_system = old_system + (
        "\n\nIMPORTANTE: o campo area_juridica deve ser exatamente UMA das chaves canonicas:\n"
        "- trabalhista (acoes da Justica do Trabalho, verbas rescisorias, FGTS, horas extras, CLT)\n"
        "- consumidor (CDC, vicio do produto, servico defeituoso, lei 8078)\n"
        "- bancario (instituicoes financeiras, emprestimos, credito consignado, cartao)\n"
        "- previdenciario (INSS, aposentadoria, beneficios, lei 8213)\n"
        "- civel (contratos cives, responsabilidade civil, danos materiais, CPC subsidiario)\n"
        "Se nao se enquadrar em nenhuma, retorne null em area_juridica."
    )
    if old_system not in js:
        raise RuntimeError("SYSTEM_EXTRACAO antigo nao encontrado — verifique se o template mudou")
    js = js.replace(old_system, new_system)

    # 2. Adiciona area_juridica no template do JSON pedido ao Claude
    old_template_line = '  "tipo_acao": "tipo da acao (ex: Trabalhista - Horas Extras, Direito do Consumidor)",'
    new_template_line = (
        old_template_line
        + '\n  "area_juridica": "uma de: trabalhista|consumidor|bancario|previdenciario|civel|null",'
    )
    if old_template_line not in js:
        raise RuntimeError("Linha tipo_acao do template nao encontrada — verifique se o template mudou")
    js = js.replace(old_template_line, new_template_line)

    return js, True


def patch_buscar_defesas(js: str) -> tuple[str, bool]:
    """Modifica o JS do node Buscar Defesas Anteriores. Encaminha area_juridica."""
    # Marcador pra idempotencia: se ja tem area_juridica no body do RAG call, sai
    if "area_juridica: dados.area_juridica" in js:
        return js, False

    old_body = "        fatos: dados.fatos_resumo || '',\n        pedidos: pedidosArr,"
    new_body = (
        "        fatos: dados.fatos_resumo || '',\n"
        "        pedidos: pedidosArr,\n"
        "        area_juridica: dados.area_juridica || null,"
    )
    if old_body not in js:
        raise RuntimeError("Body do RAG call no node Buscar Defesas nao encontrado — verifique se o template mudou")
    js = js.replace(old_body, new_body)

    return js, True


def main() -> int:
    base = Path(__file__).resolve().parents[2]
    wf_path = base / "docs" / "n8n_workflow_contestar_por_peticao.json"
    wf = json.loads(wf_path.read_text(encoding="utf-8"))

    extrator = next((n for n in wf["nodes"] if n.get("id") == "node-extrator-peticao"), None)
    buscar = next(
        (n for n in wf["nodes"] if n.get("id") == "node-buscar-defesas-peticao"), None
    )
    if not extrator or not buscar:
        print("ERRO: nodes Extrator ou Buscar Defesas nao encontrados", file=sys.stderr)
        return 1

    js_ext_novo, mudou_ext = patch_extrator(extrator["parameters"]["jsCode"])
    js_busc_novo, mudou_busc = patch_buscar_defesas(buscar["parameters"]["jsCode"])

    if not mudou_ext and not mudou_busc:
        print("Workflow ja contem area_juridica nos nodes Extrator e Buscar Defesas. Nada a fazer.")
        return 0

    extrator["parameters"]["jsCode"] = js_ext_novo
    buscar["parameters"]["jsCode"] = js_busc_novo
    wf["description"] = (
        wf.get("description", "")
        + " | PR13 #B1: Extrator pede area_juridica + Buscar Defesas encaminha pro filtro."
    )
    wf["updatedAt"] = "2026-06-08T18:00:00.000Z"

    wf_path.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"OK: Extrator (mudou={mudou_ext}) + Buscar Defesas (mudou={mudou_busc}) "
        f"patchados em {wf_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

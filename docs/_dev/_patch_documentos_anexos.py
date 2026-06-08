"""Patcha o workflow (PR14): adiciona campo `documentos_anexos[]` no JSON
da minuta gerada pelo Claude + regras no SYSTEM ensinando quais documentos
recomendar por tipo de pedido.

Idempotente: detecta o marcador `documentos_anexos` no SYSTEM e nao reaplica.

Uso:
    python docs/_dev/_patch_documentos_anexos.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Bloco a injetar APOS '== DOCUMENTOS DIGITALIZADOS ==' no SYSTEM_GERACAO.
# Regras de quais documentos pedir por tipo de pedido + formato do array.
NOVO_BLOCO_SYSTEM = """\n- DOCUMENTOS PROBATORIOS A ANEXAR: SEMPRE popule o campo documentos_anexos[] do JSON com a lista de documentos que a Reclamada deve juntar a defesa pra desincumbir do onus do art. 818 CLT. Cada item: {numero, tipo, descricao}. Regras de mapeamento pedido -> documento:\n  * HORAS EXTRAS / JORNADA / INTERVALO -> Folha de Ponto / Cartoes de Ponto eletronicos do periodo integral do contrato. Citar Sumula 338 TST.\n  * FGTS / DIFERENCAS DE DEPOSITO -> Extrato Analitico do FGTS (CEF) do periodo contratual.\n  * RESCISAO / VERBAS RESCISORIAS / MULTA 40% -> TRCT homologado + comprovantes de pagamento.\n  * DANOS MORAIS / ASSEDIO -> Eventuais e-mails/prints/audios/CFTV + laudo psicologico se houver.\n  * INSALUBRIDADE / PERICULOSIDADE -> Laudo Pericial Tecnico + PPP + ficha de EPI.\n  * EQUIPARACAO SALARIAL -> Holerites do reclamante e do paradigma + descricao de funcoes.\n  * DIFERENCAS SALARIAIS / ADICIONAIS -> Holerites mensais do periodo controverso.\n  * DESCONTOS INDEVIDOS -> Autorizacao escrita + recibos dos descontos.\n  * VINCULO EMPREGATICIO / ANOTACAO CTPS -> CTPS digital + contrato de trabalho assinado.\n  * RESCISAO INDIRETA -> Comunicacoes internas (advertencias, suspensoes) + recibos.\n  - SEMPRE incluir como Doc. 01: 'Contrato de Trabalho' e como Doc. 02: 'CTPS Digital'.\n  - Numerar sequencialmente 'Doc. 01', 'Doc. 02', etc. ate no maximo 10 itens.\n  - 'descricao' deve ser objetiva (1-2 frases) explicando O QUE prova.\n  - Se a peca nao tiver pedido relevante pra um tipo de documento, NAO incluir."""

# Linha a adicionar no template JSON pedido ao Claude — logo apos `protesta_provas`.
OLD_TEMPLATE_LINE = '  "protesta_provas": "Protesta provar o alegado por todos os meios de prova em direito admitidos, em especial depoimento pessoal do autor, oitiva de testemunhas, pericia, juntada de documentos.",'
NEW_TEMPLATE_LINE = OLD_TEMPLATE_LINE + '\n  "documentos_anexos": [{"numero": "Doc. 01", "tipo": "Contrato de Trabalho", "descricao": "Contrato firmado entre as partes, comprovando os termos pactuados (jornada, salario, funcao)."}, {"numero": "Doc. 02", "tipo": "CTPS Digital", "descricao": "Carteira de Trabalho com as anotacoes contratuais oficiais."}],'


def patch_gerador(js: str) -> tuple[str, bool]:
    """Adiciona regras no SYSTEM + campo no template do JSON."""
    if "documentos_anexos" in js:
        return js, False

    # 1. Injeta regras no SYSTEM apos '== DOCUMENTOS DIGITALIZADOS =='
    marker = "DOCUMENTOS DIGITALIZADOS:"
    if marker not in js:
        raise RuntimeError(
            "Marcador 'DOCUMENTOS DIGITALIZADOS:' nao encontrado — verifique o SYSTEM_GERACAO"
        )
    # Acha o fim do paragrafo daquela regra (proxima ocorrencia de '\n-')
    idx_marker = js.find(marker)
    # Avanca pra encontrar o proximo bullet que comeca com '\n- '
    idx_proximo_bullet = js.find("\n- ", idx_marker + len(marker))
    if idx_proximo_bullet == -1:
        raise RuntimeError(
            "Proximo bullet apos DOCUMENTOS DIGITALIZADOS nao encontrado"
        )
    # Insere o novo bloco logo antes do proximo bullet
    js = js[:idx_proximo_bullet] + NOVO_BLOCO_SYSTEM + js[idx_proximo_bullet:]

    # 2. Adiciona campo no template do JSON pedido ao Claude
    if OLD_TEMPLATE_LINE not in js:
        raise RuntimeError(
            "Linha 'protesta_provas' do template JSON nao encontrada — verifique se mudou"
        )
    js = js.replace(OLD_TEMPLATE_LINE, NEW_TEMPLATE_LINE)

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
        print("Workflow ja contem documentos_anexos. Nada a fazer.")
        return 0

    gerador["parameters"]["jsCode"] = js_novo
    wf["description"] = (
        wf.get("description", "")
        + " | PR14: documentos_anexos[] no JSON da minuta + ROL no docx."
    )
    wf["updatedAt"] = "2026-06-08T20:00:00.000Z"

    wf_path.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"OK: documentos_anexos injetado no Gerador em {wf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

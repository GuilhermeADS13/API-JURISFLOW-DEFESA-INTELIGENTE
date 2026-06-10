"""PR18 — corrige os 3 problemas encontrados na revisao da peca gerada para o
processo 0000420-35.2026.5.06.0411 (comparacao com a contestacao humana do
escritorio, 2026-06-09):

1. QUASE-CONFISSOES: a peca gerada escreveu 'as verbas rescisorias serao
   devidamente quitadas' e prometeu ~8x 'documentos a serem juntados
   oportunamente' — admite inadimplemento (fortalece multas 467/477 CLT) e
   ignora que prova documental acompanha a defesa (preclusao). Fix: regras
   PR18_NAO_CONFESSAR e PR18_NAO_PROMETER_JUNTADA no SYSTEM do Gerador +
   ajuste do exemplo da regra de LACUNAS FACTUAIS que induzia o erro.

2. PLACEHOLDER EM PROSA: 'com sede no endereco a ser complementado nos
   autos' vazou pra peca final — sendo que o endereco da re CONSTAVA na
   peticao inicial. Fix: Extrator passa a extrair endereco_reu + cnpj_reu +
   data_ajuizamento; Gerador injeta no USER_MSG e o schema do
   cabecalho_processual manda usar o endereco extraido ou o marcador
   visivel [ENDERECO DA SEDE - PREENCHER].

3. NUMEROS INVENTADOS + MARCO PRESCRICIONAL ERRADO: a peca inventou
   '600 km / 7 horas' (instrucao da preliminar 5 INDUZIA a citar cifras) e
   ancorou a prescricao na data de admissao (04/06/2021) em vez do
   ajuizamento - 5 anos (16/04/2021) — a instrucao da preliminar 7 era
   ambigua ('admissao + 5 anos antes do ajuizamento'). Fix: marco
   prescricional calculado em CODIGO no Gerador a partir de
   dados.data_ajuizamento e injetado no USER_MSG; regra
   PR18_NAO_INVENTAR_NUMEROS; preliminares 5 e 7 reescritas.

Idempotente: detecta marker PR18.

Uso:
    python docs/_dev/_patch_pr18_anti_confissao_dados_reu.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKER = "PR18"


# ───────────────────────────── Extrator ─────────────────────────────────────

def patch_extrator(js: str) -> str:
    """Adiciona endereco_reu, cnpj_reu e data_ajuizamento ao schema + fallback."""
    # 1) Schema do USER_EXTRACAO
    old_schema = '"vara": "vara/tribunal se mencionado ou null",'
    new_schema = (
        '"vara": "vara/tribunal se mencionado ou null",\n'
        '  "endereco_reu": "endereco completo da sede do reu como consta na peticao '
        "(logradouro, numero, bairro, CEP, cidade/UF) ou null — procure na qualificacao "
        'das partes no inicio da peticao",\n'
        '  "cnpj_reu": "CNPJ do reu como consta na peticao ou null",\n'
        '  "data_ajuizamento": "data de ajuizamento/autuacao da acao no formato DD/MM/AAAA '
        "(capa do PJe traz 'Data da Autuacao'; corpo da peca pode trazer a data da "
        'assinatura) ou null",  '
        f"// {MARKER}_DADOS_REU"
    )
    if old_schema not in js:
        raise RuntimeError("anchor do schema do Extrator nao encontrado")
    js = js.replace(old_schema, new_schema, 1)

    # 2) Objeto de fallback (extracao falhou) — manter shape consistente.
    old_fb = "vara: null,\n    fatos_resumo: contexto.texto_peticao.slice(0, 2000),"
    new_fb = (
        "vara: null,\n"
        "    endereco_reu: null,\n"
        "    cnpj_reu: null,\n"
        "    data_ajuizamento: null,\n"
        "    fatos_resumo: contexto.texto_peticao.slice(0, 2000),"
    )
    if old_fb not in js:
        raise RuntimeError("anchor do fallback do Extrator nao encontrado")
    return js.replace(old_fb, new_fb, 1)


# ───────────────────────────── Gerador ──────────────────────────────────────

CALC_PRESCRICAO_JS = """
// PR18_DADOS_REU: marco prescricional calculado em CODIGO (deterministico).
// A LLM errava o marco (ancorava na data de admissao em vez do ajuizamento);
// regra correta: data do ajuizamento menos 5 anos (art. 7, XXIX, CF).
const _parseDataBr = (s) => {
  const m = /([0-3]?\\d)[\\/\\-.]([01]?\\d)[\\/\\-.](\\d{4})/.exec(String(s || ''));
  if (!m) return null;
  const dt = new Date(parseInt(m[3], 10), parseInt(m[2], 10) - 1, parseInt(m[1], 10));
  return isNaN(dt.getTime()) ? null : dt;
};
let marcoPrescricional = null;
const _dtAjuizamento = _parseDataBr(dados.data_ajuizamento);
if (_dtAjuizamento) {
  const _d = new Date(_dtAjuizamento);
  _d.setFullYear(_d.getFullYear() - 5);
  const _pad = (n) => String(n).padStart(2, '0');
  marcoPrescricional = `${_pad(_d.getDate())}/${_pad(_d.getMonth() + 1)}/${_d.getFullYear()}`;
}

"""

REGRAS_PR18 = (
    "\n- [PR18_NAO_CONFESSAR] PROIBIDO ADMITIR INADIMPLEMENTO OU PROMETER CUMPRIMENTO "
    "FUTURO: frases como 'as verbas rescisorias serao devidamente quitadas', 'a Reclamada "
    "providenciara a baixa na CTPS', 'os valores serao pagos' ADMITEM que a obrigacao nao "
    "foi cumprida — confissao que fortalece as multas dos arts. 467/477 CLT contra a "
    "propria defesa. SEMPRE controverta: 'impugna-se a alegacao de inadimplemento', 'as "
    "verbas devidas observarao a modalidade rescisoria correta, sendo objeto de "
    "controversia', 'nao ha verbas incontroversas em atraso'. NUNCA escreva que a "
    "Reclamada 'fara' / 'providenciara' / 'quitara' algo no futuro."
    "\n- [PR18_NAO_PROMETER_JUNTADA] PROVA DOCUMENTAL ACOMPANHA A DEFESA (a juntada "
    "posterior preclui): NUNCA escreva 'documentos a serem juntados oportunamente', "
    "'recibos que serao juntados', 'juntara oportunamente', 'sera demonstrado pela "
    "documentacao a ser acostada'. Escreva 'conforme documentos que instruem a presente "
    "defesa' e garanta que o documento correspondente esteja listado em "
    "documentos_anexos[]. Se a defesa depende de documento que pode nao existir, anote a "
    "pendencia em riscos[] — nao prometa juntada futura no corpo da peca."
    "\n- [PR18_NAO_INVENTAR_NUMEROS] NUNCA invente numeros especificos (distancias em km, "
    "horas de viagem, valores em reais, datas, quantidades) que nao constem dos dados "
    "extraidos, do modelo base, das defesas RAG ou dos pontos do advogado. Numero "
    "plausivel inventado eh pior que ausencia do numero — destroi a credibilidade da peca "
    "perante o juizo."
)


def patch_gerador(js: str) -> str:
    # 1) Calculo do marco prescricional antes do USER_MSG.
    anchor_user = "const USER_MSG = `# Dados da Peticao"
    if anchor_user not in js:
        raise RuntimeError("anchor do USER_MSG do Gerador nao encontrado")
    js = js.replace(anchor_user, CALC_PRESCRICAO_JS + anchor_user, 1)

    # 2) Linhas novas no USER_MSG (apos a Vara).
    old_vara = "- **Vara:** ${dados.vara || 'nao informada'}"
    new_vara = (
        "- **Vara:** ${dados.vara || 'nao informada'}\n"
        "- **Data de ajuizamento:** ${dados.data_ajuizamento || 'nao identificada'}\n"
        "- **CNPJ do reu:** ${dados.cnpj_reu || 'nao consta'}\n"
        "- **Endereco da sede do reu (extraido da peticao):** "
        "${dados.endereco_reu || 'NAO CONSTA NA PETICAO — no cabecalho use o marcador "
        "literal [ENDERECO DA SEDE - PREENCHER]'}\n"
        "${marcoPrescricional ? `- **MARCO PRESCRICIONAL (calculado pelo sistema = "
        "ajuizamento menos 5 anos; use EXATAMENTE esta data na preliminar de prescricao "
        "quinquenal):** ${marcoPrescricional}` : ''}"
    )
    if old_vara not in js:
        raise RuntimeError("anchor da linha Vara do USER_MSG nao encontrado")
    js = js.replace(old_vara, new_vara, 1)

    # 3) Regras anti-confissao/anti-invencao apos a regra de LACUNAS FACTUAIS
    #    (e conserta o exemplo da propria regra, que induzia a promessa de juntada).
    old_lacuna_ex = (
        "('conforme documentos a serem apresentados em audiencia', "
        "'em valor a ser apurado em fase de liquidacao')"
    )
    new_lacuna_ex = (
        "('conforme documentos que instruem a presente defesa', "
        "'em valor a ser apurado em fase de liquidacao')"
    )
    if old_lacuna_ex not in js:
        raise RuntimeError("exemplo da regra LACUNAS FACTUAIS nao encontrado")
    js = js.replace(old_lacuna_ex, new_lacuna_ex, 1)

    old_lacuna_fim = "Inventar fato eh pior que admitir lacuna."
    if old_lacuna_fim not in js:
        raise RuntimeError("fim da regra LACUNAS FACTUAIS nao encontrado")
    js = js.replace(old_lacuna_fim, old_lacuna_fim + REGRAS_PR18, 1)

    # 4) Preliminar 5 (Juizo 100% digital): nao induzir cifras inventadas.
    old_p5 = (
        "citando: enderaco da sede, distancia em km e horas, e celeridade "
        "processual + reducao de custos de logistica."
    )
    new_p5 = (
        "citando o endereco da sede e a celeridade processual + reducao de custos de "
        "logistica. Distancia em km/horas: cite SOMENTE se constar do modelo base, das "
        "defesas RAG ou dos pontos do advogado — NUNCA estime cifras por conta propria "
        "(PR18_NAO_INVENTAR_NUMEROS)."
    )
    if old_p5 not in js:
        raise RuntimeError("preliminar 5 (Juizo 100% digital) nao encontrada")
    js = js.replace(old_p5, new_p5, 1)

    # 5) Preliminar 7 (prescricao): usar o marco calculado pelo sistema.
    old_p7 = (
        "CALCULE a data-limite especifica (admissao + 5 anos antes do ajuizamento) "
        "e cite-a expressamente."
    )
    new_p7 = (
        "Use EXATAMENTE a data 'MARCO PRESCRICIONAL' fornecida nos dados (calculada pelo "
        "sistema: data do ajuizamento menos 5 anos — NAO eh a data de admissao). Se os "
        "dados nao trouxerem o marco, NAO calcule nem invente data: escreva 'parcelas "
        "anteriores ao quinquenio que antecede o ajuizamento da acao'."
    )
    if old_p7 not in js:
        raise RuntimeError("preliminar 7 (prescricao) nao encontrada")
    js = js.replace(old_p7, new_p7, 1)

    # 6) Schema do cabecalho_processual: endereco real ou marcador visivel.
    old_cab = "com sede em ..., nos autos da"
    new_cab = (
        "com sede em <endereco_reu dos dados; se 'NAO CONSTA', escreva o marcador "
        "literal [ENDERECO DA SEDE - PREENCHER] — NUNCA prosa vaga tipo 'endereco a "
        "ser complementado nos autos'>, nos autos da"
    )
    if old_cab not in js:
        raise RuntimeError("schema do cabecalho_processual nao encontrado")
    js = js.replace(old_cab, new_cab, 1)

    # 7) Regra PF vs PJ: apontar pros campos extraidos.
    old_pj = (
        "'pessoa juridica de direito privado, inscrita no CNPJ sob o n XX, "
        "com sede em ...'"
    )
    new_pj = (
        "'pessoa juridica de direito privado, inscrita no CNPJ sob o n <cnpj_reu dos "
        "dados ou [CNPJ - PREENCHER]>, com sede em <endereco_reu dos dados ou "
        "[ENDERECO DA SEDE - PREENCHER]>'"
    )
    if old_pj not in js:
        raise RuntimeError("regra PJ da identificacao do reu nao encontrada")
    return js.replace(old_pj, new_pj, 1)


def main() -> int:
    base = Path(__file__).resolve().parents[2]
    wf_path = base / "docs" / "n8n_workflow_contestar_por_peticao.json"
    wf = json.loads(wf_path.read_text(encoding="utf-8"))

    alvos = [
        ("Claude Extrator", patch_extrator),
        ("Claude Gerador de Contestacao", patch_gerador),
    ]

    mudou_algum = False
    for nome, patch_fn in alvos:
        node = next((n for n in wf["nodes"] if n["name"] == nome), None)
        if node is None:
            print(f"ERRO: node {nome} nao encontrado", file=sys.stderr)
            return 1
        js = node["parameters"]["jsCode"]
        if MARKER + "_" in js:
            print(f"{nome}: ja contem marker {MARKER}, pulando.")
            continue
        node["parameters"]["jsCode"] = patch_fn(js)
        mudou_algum = True
        print(f"{nome}: patch aplicado.")

    if not mudou_algum:
        print("Nada a fazer.")
        return 0

    wf["description"] = (
        wf.get("description", "")
        + " | PR18: anti-confissao (nao admite inadimplemento/nao promete juntada), "
        "endereco_reu+cnpj_reu+data_ajuizamento extraidos, marco prescricional "
        "calculado em codigo, proibido inventar numeros."
    )
    wf["updatedAt"] = "2026-06-09T22:30:00.000Z"

    wf_path.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"OK: {MARKER} aplicado em {wf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

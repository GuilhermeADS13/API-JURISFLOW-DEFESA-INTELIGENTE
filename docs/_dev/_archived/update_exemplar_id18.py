"""Atualiza o exemplar curado id=18 com conteudo da peca humana real (CONTESTACAO.pdf).

Roda dentro do container: docker exec autojuri_backend python /app/docs/_dev/update_exemplar_id18.py
ou via subprocess externo apontando para o backend.

A peca humana real (Genner Trindade Advogados, processo Rosineide x CONTEC) tem
estrategia mais agressiva que a IA gerou inicialmente. Substituimos o sintetico
do id=18 por esse paradigma real.
"""

import json
import sys

sys.path.insert(0, "/app")

from App.database import _get_connection
from App.services.embedding_service import gerar_embedding


MINUTA_EXEMPLAR = {
    "resumo_estrategico": (
        "Caso paradigma: trabalhadora terceirizada (merendeira) que se afastou ANTES "
        "do termino do contrato administrativo entre a CONTEC e a Secretaria de "
        "Educacao do Estado de PE. Estrategia: 1) preliminares processuais robustas "
        "(prescricao quinquenal, incompetencia previdenciaria, limitacao da condenacao, "
        "INEPCIA por pedidos nao liquidados, juizo 100% digital, justica gratuita PARA "
        "A RECLAMADA por crise financeira, prescricao); 2) tese central: NAO houve "
        "dispensa imotivada — a autora se ausentou antes mesmo do encerramento do "
        "contrato administrativo (rescisao indireta CAMUFLADA → pedido de demissao); "
        "3) imputacao da causa do nao-pagamento ao Tomador (Secretaria nao pagou "
        "notas/faturas); 4) impugnacao de insalubridade com prova emprestada (laudos "
        "periciais de processos similares concluiram SALUBRE); 5) litigancia de ma-fe; "
        "6) impugnacao de danos morais por ausencia de ato ilicito + dano + nexo."
    ),
    "tese_central": (
        "A Reclamante NAO foi dispensada — ela se ausentou voluntariamente do trabalho "
        "ANTES do encerramento do contrato administrativo, configurando PEDIDO DE "
        "DEMISSAO (rescisao indireta camuflada). A impossibilidade temporaria de "
        "pagamento de salarios e FGTS dos meses finais decorreu de mora do Tomador "
        "(Secretaria de Educacao de PE) no adimplemento das notas/faturas, "
        "circunstancia objetiva alheia a vontade da Reclamada que afasta a mora "
        "culposa exigida pelos arts. 467 e 477 da CLT. Aplicacao do dever de mitigar "
        "as perdas (duty to mitigate the loss) — autora deveria ter aguardado o "
        "saneamento das pendencias em mediacao sindical/MTE, e nao ajuizar acao "
        "duplicando pedidos ja contemplados na acao coletiva do sindicato."
    ),
    "pontos_atendidos": [
        "Prescricao quinquenal: parcelas anteriores a 04/04/2021 prescritas (art. 7 XXIX CF; art. 11 CLT)",
        "Incompetencia para contribuicoes previdenciarias do curso do contrato (Sumula 368 TST; Sumula Vinculante 53 STF)",
        "Limitacao da condenacao aos valores atribuidos a cada pedido (art. 840 par. 1 CLT; arts. 141 e 492 CPC)",
        "Inepcia dos pedidos nao liquidados, em especial adicional de insalubridade (art. 840 par. 1 CLT; art. 485 I CPC)",
        "Juizo 100% digital — sede em Paulista/PE (regiao metropolitana do Recife), distancia de 500km/8h da Vara de Petrolina",
        "Justica gratuita pra Reclamada — crise economica-financeira (a empresa esta encerrando suas atividades)",
        "Modalidade rescisoria: pedido de demissao (rescisao indireta camuflada), nao dispensa imotivada — afasta multas 467/477 CLT",
        "FGTS dos meses junho-novembro/2025 nao depositado por mora do Tomador (Secretaria de Educacao) no pagamento de notas/faturas",
        "Diferencas CCT 2025: pagas apenas janeiro-fevereiro/2025 (R$ 228,62), salario atualizado para R$ 1.638,39 em marco/2025",
        "Desconto de R$ 333,65 em set/2024: estorno legitimo do adiantamento da diferenca CCT 2024 (art. 462 CLT) — bis in idem evitado",
        "Ferias 2022/2023 e 2023/2024 ja gozadas e pagas; ferias 2024/2025 ainda em periodo concessivo (sem dobra do art. 137)",
        "Jornada: 07:00-17:00 seg-qui + 07:00-16:00 sex = 44h semanais, com 1h intrajornada — comprovada por fichas de ponto assinadas",
        "Insalubridade: ambiente escolar SALUBRE — prova emprestada do processo 0000557-82.2024.5.06.0412 (TRT06)",
        "EPIs fornecidos + PCMSO NR-7 + PPRA juntados aos autos",
        "Vale-transporte fornecido em dinheiro (R$ 10/dia, anuencia do sindicato) — trajeto sem transporte publico regular",
        "Danos morais: ausencia dos requisitos (ato ilicito + dano + nexo) — Codigo Civil arts. 186 e 927",
        "Litigancia de ma-fe: Reclamante pleiteia verbas ja recebidas e narra inverdades (art. 793-A e seguintes CLT)",
        "Compensacao/deducao de tudo ja pago (art. 767 CLT) + retencao de contribuicoes previdenciarias e fiscais",
    ],
    "sintese": (
        "Defesa estruturada em sete preliminares (Constitucionalidade art. 790 CLT, "
        "Incompetencia Previdenciaria, Limitacao da Condenacao, Inepcia, Juizo "
        "100% Digital, Justica Gratuita pra Reclamada, Prescricao Quinquenal) seguidas "
        "de merito dividido em quatro topicos (II.A Contrato/Rescisao/Multas/Verbas; "
        "II.B Salarios em Atraso/Diferencas CCT/FGTS; II.C Ferias/Vale-Transporte/"
        "Desconto Set-24/Horas Extras/Intrajornada; II.D Insalubridade/EPIs/PCMSO/PPRA/"
        "Prova Emprestada), com topico autonomo de Litigancia de Ma-Fe e impugnacao "
        "especifica de Danos Morais. Encerra com pedidos preliminares + improcedencia "
        "total + condenacao em litigancia + compensacao/deducao."
    ),
    "fundamentos": (
        "**Constitucional:** art. 7 XXIX CF (prescricao quinquenal); art. 5 LXXIV CF "
        "(justica gratuita). **CLT:** art. 11 (prescricao); art. 71 par. 4 (intervalo "
        "intrajornada — natureza indenizatoria pos-Lei 13.467/2017); art. 137 (ferias "
        "em dobro); art. 186 c/c art. 927 CC (dano moral); art. 189/195 (insalubridade); "
        "art. 462 (vedacao de descontos nao autorizados); art. 467 (multa por verbas "
        "incontroversas); art. 477 (prazo e multa pelo pagamento das rescisorias); "
        "art. 790 par. 4 (comprovacao de insuficiencia para justica gratuita); "
        "art. 791-A (honorarios sucumbenciais 5%-15%); art. 793-A e seguintes "
        "(litigancia de ma-fe); art. 818 (onus da prova); art. 840 par. 1 (pedido "
        "certo, determinado e com valor); art. 847 (apresentacao da contestacao); "
        "art. 876 par. unico (competencia JT para previdenciarias do objeto da "
        "condenacao); art. 830 (autenticidade dos documentos). **CPC:** art. 141 e "
        "492 (julgamento nos limites da lide); art. 292 (limitacao ao valor da causa); "
        "art. 373 I (onus do autor); art. 485 I (inepcia); art. 487 II (extincao com "
        "resolucao por prescricao); art. 767 CLT (compensacao). **CC:** arts. 186, "
        "187 e 927 (ato ilicito e obrigacao de reparar). **NR-15 Portaria 3214/78** + "
        "Portaria MTP 426/2021 (insalubridade ao calor — limites de tolerancia e "
        "medidas preventivas). **Sumulas:** 331 TST (responsabilidade subsidiaria do "
        "tomador); 368 TST (competencia previdenciarias); 448 TST (insalubridade exige "
        "pericia); Sumula Vinculante 53 STF (execucao de oficio); Sumula 427 TST "
        "(publicacoes em nome do patrono). **Leis especiais:** Lei 7.418/1985 "
        "(vale-transporte — desconto de 6% do salario); Lei 8.036/1990 (FGTS); "
        "Lei 12.506/2011 (aviso previo proporcional); Lei 13.467/2017 (Reforma "
        "Trabalhista); Lei 8.666/1993 art. 71 par. 1 (responsabilidade do contratante "
        "publico); Lei 1.060/50 (gratuidade). **Doutrina:** dutty to mitigate the loss "
        "(dever de mitigar as perdas). **Prova emprestada:** processo "
        "0000557-82.2024.5.06.0412 (2a Vara do Trabalho de Petrolina-PE) — laudo "
        "pericial conclui ambiente escolar SALUBRE para merendeira."
    ),
    "pedidos": (
        "(a) Preliminarmente, julgamento a luz da Lei 13.467/2017 com indeferimento "
        "da justica gratuita pretendida pela Reclamante (ausencia de comprovacao "
        "ex art. 790 par. 4 CLT); "
        "(b) Preliminarmente, declaracao de incompetencia absoluta para contribuicoes "
        "previdenciarias do curso do contrato (Sumula 368 TST + SV 53 STF); "
        "(c) Preliminarmente, limitacao da condenacao aos valores atribuidos a cada "
        "pedido (art. 840 par. 1 CLT + arts. 141 e 492 CPC); "
        "(d) Preliminarmente, reconhecimento da inepcia dos pedidos nao liquidados, "
        "em especial o adicional de insalubridade, com extincao sem resolucao do "
        "merito (art. 485 I CPC); "
        "(e) Deferimento do Juizo 100% Digital com realizacao das audiencias em "
        "ambiente virtual (sede da Reclamada em Paulista/PE, 500km da Vara); "
        "(f) Deferimento da JUSTICA GRATUITA pra Reclamada (crise economico-financeira); "
        "(g) Declaracao da prescricao quinquenal das parcelas anteriores a 04/04/2021 "
        "(art. 7 XXIX CF; art. 11 CLT) com extincao parcial com resolucao do merito "
        "(art. 487 II CPC); "
        "(h) No merito, IMPROCEDENCIA TOTAL de todos os pedidos, com reconhecimento de "
        "que o contrato findou por PEDIDO DE DEMISSAO da Reclamante (rescisao indireta "
        "camuflada); "
        "(i) Condenacao da Reclamante em LITIGANCIA DE MA-FE (arts. 793-A e seguintes "
        "CLT) e em honorarios sucumbenciais (art. 791-A CLT); "
        "(j) Por cautela, em caso de procedencia parcial: compensacao e deducao de "
        "tudo ja pago (art. 767 CLT) + retencao das contribuicoes previdenciarias e "
        "fiscais incidentes (Sumula 368 TST); "
        "(k) Publicacoes exclusivamente em nome do patrono Genner Trindade, OAB/PE "
        "27.790, sob pena de nulidade (Sumula 427 TST)."
    ),
    "observacoes": (
        "EXEMPLAR CURADO baseado em peca humana real (Genner Trindade Advogados, "
        "processo 0000420-35.2026.5.06.0411 Rosineide x CONTEC, audiencia 24/05/2026). "
        "Padroes a replicar: 1) cabecalho com CNPJ + endereco completo da Reclamada; "
        "2) preliminares enumeradas A-G (com Inepcia, Juizo Digital e Gratuidade Re); "
        "3) merito com subsecoes II.A/II.B/II.C/II.D (cada uma ja contem impugnacao); "
        "4) tese de pedido de demissao por abandono antes do encerramento + dutty to "
        "mitigate the loss; 5) prova emprestada e referencia a acoes coletivas do "
        "sindicato + mediacoes MTE e CEJUSC TRT06; 6) Litigancia de Ma-Fe como topico "
        "III autonomo; 7) assinatura: Recife/PE + Genner Trindade + OAB/PE 27.790."
    ),
    "riscos": [
        "Ausencia ou irregularidade nos cartoes de ponto inverte o onus (Sumula 338 TST) — confirmar integridade dos registros",
        "Justica gratuita pra Reclamada (PJ) exige comprovacao robusta da crise — juntar balanco patrimonial",
        "Sem prova emprestada juntada e identificada por nro de processo, juiz pode determinar pericia",
        "Inepcia da inicial deve ser arguida de plano — pode preclusao se discutida apenas no merito",
        "Acao coletiva do sindicato cobrindo a Reclamante pode ser desafio: confirmar substituicao processual com sindicato",
    ],
}


def main() -> None:
    fatos_texto = (
        "Reclamacao Trabalhista 0000420-35.2026.5.06.0411. Reclamante: ROSINEIDE DOS SANTOS "
        "(merendeira/cozinheira terceirizada). Reclamada: CONTEC SERVICOS TERCEIRIZADOS LTDA "
        "(CNPJ 20.800.899/0001-34, sede em Paulista/PE). Tomador: Secretaria de Educacao do "
        "Estado de Pernambuco (Contrato 043/2019 SEE/PE). Admissao: 04/06/2019. Encerramento "
        "do contrato administrativo: 21/11/2025. Salario CCT/2025: R$ 1.638,39 (anterior R$ "
        "1.524,08). Pedidos do autor: ferias, 13o, aviso previo, saldo salario, FGTS+40%, "
        "multa arts. 467 e 477 CLT, danos morais, intervalo intrajornada, horas extras, "
        "vale-transporte, desconto de R$ 333,65 em set/2024, diferencas salariais, "
        "adicional de insalubridade grau medio, seguro-desemprego, baixa CTPS, bloqueio "
        "judicial de R$ 25.000."
    )
    pedido_autor_texto = (
        "Ferias 2022-2025 com dobra; 13o 2024/2025; aviso previo 45 dias; saldo salario "
        "novembro/2025; FGTS mensal + multa 40%; multas arts. 467 e 477 CLT; "
        "seguro-desemprego; danos morais R$ 10.000; intervalo intrajornada suprimido; "
        "horas extras (07h-17h); vale-transporte R$ 10/dia; devolucao em dobro do "
        "desconto de R$ 333,65 (set/2024); diferencas salariais R$ 15.000; insalubridade "
        "grau medio 20%; tutela de bloqueio de R$ 25.000; baixa CTPS."
    )
    embedding_input = f"{fatos_texto}\n\n{pedido_autor_texto}".strip()

    with _get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE contestacoes SET n8n_resposta = %s::jsonb, fatos = %s, pedido_autor = %s WHERE id = 18",
            (
                json.dumps(
                    {
                        "status": "ok",
                        "minuta": MINUTA_EXEMPLAR,
                        "engine_ia": {
                            "provider": "humano",
                            "model": "exemplar_curado",
                            "fonte": "Genner Trindade Advogados",
                        },
                    },
                    ensure_ascii=False,
                ),
                fatos_texto,
                pedido_autor_texto,
            ),
        )
        conn.commit()
        print("[1/2] n8n_resposta + fatos + pedido_autor atualizados no id=18")

    emb = gerar_embedding(embedding_input)
    if not emb:
        print("[ERRO] gerar_embedding retornou vazio")
        return

    with _get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE contestacoes SET fatos_embedding = %s::vector WHERE id = 18",
            (str(emb),),
        )
        conn.commit()
        print(f"[2/2] fatos_embedding regerado ({len(emb)} dims)")

    print("OK — exemplar id=18 atualizado com paradigma humano real")


if __name__ == "__main__":
    main()

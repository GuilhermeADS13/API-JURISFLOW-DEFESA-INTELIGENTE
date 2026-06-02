
// Dados mockados para cards, selects e historico da interface.
export const stats = [
  {
    label: "Tempo médio por defesa",
    value: "~5 min",
    detail: "Do upload da petição ao DOCX pronto pra baixar",
  },
  {
    label: "Citações verificadas",
    value: "100%",
    detail: "Toda jurisprudência e artigo são checados antes da entrega",
  },
  {
    label: "Estilo adaptativo",
    value: "DOCX",
    detail: "Fonte, espaçamento e cabeçalho copiados do modelo enviado",
  },
  {
    label: "Aprendizado contínuo",
    value: "RAG",
    detail: "Cada peça aprovada enriquece a base de defesas do escritório",
  },
];

// Lista plana de ramos juridicos (legado, ainda usada em outros lugares do app).
export const legalBranches = [
  "Direito Civil",
  "Direito do Consumidor",
  "Direito Empresarial",
  "Direito Contratual",
  "Direito Imobiliário",
  "Direito de Família e Sucessões",
  "Direito do Trabalho",
  "Direito Previdenciário",
  "Direito Tributário",
  "Direito Administrativo",
  "Direito Constitucional",
  "Direito Penal",
  "Direito Ambiental",
  "Direito Digital",
  "Direito Bancário e Financeiro",
  "Direito Eleitoral",
  "Direito Agrário",
  "Direito Médico e da Saúde",
  "Direito Marítimo e Aeronáutico",
];

/**
 * Mesmos ramos agrupados por categoria para uso com <optgroup> no select do
 * formulario principal. Ordem das categorias e dos itens dentro de cada
 * categoria foi escolhida pra colocar ramos mais usados (Trabalhista, Civil,
 * Consumidor) mais acessiveis. PR6 P3.4.
 */
export const legalBranchGroups = {
  "Trabalhista e Previdenciário": [
    "Direito do Trabalho",
    "Direito Previdenciário",
  ],
  "Civil e Empresarial": [
    "Direito Civil",
    "Direito Empresarial",
    "Direito Contratual",
    "Direito Imobiliário",
    "Direito de Família e Sucessões",
  ],
  "Público e Regulatório": [
    "Direito Tributário",
    "Direito Administrativo",
    "Direito Constitucional",
    "Direito Ambiental",
    "Direito Eleitoral",
  ],
  Especializado: [
    "Direito do Consumidor",
    "Direito Penal",
    "Direito Digital",
    "Direito Bancário e Financeiro",
    "Direito Agrário",
    "Direito Médico e da Saúde",
    "Direito Marítimo e Aeronáutico",
  ],
};

/**
 * Subtipos especificos por ramo. Quando o usuario escolhe um ramo no select
 * principal, este dicionario alimenta um segundo select condicional com tipos
 * mais granulares — o RAG semantico usa o subtipo (quando preenchido) em vez
 * do ramo generico, melhorando a precisao da busca de defesas similares. PR6 P2.2.
 *
 * Cobertura inicial: ramos mais usados na pratica. Ramo sem entrada aqui
 * mantem comportamento atual (envia somente o tipo_acao generico).
 */
export const subtiposAcao = {
  "Direito do Trabalho": [
    "Horas Extras",
    "Rescisão Indireta",
    "Danos Morais Trabalhistas",
    "FGTS",
    "Adicional de Insalubridade",
    "Adicional de Periculosidade",
    "Acidente de Trabalho",
    "Equiparação Salarial",
    "Jornada de Trabalho",
    "Vínculo Empregatício",
  ],
  "Direito do Consumidor": [
    "Cobrança Indevida",
    "Dano Moral por Negativação",
    "Produto Defeituoso",
    "Rescisão de Contrato",
    "Propaganda Enganosa",
    "Recusa de Atendimento",
  ],
  "Direito Civil": [
    "Responsabilidade Civil",
    "Inadimplemento Contratual",
    "Reparação de Danos",
    "Posse e Propriedade",
    "Indenização por Danos Morais",
  ],
  "Direito Previdenciário": [
    "Aposentadoria por Idade",
    "Aposentadoria por Invalidez",
    "Auxílio-Doença",
    "Pensão por Morte",
    "Benefício de Prestação Continuada (BPC)",
  ],
  "Direito Tributário": [
    "Execução Fiscal",
    "Repetição de Indébito",
    "ICMS",
    "ISS",
    "Imposto de Renda",
  ],
  "Direito Bancário e Financeiro": [
    "Revisão de Contrato Bancário",
    "Juros Abusivos",
    "Tarifas Indevidas",
    "Cartão de Crédito",
    "Financiamento Veicular",
  ],
};

// Historico inicial apresentado no dashboard.
export const historyItems = [
  {
    id: "CTR-2026-001",
    naturezaCaso: "Direito do Trabalho",
    status: "Concluída",
    data: "10/03/2026",
    tipo: "Defesa editada",
  },
  {
    id: "CTR-2026-002",
    naturezaCaso: "Direito Tributário",
    status: "Em análise",
    data: "10/03/2026",
    tipo: "Revisão de fundamentação",
  },
  {
    id: "CTR-2026-003",
    naturezaCaso: "Direito do Consumidor",
    status: "Aguardando revisão",
    data: "09/03/2026",
    tipo: "Defesa editada",
  },
];

// Regras de uso exibidas ao lado do editor da defesa.
export const agentRules = [
  "Não alterar dados processuais sensíveis.",
  "Não inventar jurisprudência nem citações.",
  "Manter linguagem jurídica formal e objetiva.",
  "Atuar apenas na edição da peça base.",
];

// Cards de resumo no topo da tela de dashboard.
export const dashboardCards = [
  { label: "Casos em processamento", value: "07" },
  { label: "Aguardando advogado", value: "14" },
  { label: "Prontas para exportação", value: "22" },
  { label: "Precisão média do agente", value: "96%" },
];

// Opcoes de categoria exibidas no formulario de suporte.
export const supportIssueTypes = [
  "Atraso na geração da defesa",
  "Erro na minuta sugerida",
  "Problema de upload de arquivo",
  "Falha de login ou sessão",
  "Outro",
];

// Itens orientativos para o cliente preencher uma reclamacao completa.
export const supportChecklist = [
  "Explique o que aconteceu e qual impacto no seu caso.",
  "Informe o número do processo quando houver relação direta.",
  "Descreva horário aproximado e etapa em que ocorreu a falha.",
  "Inclua expectativas de retorno para priorização adequada.",
];

// Canais e SLA exibidos na lateral da aba de suporte.
export const supportChannels = [
  "Recebimento automático por e-mail do time de suporte",
  "Triagem inicial em até 2 horas úteis",
  "Atualizações por e-mail durante o tratamento",
];

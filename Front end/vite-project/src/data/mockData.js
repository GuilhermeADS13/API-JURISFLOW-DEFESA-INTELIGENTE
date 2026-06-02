
// Dados mockados para cards, selects e historico da interface.
export const stats = [
  {
    label: "Tempo medio por defesa",
    value: "~5 min",
    detail: "Do upload da peticao ao DOCX pronto pra baixar",
  },
  {
    label: "Citacoes verificadas",
    value: "100%",
    detail: "Toda jurisprudencia e artigo sao checados antes da entrega",
  },
  {
    label: "Estilo adaptativo",
    value: "DOCX",
    detail: "Fonte, espacamento e cabecalho copiados do modelo enviado",
  },
  {
    label: "Aprendizado continuo",
    value: "RAG",
    detail: "Cada peca aprovada enriquece a base de defesas do escritorio",
  },
];

// Lista plana de ramos juridicos (legado, ainda usada em outros lugares do app).
export const legalBranches = [
  "Direito Civil",
  "Direito do Consumidor",
  "Direito Empresarial",
  "Direito Contratual",
  "Direito Imobiliario",
  "Direito de Familia e Sucessoes",
  "Direito do Trabalho",
  "Direito Previdenciario",
  "Direito Tributario",
  "Direito Administrativo",
  "Direito Constitucional",
  "Direito Penal",
  "Direito Ambiental",
  "Direito Digital",
  "Direito Bancario e Financeiro",
  "Direito Eleitoral",
  "Direito Agrario",
  "Direito Medico e da Saude",
  "Direito Maritimo e Aeronautico",
];

/**
 * Mesmos ramos agrupados por categoria para uso com <optgroup> no select do
 * formulario principal. Ordem das categorias e dos itens dentro de cada
 * categoria foi escolhida pra colocar ramos mais usados (Trabalhista, Civil,
 * Consumidor) mais acessiveis. PR6 P3.4.
 */
export const legalBranchGroups = {
  "Trabalhista e Previdenciario": [
    "Direito do Trabalho",
    "Direito Previdenciario",
  ],
  "Civil e Empresarial": [
    "Direito Civil",
    "Direito Empresarial",
    "Direito Contratual",
    "Direito Imobiliario",
    "Direito de Familia e Sucessoes",
  ],
  "Publico e Regulatorio": [
    "Direito Tributario",
    "Direito Administrativo",
    "Direito Constitucional",
    "Direito Ambiental",
    "Direito Eleitoral",
  ],
  Especializado: [
    "Direito do Consumidor",
    "Direito Penal",
    "Direito Digital",
    "Direito Bancario e Financeiro",
    "Direito Agrario",
    "Direito Medico e da Saude",
    "Direito Maritimo e Aeronautico",
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
    "Rescisao Indireta",
    "Danos Morais Trabalhistas",
    "FGTS",
    "Adicional de Insalubridade",
    "Adicional de Periculosidade",
    "Acidente de Trabalho",
    "Equiparacao Salarial",
    "Jornada de Trabalho",
    "Vinculo Empregaticio",
  ],
  "Direito do Consumidor": [
    "Cobranca Indevida",
    "Dano Moral por Negativacao",
    "Produto Defeituoso",
    "Rescisao de Contrato",
    "Propaganda Enganosa",
    "Recusa de Atendimento",
  ],
  "Direito Civil": [
    "Responsabilidade Civil",
    "Inadimplemento Contratual",
    "Reparacao de Danos",
    "Posse e Propriedade",
    "Indenizacao por Danos Morais",
  ],
  "Direito Previdenciario": [
    "Aposentadoria por Idade",
    "Aposentadoria por Invalidez",
    "Auxilio-Doenca",
    "Pensao por Morte",
    "Beneficio de Prestacao Continuada (BPC)",
  ],
  "Direito Tributario": [
    "Execucao Fiscal",
    "Repeticao de Indebito",
    "ICMS",
    "ISS",
    "Imposto de Renda",
  ],
  "Direito Bancario e Financeiro": [
    "Revisao de Contrato Bancario",
    "Juros Abusivos",
    "Tarifas Indevidas",
    "Cartao de Credito",
    "Financiamento Veicular",
  ],
};

// Historico inicial apresentado no dashboard.
export const historyItems = [
  {
    id: "CTR-2026-001",
    naturezaCaso: "Direito do Trabalho",
    status: "Concluida",
    data: "10/03/2026",
    tipo: "Defesa editada",
  },
  {
    id: "CTR-2026-002",
    naturezaCaso: "Direito Tributario",
    status: "Em analise",
    data: "10/03/2026",
    tipo: "Revisao de fundamentacao",
  },
  {
    id: "CTR-2026-003",
    naturezaCaso: "Direito do Consumidor",
    status: "Aguardando revisao",
    data: "09/03/2026",
    tipo: "Defesa editada",
  },
];

// Regras de uso exibidas ao lado do editor da defesa.
export const agentRules = [
  "Nao alterar dados processuais sensiveis.",
  "Nao inventar jurisprudencia nem citacoes.",
  "Manter linguagem juridica formal e objetiva.",
  "Atuar apenas na edicao da peca base.",
];

// Cards de resumo no topo da tela de dashboard.
export const dashboardCards = [
  { label: "Casos em processamento", value: "07" },
  { label: "Aguardando advogado", value: "14" },
  { label: "Prontas para exportacao", value: "22" },
  { label: "Precisao media do agente", value: "96%" },
];

// Opcoes de categoria exibidas no formulario de suporte.
export const supportIssueTypes = [
  "Atraso na geracao da defesa",
  "Erro na minuta sugerida",
  "Problema de upload de arquivo",
  "Falha de login ou sessao",
  "Outro",
];

// Itens orientativos para o cliente preencher uma reclamacao completa.
export const supportChecklist = [
  "Explique o que aconteceu e qual impacto no seu caso.",
  "Informe o numero do processo quando houver relacao direta.",
  "Descreva horario aproximado e etapa em que ocorreu a falha.",
  "Inclua expectativas de retorno para priorizacao adequada.",
];

// Canais e SLA exibidos na lateral da aba de suporte.
export const supportChannels = [
  "Recebimento automatico por e-mail do time de suporte",
  "Triagem inicial em ate 2 horas uteis",
  "Atualizacoes por e-mail durante o tratamento",
];

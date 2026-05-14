
// Dados mockados para cards, selects e historico da interface.
export const stats = [
  {
    label: "Tempo medio por defesa",
    value: "3m42s",
    detail: "Do envio ao texto inicial pronto para revisao",
  },
  {
    label: "Capacidade por equipe",
    value: "+240%",
    detail: "Mais casos tratados sem ampliar a operacao",
  },
  {
    label: "Conformidade da peca",
    value: "96%",
    detail: "Saidas alinhadas ao padrao juridico do escritorio",
  },
  {
    label: "Fluxos em producao",
    value: "32",
    detail: "Operacoes juridicas ativas na plataforma",
  },
];

// Lista de ramos juridicos exibida no select do formulario.
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

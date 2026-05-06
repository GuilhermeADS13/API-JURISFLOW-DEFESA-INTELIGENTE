/**
 * Enderecos centralizados da API.
 * Facilita mudanca de ambientes sem alterar varios arquivos.
 */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";
export const AGENT_API_URL = import.meta.env.VITE_IA_ENDPOINT || `${API_BASE_URL}/gerar-contestacao`;
export const SUPPORT_CONTACT_API_URL =
  import.meta.env.VITE_SUPPORT_CONTACT_ENDPOINT || `${API_BASE_URL}/suporte/contato`;
export const DASHBOARD_SUMMARY_API_URL =
  import.meta.env.VITE_DASHBOARD_SUMMARY_ENDPOINT || `${API_BASE_URL}/contestacoes/resumo`;
export const PETICAO_API_URL =
  import.meta.env.VITE_PETICAO_ENDPOINT || `${API_BASE_URL}/contestar-por-peticao`;

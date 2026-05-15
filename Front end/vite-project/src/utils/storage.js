/**
 * Chave do rascunho local.
 * Mantem campos do formulario para recuperar trabalho nao enviado.
 *
 * v3 (Guia Tecnico v2): rascunho guarda o modo de entrada ('manual'|'peticao').
 * v4 (PR6): campos renomeados — cliente->autor, tese->pedidoAutor,
 *           observacoes->fatos, e novo campo reu. Migracao silenciosa preserva
 *           os valores do usuario sem forcar repreenchimento.
 */
export const DRAFT_STORAGE_KEY = "jurisflow:draft:v3";
const DRAFT_STORAGE_KEY_LEGACY_V2 = "jurisflow:draft:v2";

/**
 * Migra um objeto `form` com nomes antigos (cliente/tese/observacoes) para o
 * shape novo (autor/pedidoAutor/fatos + reu). Idempotente: se ja estiver no
 * shape novo, retorna sem alteracao. Valores ausentes viram string vazia para
 * evitar undefined.trim() em handlers.
 */
export function migrateFormFields(form) {
  if (!form || typeof form !== "object") return form;

  const next = { ...form };

  if (next.autor === undefined && typeof next.cliente === "string") {
    next.autor = next.cliente;
  }
  if (next.pedidoAutor === undefined && typeof next.tese === "string") {
    next.pedidoAutor = next.tese;
  }
  if (next.fatos === undefined && typeof next.observacoes === "string") {
    next.fatos = next.observacoes;
  }

  // Remove os nomes antigos depois de copiar, para nao confundir o state.
  delete next.cliente;
  delete next.tese;
  delete next.observacoes;

  // Garante que todos os campos esperados existem (sem undefined).
  next.processo = typeof next.processo === "string" ? next.processo : "";
  next.autor = typeof next.autor === "string" ? next.autor : "";
  next.reu = typeof next.reu === "string" ? next.reu : "";
  next.tipoAcao = typeof next.tipoAcao === "string" ? next.tipoAcao : "";
  next.subtipoAcao = typeof next.subtipoAcao === "string" ? next.subtipoAcao : "";
  next.fatos = typeof next.fatos === "string" ? next.fatos : "";
  next.pedidoAutor = typeof next.pedidoAutor === "string" ? next.pedidoAutor : "";

  return next;
}

/**
 * Chave da sessao local (somente dados de perfil, sem token sensivel).
 */
export const AUTH_SESSION_STORAGE_KEY = "jurisflow:auth:session:v2";
/**
 * Le o rascunho salvo no navegador.
 */
export function readDraftFromStorage() {
  if (typeof window === "undefined") {
    return { form: null, info: "" };
  }

  try {
    let saved = window.localStorage.getItem(DRAFT_STORAGE_KEY);

    // Migracao v2 -> v3: se o usuario tinha rascunho na chave antiga, lemos
    // dela e injetamos modo='manual' (comportamento padrao do v2).
    if (!saved) {
      const legacy = window.localStorage.getItem(DRAFT_STORAGE_KEY_LEGACY_V2);
      if (legacy) {
        try {
          const parsedLegacy = JSON.parse(legacy);
          const migrated = {
            ...parsedLegacy,
            form: { ...(parsedLegacy.form || {}), modo: "manual" },
          };
          window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(migrated));
          window.localStorage.removeItem(DRAFT_STORAGE_KEY_LEGACY_V2);
          saved = JSON.stringify(migrated);
        } catch {
          // Se v2 corrompido, ignora e segue com rascunho vazio.
        }
      }
    }

    if (!saved) return { form: null, info: "" };

    const parsed = JSON.parse(saved);
    const migratedForm = parsed.form ? migrateFormFields(parsed.form) : null;
    return {
      form: migratedForm,
      info: parsed.savedAt ? `Rascunho recuperado: ${parsed.savedAt}` : "",
    };
  } catch {
    return {
      form: null,
      info: "Nao foi possivel recuperar o rascunho salvo.",
    };
  }
}

/**
 * Persiste rascunho da tela principal.
 */
export function persistDraft(payload) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(payload));
}

/**
 * Le sessao local (perfil), sem depender de token no navegador.
 */
export function readStoredSession() {
  if (typeof window === "undefined") return null;

  try {
    const saved = window.localStorage.getItem(AUTH_SESSION_STORAGE_KEY);
    if (!saved) return null;
    return JSON.parse(saved);
  } catch {
    return null;
  }
}

/**
 * Salva dados nao sensiveis da conta no browser.
 */
export function persistSession(session) {
  if (typeof window === "undefined") return;
  const safeSession = {
    id: session?.id || "",
    name: session?.name || "Conta",
    email: session?.email || "",
  };
  window.localStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify(safeSession));
}

/**
 * Remove sessao local ao sair da conta.
 */
export function clearSession() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
}


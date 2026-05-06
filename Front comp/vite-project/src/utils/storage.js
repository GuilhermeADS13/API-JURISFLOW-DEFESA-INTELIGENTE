/**
 * Chave do rascunho local.
 * Mantem campos do formulario para recuperar trabalho nao enviado.
 *
 * v3 (Guia Tecnico v2): rascunho passa a guardar o modo de entrada
 * ('manual' | 'peticao'). Migramos v2 silenciosamente para v3 mantendo
 * modo='manual' (comportamento anterior).
 */
export const DRAFT_STORAGE_KEY = "jurisflow:draft:v3";
const DRAFT_STORAGE_KEY_LEGACY_V2 = "jurisflow:draft:v2";

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
    return {
      form: parsed.form || null,
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


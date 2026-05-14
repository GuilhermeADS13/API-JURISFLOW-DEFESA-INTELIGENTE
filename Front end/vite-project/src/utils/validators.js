/**
 * Regex de e-mail para validacao basica no front.
 */
export const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/i;

/**
 * Regex do numero CNJ, alinhada com validacao do backend.
 */
export const PROCESSO_REGEX = /^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$/;

export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 128;

/**
 * Normaliza e-mail para comparacoes e persistencia.
 */
export function normalizeEmail(value) {
  return (value || "").trim().toLowerCase();
}

/**
 * Verifica formato do e-mail informado.
 */
export function isValidEmail(value) {
  return EMAIL_REGEX.test(normalizeEmail(value));
}

/**
 * Extrai mensagem util de erro retornado pela API.
 */
export async function getApiErrorMessage(response, fallbackMessage) {
  try {
    const data = await response.json();
    if (typeof data?.detail === "string" && data.detail.trim()) {
      return data.detail;
    }
    if (typeof data?.message === "string" && data.message.trim()) {
      return data.message;
    }
  } catch {
    // Mantem fallback se nao for possivel interpretar JSON.
  }

  return fallbackMessage;
}

/**
 * Checks visuais de senha para orientar o usuario.
 */
export function getPasswordChecks(value) {
  const password = value || "";
  return {
    minLength: password.length >= PASSWORD_MIN_LENGTH,
    hasUppercase: /[A-Z]/.test(password),
    hasLowercase: /[a-z]/.test(password),
    hasNumber: /\d/.test(password),
    hasSymbol: /[^A-Za-z0-9]/.test(password),
    maxLength: password.length <= PASSWORD_MAX_LENGTH,
  };
}

/**
 * Regra de validacao para cada campo do modal de autenticacao.
 */
export function validateAuthField(name, value, mode) {
  const fieldValue = value || "";

  if (name === "name") {
    if (mode !== "signup") return "";
    if (!fieldValue.trim()) return "Informe o nome para criar a conta.";
    if (fieldValue.trim().length < 3) return "Use pelo menos 3 caracteres no nome.";
    return "";
  }

  if (name === "email") {
    if (!fieldValue.trim()) return "Informe o e-mail.";
    if (!isValidEmail(fieldValue)) return "Informe um e-mail valido.";
    return "";
  }

  if (name === "password") {
    if (!fieldValue.trim()) return "Informe a senha.";

    if (mode === "signup") {
      const checks = getPasswordChecks(fieldValue);
      if (!checks.minLength || !checks.hasUppercase || !checks.hasLowercase || !checks.hasNumber || !checks.hasSymbol) {
        return "A senha deve ter 8+ caracteres, com maiuscula, minuscula, numero e simbolo.";
      }
    }

    return "";
  }

  return "";
}

/**
 * Valida numero de processo CNJ no cliente.
 */
export function isValidNumeroProcesso(value) {
  return PROCESSO_REGEX.test((value || "").trim());
}

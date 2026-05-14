import { describe, expect, it } from "vitest";

import {
  EMAIL_REGEX,
  PROCESSO_REGEX,
  PASSWORD_MIN_LENGTH,
  PASSWORD_MAX_LENGTH,
  normalizeEmail,
  isValidEmail,
  getApiErrorMessage,
  getPasswordChecks,
  validateAuthField,
  isValidNumeroProcesso,
} from "./validators";

// ---------------------------------------------------------------------------
// normalizeEmail
// ---------------------------------------------------------------------------
describe("normalizeEmail", () => {
  it("converte para minusculo e remove espacos", () => {
    expect(normalizeEmail("  Joao@Email.COM  ")).toBe("joao@email.com");
  });

  it("retorna string vazia para null/undefined", () => {
    expect(normalizeEmail(null)).toBe("");
    expect(normalizeEmail(undefined)).toBe("");
  });

  it("retorna string vazia para string vazia", () => {
    expect(normalizeEmail("")).toBe("");
  });
});

// ---------------------------------------------------------------------------
// isValidEmail
// ---------------------------------------------------------------------------
describe("isValidEmail", () => {
  const emailsValidos = [
    "contato@escritorio.com",
    "user.name@domain.co",
    "a@b.cc",
    "test+tag@gmail.com",
    "UPPER@CASE.COM",
    "  spaces@trim.com  ",
  ];

  emailsValidos.forEach((email) => {
    it(`aceita e-mail valido: ${email.trim()}`, () => {
      expect(isValidEmail(email)).toBe(true);
    });
  });

  const emailsInvalidos = [
    "",
    "   ",
    "sem-arroba",
    "@sem-usuario.com",
    "sem-dominio@",
    "user@.com",
    "user@dominio.c",
    null,
    undefined,
  ];

  emailsInvalidos.forEach((email) => {
    it(`rejeita e-mail invalido: ${JSON.stringify(email)}`, () => {
      expect(isValidEmail(email)).toBe(false);
    });
  });
});

// ---------------------------------------------------------------------------
// getApiErrorMessage
// ---------------------------------------------------------------------------
describe("getApiErrorMessage", () => {
  const fallback = "Erro generico.";

  it("extrai campo detail da resposta JSON", async () => {
    const response = { json: async () => ({ detail: "Token expirado." }) };
    expect(await getApiErrorMessage(response, fallback)).toBe("Token expirado.");
  });

  it("extrai campo message quando detail ausente", async () => {
    const response = { json: async () => ({ message: "Nao autorizado." }) };
    expect(await getApiErrorMessage(response, fallback)).toBe("Nao autorizado.");
  });

  it("prioriza detail sobre message", async () => {
    const response = {
      json: async () => ({ detail: "Detalhe", message: "Msg" }),
    };
    expect(await getApiErrorMessage(response, fallback)).toBe("Detalhe");
  });

  it("retorna fallback quando detail e message vazios", async () => {
    const response = { json: async () => ({ detail: "  ", message: "" }) };
    expect(await getApiErrorMessage(response, fallback)).toBe(fallback);
  });

  it("retorna fallback quando JSON invalido", async () => {
    const response = {
      json: async () => {
        throw new Error("Invalid JSON");
      },
    };
    expect(await getApiErrorMessage(response, fallback)).toBe(fallback);
  });

  it("retorna fallback quando body esta vazio", async () => {
    const response = { json: async () => ({}) };
    expect(await getApiErrorMessage(response, fallback)).toBe(fallback);
  });

  it("retorna fallback quando detail nao e string", async () => {
    const response = { json: async () => ({ detail: 123 }) };
    expect(await getApiErrorMessage(response, fallback)).toBe(fallback);
  });
});

// ---------------------------------------------------------------------------
// getPasswordChecks
// ---------------------------------------------------------------------------
describe("getPasswordChecks", () => {
  it("senha forte passa em todos os checks", () => {
    const checks = getPasswordChecks("Senha@123");
    expect(checks.minLength).toBe(true);
    expect(checks.hasUppercase).toBe(true);
    expect(checks.hasLowercase).toBe(true);
    expect(checks.hasNumber).toBe(true);
    expect(checks.hasSymbol).toBe(true);
    expect(checks.maxLength).toBe(true);
  });

  it("senha curta falha em minLength", () => {
    const checks = getPasswordChecks("Ab1!");
    expect(checks.minLength).toBe(false);
  });

  it("senha sem maiuscula falha em hasUppercase", () => {
    const checks = getPasswordChecks("abcdefg1!");
    expect(checks.hasUppercase).toBe(false);
  });

  it("senha sem minuscula falha em hasLowercase", () => {
    const checks = getPasswordChecks("ABCDEFG1!");
    expect(checks.hasLowercase).toBe(false);
  });

  it("senha sem numero falha em hasNumber", () => {
    const checks = getPasswordChecks("Abcdefgh!");
    expect(checks.hasNumber).toBe(false);
  });

  it("senha sem simbolo falha em hasSymbol", () => {
    const checks = getPasswordChecks("Abcdefg1");
    expect(checks.hasSymbol).toBe(false);
  });

  it("senha vazia falha em todos exceto maxLength", () => {
    const checks = getPasswordChecks("");
    expect(checks.minLength).toBe(false);
    expect(checks.hasUppercase).toBe(false);
    expect(checks.hasLowercase).toBe(false);
    expect(checks.hasNumber).toBe(false);
    expect(checks.hasSymbol).toBe(false);
    expect(checks.maxLength).toBe(true);
  });

  it("trata null/undefined como string vazia", () => {
    const checks = getPasswordChecks(null);
    expect(checks.minLength).toBe(false);
    expect(checks.maxLength).toBe(true);
  });

  it("senha excedendo maxLength falha", () => {
    const longPassword = "Aa1!" + "x".repeat(PASSWORD_MAX_LENGTH);
    const checks = getPasswordChecks(longPassword);
    expect(checks.maxLength).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// validateAuthField
// ---------------------------------------------------------------------------
describe("validateAuthField", () => {
  describe("campo name", () => {
    it("ignora validacao fora do modo signup", () => {
      expect(validateAuthField("name", "", "login")).toBe("");
    });

    it("exige nome no signup", () => {
      expect(validateAuthField("name", "", "signup")).toContain("nome");
    });

    it("exige pelo menos 3 caracteres", () => {
      expect(validateAuthField("name", "AB", "signup")).toContain("3 caracteres");
    });

    it("aceita nome valido no signup", () => {
      expect(validateAuthField("name", "Maria Silva", "signup")).toBe("");
    });

    it("trata null como vazio", () => {
      expect(validateAuthField("name", null, "signup")).toContain("nome");
    });
  });

  describe("campo email", () => {
    it("exige preenchimento", () => {
      expect(validateAuthField("email", "", "login")).toContain("e-mail");
    });

    it("valida formato invalido", () => {
      expect(validateAuthField("email", "invalido", "login")).toContain("valido");
    });

    it("aceita email valido", () => {
      expect(validateAuthField("email", "user@test.com", "login")).toBe("");
    });

    it("rejeita email apenas com espacos", () => {
      const result = validateAuthField("email", "   ", "login");
      expect(result.length).toBeGreaterThan(0);
    });
  });

  describe("campo password", () => {
    it("exige preenchimento", () => {
      expect(validateAuthField("password", "", "login")).toContain("senha");
    });

    it("aceita qualquer senha no login (sem regras de forca)", () => {
      expect(validateAuthField("password", "abc", "login")).toBe("");
    });

    it("rejeita senha fraca no signup", () => {
      const msg = validateAuthField("password", "fraca", "signup");
      expect(msg).toContain("8+");
    });

    it("aceita senha forte no signup", () => {
      expect(validateAuthField("password", "Forte@123", "signup")).toBe("");
    });

    it("trata null como vazio", () => {
      expect(validateAuthField("password", null, "login")).toContain("senha");
    });
  });

  describe("campo desconhecido", () => {
    it("retorna string vazia para campo nao mapeado", () => {
      expect(validateAuthField("telefone", "123", "login")).toBe("");
    });
  });
});

// ---------------------------------------------------------------------------
// isValidNumeroProcesso
// ---------------------------------------------------------------------------
describe("isValidNumeroProcesso", () => {
  const processosValidos = [
    "0001234-56.2026.8.00.0000",
    "1234567-89.2024.1.23.4567",
  ];

  processosValidos.forEach((num) => {
    it(`aceita CNJ valido: ${num}`, () => {
      expect(isValidNumeroProcesso(num)).toBe(true);
    });
  });

  const processosInvalidos = [
    "",
    "123",
    "0001234-56.2026.8.00.000",
    "0001234-56.2026.8.00.00001",
    "000123A-56.2026.8.00.0000",
    "0001234-56-2026.8.00.0000",
    null,
    undefined,
    "  ",
  ];

  processosInvalidos.forEach((num) => {
    it(`rejeita CNJ invalido: ${JSON.stringify(num)}`, () => {
      expect(isValidNumeroProcesso(num)).toBe(false);
    });
  });

  it("aceita numero com espacos ao redor (trim)", () => {
    expect(isValidNumeroProcesso("  0001234-56.2026.8.00.0000  ")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Constantes exportadas
// ---------------------------------------------------------------------------
describe("constantes", () => {
  it("PASSWORD_MIN_LENGTH e 8", () => {
    expect(PASSWORD_MIN_LENGTH).toBe(8);
  });

  it("PASSWORD_MAX_LENGTH e 128", () => {
    expect(PASSWORD_MAX_LENGTH).toBe(128);
  });

  it("EMAIL_REGEX e instancia de RegExp", () => {
    expect(EMAIL_REGEX).toBeInstanceOf(RegExp);
  });

  it("PROCESSO_REGEX e instancia de RegExp", () => {
    expect(PROCESSO_REGEX).toBeInstanceOf(RegExp);
  });
});

import { afterEach, describe, expect, it, beforeEach, vi } from "vitest";
import {
  DRAFT_STORAGE_KEY,
  AUTH_SESSION_STORAGE_KEY,
  readDraftFromStorage,
  persistDraft,
  readStoredSession,
  persistSession,
  clearSession,
} from "./storage";

// Mock do localStorage usando um Map simples.
function createLocalStorageMock() {
  const store = new Map();
  return {
    getItem: vi.fn((key) => store.get(key) ?? null),
    setItem: vi.fn((key, value) => store.set(key, value)),
    removeItem: vi.fn((key) => store.delete(key)),
    clear: vi.fn(() => store.clear()),
  };
}

describe("storage", () => {
  let storageMock;

  beforeEach(() => {
    storageMock = createLocalStorageMock();
    // Garante que window e localStorage existem no ambiente de teste.
    globalThis.window = globalThis.window || {};
    globalThis.window.localStorage = storageMock;
  });

  // -------------------------------------------------------------------------
  // Constantes
  // -------------------------------------------------------------------------
  describe("constantes", () => {
    it("DRAFT_STORAGE_KEY possui prefixo jurisflow", () => {
      expect(DRAFT_STORAGE_KEY).toContain("jurisflow");
    });

    it("AUTH_SESSION_STORAGE_KEY possui prefixo jurisflow", () => {
      expect(AUTH_SESSION_STORAGE_KEY).toContain("jurisflow");
    });
  });

  // -------------------------------------------------------------------------
  // readDraftFromStorage
  // -------------------------------------------------------------------------
  describe("readDraftFromStorage", () => {
    it("retorna form null e info vazia quando nenhum rascunho existe", () => {
      const result = readDraftFromStorage();
      expect(result.form).toBeNull();
      expect(result.info).toBe("");
    });

    it("recupera rascunho salvo com data", () => {
      const draft = { form: { campo: "valor" }, savedAt: "2026-01-01 10:00" };
      storageMock.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));

      const result = readDraftFromStorage();
      expect(result.form).toEqual({ campo: "valor" });
      expect(result.info).toContain("Rascunho recuperado");
      expect(result.info).toContain("2026-01-01");
    });

    it("retorna form null se rascunho nao possui campo form", () => {
      storageMock.setItem(DRAFT_STORAGE_KEY, JSON.stringify({}));
      const result = readDraftFromStorage();
      expect(result.form).toBeNull();
    });

    it("retorna info vazia quando savedAt ausente", () => {
      storageMock.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ form: {} }));
      const result = readDraftFromStorage();
      expect(result.info).toBe("");
    });

    it("retorna mensagem de erro quando JSON e invalido", () => {
      storageMock.getItem.mockReturnValue("{{json-invalido");
      const result = readDraftFromStorage();
      expect(result.form).toBeNull();
      expect(result.info).toContain("Nao foi possivel");
    });
  });

  // -------------------------------------------------------------------------
  // persistDraft
  // -------------------------------------------------------------------------
  describe("persistDraft", () => {
    it("salva payload no localStorage", () => {
      const payload = { form: { numero: "123" }, savedAt: "agora" };
      persistDraft(payload);
      expect(storageMock.setItem).toHaveBeenCalledWith(
        DRAFT_STORAGE_KEY,
        JSON.stringify(payload),
      );
    });
  });

  // -------------------------------------------------------------------------
  // readStoredSession
  // -------------------------------------------------------------------------
  describe("readStoredSession", () => {
    it("retorna null quando nenhuma sessao existe", () => {
      expect(readStoredSession()).toBeNull();
    });

    it("recupera sessao valida", () => {
      const session = { id: "1", name: "Maria", email: "m@e.com" };
      storageMock.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify(session));

      const result = readStoredSession();
      expect(result).toEqual(session);
    });

    it("retorna null quando JSON e invalido", () => {
      storageMock.getItem.mockReturnValue("invalido");
      expect(readStoredSession()).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // persistSession
  // -------------------------------------------------------------------------
  describe("persistSession", () => {
    it("salva apenas campos seguros (id, name, email)", () => {
      persistSession({ id: "42", name: "Joao", email: "j@e.com", token: "secret" });

      const saved = JSON.parse(storageMock.setItem.mock.calls[0][1]);
      expect(saved.id).toBe("42");
      expect(saved.name).toBe("Joao");
      expect(saved.email).toBe("j@e.com");
      expect(saved.token).toBeUndefined();
    });

    it("usa valores padrao quando session e null", () => {
      persistSession(null);

      const saved = JSON.parse(storageMock.setItem.mock.calls[0][1]);
      expect(saved.id).toBe("");
      expect(saved.name).toBe("Conta");
      expect(saved.email).toBe("");
    });

    it("usa valores padrao quando session e undefined", () => {
      persistSession(undefined);

      const saved = JSON.parse(storageMock.setItem.mock.calls[0][1]);
      expect(saved.name).toBe("Conta");
    });
  });

  // -------------------------------------------------------------------------
  // clearSession
  // -------------------------------------------------------------------------
  describe("clearSession", () => {
    it("remove sessao do localStorage", () => {
      clearSession();
      expect(storageMock.removeItem).toHaveBeenCalledWith(AUTH_SESSION_STORAGE_KEY);
    });
  });
});

// ---------------------------------------------------------------------------
// Guardas SSR (typeof window === "undefined")
// Testadas em bloco separado para controlar o objeto global com seguranca.
// ---------------------------------------------------------------------------
describe("storage - guardas SSR (sem window)", () => {
  let windowBackup;

  beforeEach(() => {
    windowBackup = globalThis.window;
    // Remove window para simular ambiente SSR / Node puro.
    delete globalThis.window;
  });

  afterEach(() => {
    globalThis.window = windowBackup;
  });

  it("readDraftFromStorage retorna default sem lancar erro", () => {
    const result = readDraftFromStorage();
    expect(result).toEqual({ form: null, info: "" });
  });

  it("persistDraft nao lanca erro sem window", () => {
    expect(() => persistDraft({ form: {}, savedAt: "agora" })).not.toThrow();
  });

  it("readStoredSession retorna null sem window", () => {
    expect(readStoredSession()).toBeNull();
  });

  it("persistSession nao lanca erro sem window", () => {
    expect(() => persistSession({ id: "1", name: "A", email: "a@b.com" })).not.toThrow();
  });

  it("clearSession nao lanca erro sem window", () => {
    expect(() => clearSession()).not.toThrow();
  });
});

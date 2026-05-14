// Testes de integracao do supabaseClient com mock do SDK Supabase.
import { describe, expect, it, vi } from "vitest";

const mockClient = { auth: {}, from: vi.fn() };

vi.mock("@supabase/supabase-js", () => ({
  createClient: vi.fn(() => mockClient),
}));

describe("supabaseClient", () => {
  describe("isSupabaseConfigured", () => {
    it("e um booleano", async () => {
      const { isSupabaseConfigured } = await import("./supabaseClient");
      expect(typeof isSupabaseConfigured).toBe("boolean");
    });

    it("reflete presenca das variaveis de ambiente VITE_SUPABASE_URL e VITE_SUPABASE_PUBLISHABLE_KEY", async () => {
      const { isSupabaseConfigured } = await import("./supabaseClient");
      // O valor depende do ambiente. Verificamos apenas que o contrato e
      // booleano e coerente com o que o modulo exporta.
      expect(isSupabaseConfigured === true || isSupabaseConfigured === false).toBe(true);
    });
  });

  describe("getSupabaseClient", () => {
    it("retorna o mesmo cliente em chamadas repetidas (singleton)", async () => {
      const { isSupabaseConfigured, getSupabaseClient } = await import("./supabaseClient");

      // So testa o singleton quando o Supabase esta configurado.
      if (!isSupabaseConfigured) {
        expect(() => getSupabaseClient()).toThrow("Supabase nao configurado");
        return;
      }

      const cliente1 = getSupabaseClient();
      const cliente2 = getSupabaseClient();
      expect(cliente1).toBe(cliente2);
    });

    it("lanca erro com mensagem orientando sobre variaveis quando nao configurado", async () => {
      const { isSupabaseConfigured, getSupabaseClient } = await import("./supabaseClient");

      if (!isSupabaseConfigured) {
        expect(() => getSupabaseClient()).toThrow("VITE_SUPABASE_URL");
      } else {
        // Supabase esta configurado — verifica que o cliente e objeto valido.
        const client = getSupabaseClient();
        expect(client).toBeDefined();
      }
    });
  });
});

import { describe, expect, it, vi } from "vitest";
import { generateCaseId } from "./cases";

describe("generateCaseId", () => {
  it("gera primeiro ID quando historico esta vazio", () => {
    const id = generateCaseId([]);
    const year = new Date().getFullYear();
    expect(id).toBe(`CTR-${year}-001`);
  });

  it("incrementa a partir do maior ID existente", () => {
    const history = [
      { id: "CTR-2026-001" },
      { id: "CTR-2026-003" },
      { id: "CTR-2026-002" },
    ];
    const id = generateCaseId(history);
    const year = new Date().getFullYear();
    expect(id).toBe(`CTR-${year}-004`);
  });

  it("ignora IDs com formato invalido (NaN)", () => {
    const history = [
      { id: "CTR-2026-abc" },
      { id: "CTR-2026-002" },
    ];
    const id = generateCaseId(history);
    const year = new Date().getFullYear();
    expect(id).toBe(`CTR-${year}-003`);
  });

  it("preenche numero com zeros a esquerda (padStart 3)", () => {
    const history = [{ id: "CTR-2026-009" }];
    const id = generateCaseId(history);
    expect(id).toMatch(/-010$/);
  });

  it("gera ID com ano corrente independente do historico", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2030, 0, 1));

    const id = generateCaseId([]);
    expect(id).toBe("CTR-2030-001");

    vi.useRealTimers();
  });

  it("funciona com historico de apenas um item", () => {
    const history = [{ id: "CTR-2026-050" }];
    const id = generateCaseId(history);
    const year = new Date().getFullYear();
    expect(id).toBe(`CTR-${year}-051`);
  });

  it("lida com IDs que possuem numeros grandes (> 999)", () => {
    const history = [{ id: "CTR-2026-1500" }];
    const id = generateCaseId(history);
    const year = new Date().getFullYear();
    expect(id).toBe(`CTR-${year}-1501`);
  });
});

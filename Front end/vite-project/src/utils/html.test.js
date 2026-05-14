import { describe, expect, it } from "vitest";
import { escapeHtml } from "./html";

describe("escapeHtml", () => {
  it("escapa & para &amp;", () => {
    expect(escapeHtml("Tom & Jerry")).toBe("Tom &amp; Jerry");
  });

  it("escapa < para &lt;", () => {
    expect(escapeHtml("<script>")).toBe("&lt;script&gt;");
  });

  it("escapa > para &gt;", () => {
    expect(escapeHtml("a > b")).toBe("a &gt; b");
  });

  it("escapa aspas duplas para &quot;", () => {
    expect(escapeHtml('diz "ola"')).toBe("diz &quot;ola&quot;");
  });

  it("escapa aspas simples para &#39;", () => {
    expect(escapeHtml("it's")).toBe("it&#39;s");
  });

  it("escapa todos os caracteres especiais em uma unica string", () => {
    const input = `<div class="test" data-info='a&b'>`;
    const expected =
      "&lt;div class=&quot;test&quot; data-info=&#39;a&amp;b&#39;&gt;";
    expect(escapeHtml(input)).toBe(expected);
  });

  it("nao altera texto sem caracteres especiais", () => {
    expect(escapeHtml("Texto normal 123")).toBe("Texto normal 123");
  });

  it("retorna string vazia para null/undefined", () => {
    expect(escapeHtml(null)).toBe("");
    expect(escapeHtml(undefined)).toBe("");
  });

  it("retorna string vazia para string vazia", () => {
    expect(escapeHtml("")).toBe("");
  });

  it("protege contra XSS tipico com tag script", () => {
    const xss = '<script>alert("XSS")</script>';
    const result = escapeHtml(xss);
    expect(result).not.toContain("<script>");
    expect(result).toContain("&lt;script&gt;");
  });

  it("protege contra XSS com atributo onerror", () => {
    const xss = '<img src=x onerror="alert(1)">';
    const result = escapeHtml(xss);
    expect(result).not.toContain("<img");
    expect(result).toContain("&lt;img");
  });
});

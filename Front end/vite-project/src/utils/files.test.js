import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MAX_FILE_SIZE_BYTES,
  ALLOWED_EXTENSIONS,
  ALLOWED_MIME_TYPES,
  normalizeFileName,
  validateFile,
  readFileAsBase64,
} from "./files";

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------
describe("constantes de arquivo", () => {
  it("MAX_FILE_SIZE_BYTES e 10MB", () => {
    expect(MAX_FILE_SIZE_BYTES).toBe(10 * 1024 * 1024);
  });

  it("extensoes permitidas incluem pdf, doc e docx", () => {
    expect(ALLOWED_EXTENSIONS).toContain("pdf");
    expect(ALLOWED_EXTENSIONS).toContain("doc");
    expect(ALLOWED_EXTENSIONS).toContain("docx");
  });

  it("ALLOWED_MIME_TYPES aceita application/pdf", () => {
    expect(ALLOWED_MIME_TYPES.has("application/pdf")).toBe(true);
  });

  it("ALLOWED_MIME_TYPES aceita MIME vazio (fallback de browser)", () => {
    expect(ALLOWED_MIME_TYPES.has("")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// normalizeFileName
// ---------------------------------------------------------------------------
describe("normalizeFileName", () => {
  it("converte para minusculo", () => {
    expect(normalizeFileName("Contestacao_FINAL")).toBe("contestacao_final");
  });

  it("substitui caracteres especiais por hifen", () => {
    expect(normalizeFileName("peça base (v2)")).toBe("pe-a-base-v2");
  });

  it("colapsa hifens consecutivos", () => {
    expect(normalizeFileName("a---b")).toBe("a-b");
  });

  it("remove hifens no inicio e fim", () => {
    expect(normalizeFileName("-nome-")).toBe("nome");
  });

  it("retorna 'defesa' como padrao para null/undefined", () => {
    expect(normalizeFileName(null)).toBe("defesa");
    expect(normalizeFileName(undefined)).toBe("defesa");
  });

  it("retorna 'defesa' para string vazia", () => {
    expect(normalizeFileName("")).toBe("defesa");
  });
});

// ---------------------------------------------------------------------------
// validateFile
// ---------------------------------------------------------------------------
describe("validateFile", () => {
  function createFakeFile(name, type, size) {
    return { name, type, size };
  }

  it("rejeita quando nenhum arquivo e selecionado", () => {
    expect(validateFile(null)).toContain("Selecione");
    expect(validateFile(undefined)).toContain("Selecione");
  });

  it("aceita arquivo PDF valido", () => {
    const file = createFakeFile("peca.pdf", "application/pdf", 1024);
    expect(validateFile(file)).toBe("");
  });

  it("aceita arquivo DOC valido", () => {
    const file = createFakeFile("peca.doc", "application/msword", 1024);
    expect(validateFile(file)).toBe("");
  });

  it("aceita arquivo DOCX valido", () => {
    const file = createFakeFile(
      "peca.docx",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      1024,
    );
    expect(validateFile(file)).toBe("");
  });

  it("aceita arquivo com MIME vazio (fallback de browser)", () => {
    const file = createFakeFile("peca.doc", "", 1024);
    expect(validateFile(file)).toBe("");
  });

  it("rejeita extensao invalida", () => {
    const file = createFakeFile("virus.exe", "application/octet-stream", 1024);
    expect(validateFile(file)).toContain("Formato invalido");
  });

  it("rejeita MIME type invalido", () => {
    const file = createFakeFile("falso.pdf", "application/octet-stream", 1024);
    expect(validateFile(file)).toContain("Tipo de arquivo");
  });

  it("rejeita arquivo que excede 10MB", () => {
    const file = createFakeFile(
      "grande.pdf",
      "application/pdf",
      MAX_FILE_SIZE_BYTES + 1,
    );
    expect(validateFile(file)).toContain("10MB");
  });

  it("aceita arquivo exatamente no limite de 10MB", () => {
    const file = createFakeFile(
      "limite.pdf",
      "application/pdf",
      MAX_FILE_SIZE_BYTES,
    );
    expect(validateFile(file)).toBe("");
  });

  it("rejeita arquivo .txt", () => {
    const file = createFakeFile("texto.txt", "text/plain", 100);
    expect(validateFile(file)).toContain("Formato invalido");
  });

  it("rejeita arquivo .exe renomeado para .pdf com MIME errado", () => {
    const file = createFakeFile("falso.pdf", "application/x-msdownload", 1024);
    expect(validateFile(file)).toContain("Tipo de arquivo");
  });
});

// ---------------------------------------------------------------------------
// readFileAsBase64
// ---------------------------------------------------------------------------
describe("readFileAsBase64", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("retorna string vazia para arquivo null", async () => {
    const result = await readFileAsBase64(null);
    expect(result).toBe("");
  });

  it("retorna string vazia para undefined", async () => {
    const result = await readFileAsBase64(undefined);
    expect(result).toBe("");
  });

  it("extrai base64 puro removendo prefixo data:...;base64,", async () => {
    const fakeBase64 = "SGVsbG8gV29ybGQ=";

    const MockFileReader = vi.fn(function () {
      this.readAsDataURL = vi.fn(() => {
        // Simula comportamento assincrono do browser
        setTimeout(() => {
          this.result = `data:application/pdf;base64,${fakeBase64}`;
          this.onload();
        }, 0);
      });
    });

    vi.stubGlobal("FileReader", MockFileReader);

    const fakeFile = new Blob(["conteudo"], { type: "application/pdf" });
    const result = await readFileAsBase64(fakeFile);
    expect(result).toBe(fakeBase64);
  });

  it("retorna string bruta quando resultado nao tem virgula", async () => {
    const fakeRaw = "base64semvirgula";

    const MockFileReader = vi.fn(function () {
      this.readAsDataURL = vi.fn(() => {
        setTimeout(() => {
          this.result = fakeRaw;
          this.onload();
        }, 0);
      });
    });

    vi.stubGlobal("FileReader", MockFileReader);

    const fakeFile = new Blob(["x"], { type: "application/pdf" });
    const result = await readFileAsBase64(fakeFile);
    expect(result).toBe(fakeRaw);
  });

  it("rejeita a promise quando FileReader dispara onerror", async () => {
    const MockFileReader = vi.fn(function () {
      this.readAsDataURL = vi.fn(() => {
        setTimeout(() => {
          this.onerror();
        }, 0);
      });
    });

    vi.stubGlobal("FileReader", MockFileReader);

    const fakeFile = new Blob(["x"], { type: "application/pdf" });
    await expect(readFileAsBase64(fakeFile)).rejects.toThrow(
      "Falha ao ler arquivo no navegador.",
    );
  });

  it("retorna string vazia quando reader.result nao e string", async () => {
    const MockFileReader = vi.fn(function () {
      this.readAsDataURL = vi.fn(() => {
        setTimeout(() => {
          this.result = null; // nao e string
          this.onload();
        }, 0);
      });
    });

    vi.stubGlobal("FileReader", MockFileReader);

    const fakeFile = new Blob(["x"], { type: "application/pdf" });
    const result = await readFileAsBase64(fakeFile);
    expect(result).toBe("");
  });
});

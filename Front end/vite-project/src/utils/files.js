/**
 * Limite maximo do arquivo para evitar payload excessivo.
 */
export const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024;

/**
 * Extensoes aceitas para peca base.
 */
export const ALLOWED_EXTENSIONS = ["pdf", "doc", "docx"];

/**
 * MIME types correspondentes. Browsers preenchem `file.type` a partir do
 * proprio arquivo (Content-Type sniffing), entao validar aqui evita o caso
 * trivial de renomear .exe para .pdf. Validacao definitiva continua no backend.
 */
export const ALLOWED_MIME_TYPES = new Set([
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  // Alguns navegadores deixam vazio para .doc/.docx; aceitamos para nao
  // bloquear usuarios legitimos. O backend ainda precisa validar magic bytes.
  "",
]);

/**
 * Normaliza nome para exportacao local de arquivo.
 */
export function normalizeFileName(value) {
  return (value || "defesa")
    .toLowerCase()
    .replace(/[^\w-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

/**
 * Valida arquivo do input antes do envio.
 */
export function validateFile(file) {
  if (!file) return "Selecione um arquivo DOCX, DOC ou PDF.";

  const extension = file.name.split(".").pop()?.toLowerCase() || "";
  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    return "Formato invalido. Envie apenas DOCX, DOC ou PDF.";
  }
  // Verifica MIME alem da extensao para barrar renomeacoes triviais (.exe -> .pdf).
  if (!ALLOWED_MIME_TYPES.has(file.type || "")) {
    return "Tipo de arquivo nao reconhecido. Envie um DOCX, DOC ou PDF valido.";
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return "Arquivo muito grande. Limite de 10MB.";
  }

  return "";
}

/**
 * Converte File do navegador para base64 puro (sem prefixo data:).
 */
export async function readFileAsBase64(file) {
  if (!file) return "";

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const raw = typeof reader.result === "string" ? reader.result : "";
      const base64 = raw.includes(",") ? raw.split(",")[1] : raw;
      resolve(base64);
    };
    reader.onerror = () => reject(new Error("Falha ao ler arquivo no navegador."));
    reader.readAsDataURL(file);
  });
}

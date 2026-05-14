/**
 * Escapa caracteres HTML para evitar injecao ao renderizar texto bruto.
 */
export function escapeHtml(value) {
  const source = value || "";
  return source
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

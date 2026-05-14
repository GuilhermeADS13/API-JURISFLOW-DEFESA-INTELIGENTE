/**
 * Gera id incremental de caso por ano para exibicao no dashboard.
 */
export function generateCaseId(currentHistory) {
  const year = new Date().getFullYear();
  const existing = currentHistory
    .map((item) => Number(item.id.split("-")[2]))
    .filter((value) => Number.isFinite(value));
  const next = (existing.length ? Math.max(...existing) : 0) + 1;
  return `CTR-${year}-${String(next).padStart(3, "0")}`;
}

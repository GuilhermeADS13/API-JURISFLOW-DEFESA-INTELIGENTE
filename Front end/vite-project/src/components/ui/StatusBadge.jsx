// Badge visual reutilizavel para status de itens no dashboard.
import React from "react";
import { Badge } from "react-bootstrap";

/**
 * Badge visual para status do caso no dashboard.
 */
export default function StatusBadge({ status }) {
  // Remove acentos pra matching tolerar "análise" ↔ "analise", "concluída" ↔ "concluida" etc.
  const normalized = status
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

  let tone = "neutral";

  if (normalized.includes("conclu")) {
    tone = "success";
  } else if (normalized.includes("analise")) {
    tone = "warning";
  } else if (normalized.includes("revis")) {
    tone = "info";
  }

  return (
    <Badge pill className={`status-pill status-pill-${tone}`}>
      {status}
    </Badge>
  );
}

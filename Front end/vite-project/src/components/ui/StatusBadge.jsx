// Badge visual reutilizavel para status de itens no dashboard.
import React from "react";
import { Badge } from "react-bootstrap";

/**
 * Badge visual para status do caso no dashboard.
 */
export default function StatusBadge({ status }) {
  const normalized = status.toLowerCase();

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

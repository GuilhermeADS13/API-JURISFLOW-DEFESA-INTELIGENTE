"""Schema Pydantic para coleta de feedback do advogado sobre a minuta gerada."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FeedbackContestacao(BaseModel):
    """Payload para POST /api/contestacoes/{contestacao_id}/feedback.

    O advogado avalia se a minuta gerada foi util ou nao, com comentario opcional.
    O backend usa esse dado para ponderar o ranking RAG nas proximas geracoes.
    """

    model_config = ConfigDict(extra="ignore")

    util: bool
    comentario: Annotated[str | None, Field(default=None, max_length=2000)] = None

    @field_validator("comentario")
    @classmethod
    def limpar_comentario(cls, value: str | None) -> str | None:
        if value is None:
            return None
        texto = value.strip()
        return texto if texto else None

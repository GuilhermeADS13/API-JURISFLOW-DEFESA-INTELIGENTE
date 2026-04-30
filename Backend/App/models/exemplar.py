"""Schema Pydantic para cadastro de contestacao exemplar (curadoria admin)."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExemplarContestacao(BaseModel):
    """Payload para POST /api/admin/exemplares.

    Contestacoes exemplares sao usadas como few-shot no system prompt do agente Claude.
    Devem ser selecionadas pelo escritorio como representativas de alta qualidade.
    """

    model_config = ConfigDict(extra="ignore")

    tipo_acao: Annotated[str, Field(min_length=2, max_length=100)]
    tese_central: Annotated[str, Field(min_length=10, max_length=2000)]
    fundamentos_resumo: Annotated[str, Field(min_length=20, max_length=5000)]
    nota_qualidade: Annotated[int, Field(default=8, ge=1, le=10)] = 8

    @field_validator("tipo_acao", "tese_central", "fundamentos_resumo")
    @classmethod
    def limpar_texto(cls, value: str) -> str:
        texto = value.strip()
        if not texto:
            raise ValueError("Campo obrigatorio.")
        return texto

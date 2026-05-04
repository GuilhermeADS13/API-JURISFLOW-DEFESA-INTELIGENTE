"""Rota POST /api/contestacoes/{contestacao_id}/feedback.

Permite ao advogado autenticado avaliar uma minuta (util/nao-util + comentario opcional).
O feedback e usado pelo RAG do agente para ponderar ranking das defesas anteriores.
"""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request, status
from pydantic import ValidationError

from App.database import (
    DatabaseIntegrityError,
    get_contestacoes_exemplares,
    salvar_exemplar,
    salvar_feedback,
)
from App.limiter import limiter
from App.models.feedback import FeedbackContestacao
from App.models.exemplar import ExemplarContestacao
from App.security import get_authenticated_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/contestacoes/{contestacao_id}/feedback")
@limiter.limit("20/minute")
async def registrar_feedback(
    request: Request,
    contestacao_id: int = Path(..., ge=1),
    payload: FeedbackContestacao = Body(...),
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Registra avaliacao (util/nao-util) do advogado sobre a minuta gerada.

    Retorna 404 se o contestacao_id nao existir ou nao pertencer ao usuario.
    """
    usuario_id = str(usuario["id"])

    persistido = salvar_feedback(
        contestacao_id=contestacao_id,
        usuario_id=usuario_id,
        util=payload.util,
        comentario=payload.comentario,
    )

    if not persistido:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestacao nao encontrada ou sem permissao.",
        )

    logger.info(
        "Feedback registrado contestacao_id=%s usuario_id=%s util=%s",
        contestacao_id,
        usuario_id,
        payload.util,
    )

    return {"status": "ok", "contestacao_id": contestacao_id, "util": payload.util}


# ---------- endpoints admin exemplares ----------

def _is_admin(usuario: dict[str, str]) -> bool:
    """Verifica se o email do usuario esta na lista de admins do .env."""
    import os
    admins_raw = os.getenv("ADMIN_EMAILS", "")
    admins = {e.strip().lower() for e in admins_raw.split(",") if e.strip()}
    email = str(usuario.get("email", "")).lower()
    return email in admins


@router.post("/admin/exemplares", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def criar_exemplar(
    request: Request,
    payload: ExemplarContestacao,
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Endpoint admin: cadastra contestacao exemplar para few-shot do agente.

    Protegido por lista ADMIN_EMAILS no .env.
    """
    if not _is_admin(usuario):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )

    inserted_id = salvar_exemplar(
        tipo_acao=payload.tipo_acao,
        tese_central=payload.tese_central,
        fundamentos_resumo=payload.fundamentos_resumo,
        nota_qualidade=payload.nota_qualidade,
    )

    logger.info(
        "Exemplar criado id=%s tipo_acao=%s por admin=%s",
        inserted_id,
        payload.tipo_acao,
        usuario.get("email"),
    )

    return {"status": "criado", "id": inserted_id, "tipo_acao": payload.tipo_acao}


@router.get("/admin/exemplares")
@limiter.limit("20/minute")
async def listar_exemplares(
    request: Request,
    tipo_acao: str,
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Admin: lista exemplares curados por tipo_acao."""
    if not _is_admin(usuario):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )

    exemplares = get_contestacoes_exemplares(tipo_acao)
    return {"tipo_acao": tipo_acao, "exemplares": exemplares, "total": len(exemplares)}

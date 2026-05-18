# Rotas HTTP de contestacoes: envio ao n8n e consulta de resumo do dashboard.
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from App.database import (
    get_dashboard_cards_por_usuario,
    list_contestacoes_por_usuario,
    save_contestacao,
)
from App.limiter import limiter
from App.models.processo import Processo
from App.security import get_authenticated_user
from App.services.n8n_service import N8NServiceError, enviar_para_n8n

logger = logging.getLogger(__name__)

router = APIRouter()

# PR8 P2.1 — rate limit configuravel via env. Default generoso (10/min) suporta
# fluxo real do advogado submetendo 3-5 casos em sequencia. Testes de carga
# podem definir "2/minute" no .env.
RATE_LIMIT_CONTESTACAO = os.getenv("RATE_LIMIT_CONTESTACAO", "10/minute")
RATE_LIMIT_DASHBOARD = os.getenv("RATE_LIMIT_DASHBOARD", "30/minute")


@router.post("/gerar-contestacao")
@limiter.limit(RATE_LIMIT_CONTESTACAO)
async def gerar_contestacao(
    request: Request,
    processo: Processo,
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Dispara workflow do n8n e persiste rastreio do envio."""
    payload = processo.model_dump()
    payload["usuario_id"] = usuario["id"]
    payload["usuario_nome"] = usuario.get("nome", "")
    payload["usuario_email"] = usuario.get("email", "")
    payload["auth_provider"] = usuario.get("auth_provider", "legacy")

    try:
        resposta = await enviar_para_n8n(payload)
        workflow_status = "processando"
        if isinstance(resposta, dict):
            workflow_status = (
                str(resposta.get("status") or "processando").strip() or "processando"
            )

        if workflow_status in {"erro_validacao", "rejeitado"}:
            save_contestacao(payload, status=workflow_status, n8n_resposta=resposta)
            # Log completo da resposta do n8n para diagnostico, sem vazar detalhes ao cliente.
            logger.warning(
                "n8n rejeitou contestacao usuario_id=%s status=%s resposta=%s",
                usuario["id"],
                workflow_status,
                resposta,
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Nao foi possivel gerar a contestacao com os dados informados. Revise os campos e tente novamente.",
            )

        registro_id = save_contestacao(
            payload, status=workflow_status, n8n_resposta=resposta
        )
    except N8NServiceError as error:
        save_contestacao(
            payload,
            status="erro",
            n8n_resposta={"mensagem": str(error)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error

    case_year = datetime.now().year
    case_id = f"CTR-{case_year}-{int(registro_id):06d}"

    return {
        "status": "processando",
        "id_registro": registro_id,
        "id_caso": case_id,
        "workflow": resposta,
    }


@router.get("/contestacoes/resumo")
@limiter.limit(RATE_LIMIT_DASHBOARD)
async def obter_resumo_contestacoes(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Retorna cards e historico reais do dashboard para o usuario autenticado."""
    usuario_id = str(usuario["id"])
    return {
        "cards": get_dashboard_cards_por_usuario(usuario_id),
        "history": list_contestacoes_por_usuario(usuario_id, limit=limit),
    }

# Rotas HTTP de contestacoes: envio ao n8n e consulta de resumo do dashboard.
import base64
import binascii
import logging
import os
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from App.database import (
    get_contestacao,
    get_dashboard_cards_por_usuario,
    list_contestacoes_por_usuario,
    save_contestacao,
)
from App.limiter import limiter
from App.models.processo import Processo
from App.security import get_authenticated_user
from App.services.n8n_service import N8NServiceError, enviar_para_n8n
from App.services.peticao_extractor import ExtracaoError, extrair_texto_peticao

logger = logging.getLogger(__name__)

router = APIRouter()

# PR8 P2.1 — rate limit configuravel via env. Default generoso (10/min) suporta
# fluxo real do advogado submetendo 3-5 casos em sequencia. Testes de carga
# podem definir "2/minute" no .env.
RATE_LIMIT_CONTESTACAO = os.getenv("RATE_LIMIT_CONTESTACAO", "10/minute")
RATE_LIMIT_DASHBOARD = os.getenv("RATE_LIMIT_DASHBOARD", "30/minute")


def _extrair_texto_arquivo(
    base64_content: str | None,
    nome: str,
    usuario_id: str,
    rotulo: str,
) -> str:
    """Decodifica base64 e extrai texto via peticao_extractor (PDF/DOCX/.doc).

    Retorna string vazia se: campo ausente, base64 invalido, ou extracao falhar.
    Falhas sao logadas mas nao bloqueiam o fluxo — o n8n tem fallback proprio.
    """
    if not base64_content:
        return ""
    try:
        bytes_ = base64.b64decode(base64_content, validate=False)
    except (binascii.Error, ValueError):
        logger.warning(
            "[%s] base64 invalido usuario_id=%s nome=%s", rotulo, usuario_id, nome
        )
        return ""
    if not bytes_:
        return ""
    try:
        return extrair_texto_peticao(bytes_, nome)
    except ExtracaoError as error:
        logger.warning(
            "[%s] falha na extracao usuario_id=%s nome=%s erro=%s",
            rotulo, usuario_id, nome, error,
        )
        return ""


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

    # PR10 - Extrai texto do arquivo base (peticao inicial) e do modelo base
    # (peca timbrada do escritorio) ANTES de enviar ao n8n. O sandbox JS do n8n
    # nao consegue ler PDF/DOCX (binarios ZIP+XML); por isso o backend faz a
    # extracao via peticao_extractor (pypdf + python-docx + Tesseract OCR fallback)
    # e injeta os campos `arquivo_base_conteudo_texto` e `modelo_mae_texto`
    # no payload, que o node "Validar Campos" do workflow contestacao-claude
    # le diretamente sem tentar extrair texto de novo.
    payload["arquivo_base_conteudo_texto"] = _extrair_texto_arquivo(
        payload.get("arquivo_base_conteudo_base64"),
        payload.get("arquivo_base_nome") or "peticao.pdf",
        usuario["id"],
        rotulo="arquivo_base",
    )
    payload["modelo_mae_texto"] = _extrair_texto_arquivo(
        payload.get("modelo_base_base64"),
        payload.get("modelo_base_nome") or "modelo_base.docx",
        usuario["id"],
        rotulo="modelo_base",
    )

    try:
        # PR8 P3.1 — mede o tempo end-to-end da chamada ao n8n para observabilidade.
        t_inicio = time.monotonic()
        resposta = await enviar_para_n8n(payload)
        tempo_processamento_ms = int((time.monotonic() - t_inicio) * 1000)
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

        # PR9 P3.2 — workflow sinaliza falha da IA (Claude indisponivel, fallback
        # local acionado) com status='erro_ia'. Backend deve retornar HTTP 503
        # (servico temporariamente indisponivel) em vez de 422 — usuario sabe
        # que e problema do servico, nao dos dados que enviou.
        if workflow_status == "erro_ia":
            save_contestacao(payload, status=workflow_status, n8n_resposta=resposta)
            motivo = (
                resposta.get("_debug", {}).get("fallback_motivo")
                if isinstance(resposta, dict)
                else None
            )
            logger.error(
                "n8n retornou erro_ia usuario_id=%s motivo=%s",
                usuario["id"],
                motivo,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Servico de IA temporariamente indisponivel. Tente novamente em alguns minutos.",
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

    # PR8 P2.5 — eleva campos do DOCX/minuta/engine_ia para o topo da resposta.
    # Antes ficavam soterrados em `workflow` e o frontend nao sabia como acessar.
    # Mantem `workflow` para compatibilidade com integracao antiga.
    resposta_dict = resposta if isinstance(resposta, dict) else {}
    return {
        "status": "processando",
        "id_registro": registro_id,
        "id_caso": case_id,
        "arquivo_editado_base64": resposta_dict.get("arquivo_editado_base64"),
        "arquivo_editado_nome": resposta_dict.get("arquivo_editado_nome"),
        "minuta": resposta_dict.get("minuta"),
        "engine_ia": resposta_dict.get("engine_ia"),
        "tempo_processamento_ms": tempo_processamento_ms,
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


@router.get("/contestacoes/{contestacao_id}")
@limiter.limit(RATE_LIMIT_DASHBOARD)
async def obter_contestacao(
    request: Request,
    contestacao_id: int,
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Retorna detalhes de uma contestacao especifica do usuario autenticado (PR8 P3.3).

    A funcao `get_contestacao` ja filtra por `usuario_id` (defesa em profundidade
    contra IDOR) — usuario A consultando id de contestacao do usuario B recebe 404.
    """
    registro = get_contestacao(contestacao_id, str(usuario["id"]))
    if registro is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestacao nao encontrada.",
        )
    return registro

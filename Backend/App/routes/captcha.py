"""Rotas do cascade CAPTCHA solver (PR28).

Endpoints:
    POST   /api/captcha/solve           — scraper submete CAPTCHA a resolver
    GET    /api/captcha/status/{token}  — scraper poll ate status='ok'
    POST   /api/captcha/answer/{token}  — humano registra resposta (interno / bot)
    GET    /api/captcha/pendentes       — lista introspeccao (admin)

Fluxo tipico:
    1. Scraper detecta CAPTCHA na pagina, faz POST /solve com imagem
       (multipart) + tipo + tribunal
    2. Backend tenta CRNN local. Se resolveu: retorna 200 {status:ok, texto}
    3. Senao: notifica humano (email/Telegram) + retorna 202 {status:pending, token}
    4. Scraper poll GET /status/{token} ate ok/expirado
    5. Humano abre link do email/Telegram → UI HTML simples de resposta →
       POST /answer/{token} com texto → backend acorda tarefa

Pagina HTML de resposta (`/captcha/responder/{token}`) NAO faz parte desta
rota — proximo PR (frontend). Este endpoint expoe apenas a API JSON.

Auth: scraper interno usa BACKEND_ADMIN_TOKEN. Endpoint /answer aceita
tambem query param `?tk=...` pra ser clicavel do celular sem digitar
token no header (facilita UX no fluxo humano).
"""

import logging

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)

from App.limiter import limiter
from App.security import get_authenticated_user
from App.services.captcha_orchestrator import (
    consultar_status,
    registrar_resposta,
    resolver,
    snapshot_pendentes,
)

logger = logging.getLogger(__name__)
router = APIRouter()


_TIPOS_VALIDOS = {"visual", "turnstile", "recaptcha_v2", "hcaptcha", "desconhecido"}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB — mais que suficiente pra qualquer CAPTCHA


@router.post("/captcha/solve", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def solve(
    request: Request,
    tipo: str = Form(default="visual"),
    tribunal: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Recebe CAPTCHA e roda cascade CRNN → notificacao humana.

    Auth: qualquer usuario autenticado. Uso interno esperado eh via
    backend_admin_token (n8n / scraper); humanos que testarem via
    session normal tambem funciona.
    """
    tipo_norm = tipo.strip().lower() or "visual"
    if tipo_norm not in _TIPOS_VALIDOS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"tipo invalido: {tipo!r}. Valido: {sorted(_TIPOS_VALIDOS)}",
        )

    image_bytes = None
    if file is not None:
        image_bytes = await file.read()
        if len(image_bytes) > _MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Imagem excede {_MAX_IMAGE_BYTES // (1024 * 1024)} MB.",
            )

    # Tipos sem imagem esperada (Turnstile, reCAPTCHA v3) — image_bytes fica None
    tribunal_norm = tribunal.strip() or None
    resultado = resolver(
        image_bytes,
        tipo=tipo_norm,  # type: ignore[arg-type]
        tribunal=tribunal_norm,
    )

    # HTTP semantics:
    #   ok       -> 200
    #   pending  -> 202 (Accepted, task criada)
    #   sem_canal-> 503 (Service Unavailable, config incompleta)
    if resultado.status == "ok":
        return {"status": "ok", "texto": resultado.texto}
    if resultado.status == "pending":
        return {
            "status": "pending",
            "token": resultado.token,
            "mensagem": resultado.mensagem,
        }
    # sem_canal ou outro — 503
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=resultado.mensagem or "Cascade CAPTCHA sem canal disponivel.",
    )


@router.get("/captcha/status/{token}")
@limiter.limit("120/minute")
async def status_endpoint(
    request: Request,
    token: str,
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Polling do scraper. Retorna {status, texto?}.

    Rate limit alto (120/min) porque scraper pode pollar a cada 2-5s.
    """
    resultado = consultar_status(token)
    payload: dict = {"status": resultado.status, "token": resultado.token}
    if resultado.texto:
        payload["texto"] = resultado.texto
    if resultado.mensagem:
        payload["mensagem"] = resultado.mensagem
    return payload


@router.post("/captcha/answer/{token}")
@limiter.limit("30/minute")
async def answer_endpoint(
    request: Request,
    token: str,
    payload: dict = Body(...),
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Humano registra a resposta do CAPTCHA.

    Body: {"texto": "AB5C"}
    """
    texto = str(payload.get("texto") or "").strip()
    if not texto:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campo 'texto' obrigatorio no body.",
        )
    if len(texto) > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Resposta muito longa (max 100 chars).",
        )

    ok = registrar_resposta(token, texto)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Token {token} nao encontrado ou expirou.",
        )
    return {"status": "ok", "token": token, "mensagem": "Resposta registrada."}


@router.get("/captcha/pendentes")
@limiter.limit("30/minute")
async def listar_pendentes(
    request: Request,
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Introspeccao pro admin ver tasks aguardando humano."""
    return {"pendentes": snapshot_pendentes()}

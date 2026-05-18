# Rotas HTTP de autenticacao de usuario (cadastro, login, logout e sessao).
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from App.database import (
    DatabaseIntegrityError,
    create_sessao_usuario,
    create_usuario,
    get_usuario_por_email,
    revoke_sessao,
    update_usuario_senha_hash,
)
from App.limiter import limiter
from App.models.usuario import UsuarioCadastro, UsuarioLogin, UsuarioLogout
from App.security import (
    apply_session_cookie,
    clear_session_cookie,
    extract_session_token,
    get_authenticated_user,
)
from App.services.auth_service import hash_password, needs_rehash, verify_password

logger = logging.getLogger(__name__)

router = APIRouter()


def _client_ip(request: Request) -> str:
    """IP da requisicao para auditoria de tentativas de login."""
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


@router.post("/usuarios/cadastro", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def cadastrar_usuario(
    request: Request, payload: UsuarioCadastro, response: Response
) -> dict:
    client_ip = _client_ip(request)
    existente = get_usuario_por_email(payload.email)
    if existente:
        logger.info("Tentativa de cadastro com email duplicado de ip=%s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ja existe uma conta com este e-mail.",
        )

    user_id = f"USR-{uuid4().hex[:12].upper()}"
    senha_hash = hash_password(payload.senha)

    try:
        usuario = create_usuario(
            user_id=user_id,
            nome=payload.nome,
            email=payload.email,
            senha_hash=senha_hash,
        )
    except DatabaseIntegrityError as error:
        logger.warning(
            "Conflito de integridade no cadastro: ip=%s erro=%s",
            client_ip,
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ja existe uma conta com este e-mail.",
        ) from error

    token = create_sessao_usuario(usuario["id"])
    apply_session_cookie(response, token)
    # Auditoria: nao logamos email completo para minimizar PII em logs.
    logger.info("Cadastro concluido: usuario_id=%s ip=%s", usuario["id"], client_ip)

    return {
        "status": "sucesso",
        "usuario": usuario,
        "token": token,
    }


@router.post("/usuarios/login")
@limiter.limit("10/minute")
async def login_usuario(
    request: Request, payload: UsuarioLogin, response: Response
) -> dict:
    client_ip = _client_ip(request)
    usuario = get_usuario_por_email(payload.email)
    if not usuario:
        # Loga falha sem expor o email para evitar enumeracao em caso de leak de log.
        logger.warning("Falha de login (usuario inexistente) ip=%s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais invalidas.",
        )

    senha_ok = verify_password(payload.senha, usuario["senha_hash"])
    if not senha_ok:
        logger.warning(
            "Falha de login (senha incorreta) usuario_id=%s ip=%s",
            usuario["id"],
            client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais invalidas.",
        )

    # Migracao transparente para parametros PBKDF2 atuais — so executa se o
    # hash em repouso usa iteracoes desatualizadas. Falha aqui nao bloqueia o
    # login, apenas adia a migracao para a proxima autenticacao.
    if needs_rehash(usuario["senha_hash"]):
        try:
            update_usuario_senha_hash(usuario["id"], hash_password(payload.senha))
        except Exception as error:
            logger.warning(
                "Falha ao re-hashear senha usuario_id=%s erro=%s",
                usuario["id"],
                error,
            )

    token = create_sessao_usuario(usuario["id"])
    apply_session_cookie(response, token)
    logger.info("Login bem sucedido usuario_id=%s ip=%s", usuario["id"], client_ip)

    return {
        "status": "sucesso",
        "usuario": {
            "id": usuario["id"],
            "nome": usuario["nome"],
            "email": usuario["email"],
        },
        "token": token,
    }


@router.post("/usuarios/logout")
async def logout_usuario(
    request: Request,
    response: Response,
    payload: UsuarioLogout | None = None,
) -> dict:
    header_token = extract_session_token(request, request.headers.get("authorization"))
    token = (payload.token if payload else None) or header_token

    if token:
        revoke_sessao(token)

    clear_session_cookie(response)

    return {"status": "sucesso", "message": "Sessao encerrada."}


@router.get("/usuarios/sessao")
async def obter_sessao(
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Retorna dados basicos da sessao autenticada."""
    return {
        "status": "sucesso",
        "usuario": {
            "id": usuario["id"],
            "nome": usuario["nome"],
            "email": usuario["email"],
        },
    }

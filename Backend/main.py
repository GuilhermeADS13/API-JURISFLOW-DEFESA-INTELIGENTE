# Ponto de entrada da API FastAPI com middlewares, rotas e healthchecks.
import logging
import os
from pathlib import Path


def load_env_file() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # PR8 P1.4: NAO sobrescrever variaveis ja presentes no ambiente.
        # Em producao (Docker, Railway, Kubernetes) as envs vem injetadas e o
        # .env local (se acidentalmente presente na imagem) nao pode vazar
        # config de dev sobre prod. Em dev, basta nao ter a var setada no
        # sistema antes de rodar o backend.
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file()

# Configuracao de logging estruturado para observabilidade em producao.
# Formato: timestamp | nivel | logger | mensagem
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

# Imports a partir daqui sao posicionados apos load_env_file() de proposito,
# para que modulos da App leiam env vars ja carregadas do .env local. ruff
# desativado por linha (E402) — comportamento intencional documentado.
from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI, HTTPException, Request, status  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

from App.database import init_db, ping_database  # noqa: E402
from App.limiter import limiter  # noqa: E402
from App.routes import (  # noqa: E402
    contestacao,
    contestacao_peticao,
    edicao,
    feedback,
    rag,
    suporte,
    usuario,
)


def parse_frontend_origins() -> list[str]:
    raw_value = os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [
        origin.strip().rstrip("/") for origin in raw_value.split(",") if origin.strip()
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="API de Automacao de Contestacao",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_frontend_origins(),
    # Necessario para trafegar cookie HTTPOnly de sessao entre front e backend.
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin"
    # PR8 P2.6 — CSP restritivo: backend e API JSON, nao serve script proprio
    # nem incorpora HTML de terceiros. frame-ancestors 'none' complementa o
    # X-Frame-Options para browsers modernos.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'none'; "
        "object-src 'none'; "
        "frame-ancestors 'none'"
    )
    # Bloqueia APIs sensiveis do browser que o backend nao precisa.
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    return response


app.include_router(contestacao.router, prefix="/api", tags=["Contestacao"])
app.include_router(
    contestacao_peticao.router, prefix="/api", tags=["Contestacao por Peticao"]
)
app.include_router(edicao.router, prefix="/api", tags=["Edicao"])
app.include_router(usuario.router, prefix="/api", tags=["Usuarios"])
app.include_router(suporte.router, prefix="/api", tags=["Suporte"])
app.include_router(feedback.router, prefix="/api", tags=["Feedback"])
app.include_router(rag.router, prefix="/api", tags=["RAG Semantico"])


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "message": "Backend online"}


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/health/db")
def healthcheck_database() -> dict[str, str]:
    try:
        ping_database()
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Banco PostgreSQL indisponivel.",
        ) from error

    return {"status": "healthy", "database": "postgresql"}

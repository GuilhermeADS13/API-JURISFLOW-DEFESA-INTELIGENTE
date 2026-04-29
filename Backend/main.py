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
        # Em desenvolvimento, garantimos que o .env do projeto tenha prioridade
        # para evitar variaveis antigas do sistema operacional.
        if key:
            os.environ[key] = value


load_env_file()

# Configuracao de logging estruturado para observabilidade em producao.
# Formato: timestamp | nivel | logger | mensagem
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from App.database import init_db, ping_database
from App.limiter import limiter
from App.routes import contestacao, suporte, usuario


def parse_frontend_origins() -> list[str]:
    raw_value = os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip().rstrip("/") for origin in raw_value.split(",") if origin.strip()]


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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin"
    return response


app.include_router(contestacao.router, prefix="/api", tags=["Contestacao"])
app.include_router(usuario.router, prefix="/api", tags=["Usuarios"])
app.include_router(suporte.router, prefix="/api", tags=["Suporte"])


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

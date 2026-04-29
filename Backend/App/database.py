# pyright: reportMissingModuleSource=false

"""Camada de acesso a dados do sistema.

Este modulo centraliza:
- configuracao de conexao PostgreSQL com pool de conexoes,
- inicializacao do schema,
- operacoes de usuario/sessao,
- persistencia de contestacoes.
"""

import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus
from uuid import uuid4

try:
    import psycopg2
    import psycopg2.pool as psycopg2_pool
    from psycopg2.extras import Json as PGJsonAdapter
except ModuleNotFoundError:
    psycopg2 = None
    psycopg2_pool = None
    PGJsonAdapter = None

DEFAULT_DATABASE_HOST = "localhost"
DEFAULT_DATABASE_PORT = 5432
DEFAULT_DATABASE_NAME = "contestacao_db"
DEFAULT_DATABASE_USER = "postgres"
DEFAULT_DATABASE_SSLMODE = "require"
DEFAULT_DATABASE_CONNECT_TIMEOUT = 5
DEFAULT_SESSION_TTL_HOURS = 12
DEFAULT_POOL_MIN_CONNECTIONS = 1
DEFAULT_POOL_MAX_CONNECTIONS = 10

_db_initialized = False
_db_init_lock = threading.Lock()
_connection_pool = None
_pool_lock = threading.Lock()

# Cache em-memoria de sessoes validadas para evitar JOIN no Postgres a cada request.
# Chave = token; valor = (expira_em_epoch, payload_dict). Reduz pressao no DB para
# fluxos curtos do dashboard sem comprometer revogacao (TTL curto, default 60s).
_session_cache: dict[str, tuple[float, dict[str, str]]] = {}
_session_cache_lock = threading.Lock()


def _get_session_cache_ttl_seconds() -> int:
    return _safe_int(os.getenv("SESSION_CACHE_TTL_SECONDS"), 60)


def _invalidate_session_cache(token: str | None = None) -> None:
    """Limpa cache: remove um token especifico ou tudo."""
    with _session_cache_lock:
        if token is None:
            _session_cache.clear()
        else:
            _session_cache.pop(token, None)


class DatabaseIntegrityError(Exception):
    """Erro de integridade no banco (ex.: chave unica duplicada)."""



def _safe_int(value: str | None, fallback: int) -> int:
    """Converte string para inteiro positivo, com fallback seguro."""
    try:
        parsed = int(value) if value is not None else fallback
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback



def _build_database_url_from_parts() -> str:
    """Monta a URL do banco usando variaveis de ambiente separadas.

    Requer `DATABASE_PASSWORD` para evitar fallback inseguro em producao.
    """
    host = os.getenv("DATABASE_HOST", DEFAULT_DATABASE_HOST).strip() or DEFAULT_DATABASE_HOST
    port = _safe_int(os.getenv("DATABASE_PORT", str(DEFAULT_DATABASE_PORT)), DEFAULT_DATABASE_PORT)
    name = os.getenv("DATABASE_NAME", DEFAULT_DATABASE_NAME).strip() or DEFAULT_DATABASE_NAME
    user = os.getenv("DATABASE_USER", DEFAULT_DATABASE_USER).strip() or DEFAULT_DATABASE_USER
    password = os.getenv("DATABASE_PASSWORD", "").strip()
    sslmode = os.getenv("DATABASE_SSLMODE", DEFAULT_DATABASE_SSLMODE).strip() or DEFAULT_DATABASE_SSLMODE

    if not password:
        raise RuntimeError(
            "A variavel DATABASE_PASSWORD e obrigatoria quando DATABASE_URL nao estiver definida."
        )

    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/"
        f"{quote_plus(name)}?sslmode={sslmode}"
    )



def _normalize_database_url(database_url: str) -> str:
    """Normaliza prefixo legado `postgres://` para `postgresql://`."""
    value = database_url.strip()
    if value.startswith("postgres://"):
        return "postgresql://" + value[len("postgres://") :]
    return value



def _get_database_url() -> str:
    """Retorna URL final de conexao priorizando `DATABASE_URL`."""
    raw_database_url = os.getenv("DATABASE_URL", "").strip()
    if raw_database_url:
        return _normalize_database_url(raw_database_url)
    return _build_database_url_from_parts()



def _get_session_ttl_seconds() -> int:
    """Calcula TTL da sessao em segundos com base no ambiente."""
    ttl_hours = _safe_int(os.getenv("SESSION_TTL_HOURS", str(DEFAULT_SESSION_TTL_HOURS)), DEFAULT_SESSION_TTL_HOURS)
    return ttl_hours * 3600



def _get_pool() -> "psycopg2_pool.ThreadedConnectionPool":
    """Retorna (ou inicializa) o pool de conexoes com o banco."""
    global _connection_pool

    if psycopg2_pool is None:
        raise RuntimeError(
            "Driver PostgreSQL nao encontrado. Instale `psycopg2-binary` no ambiente do backend."
        )

    if _connection_pool is None:
        with _pool_lock:
            if _connection_pool is None:
                database_url = _get_database_url()
                min_conn = _safe_int(
                    os.getenv("DATABASE_POOL_MIN", str(DEFAULT_POOL_MIN_CONNECTIONS)),
                    DEFAULT_POOL_MIN_CONNECTIONS,
                )
                max_conn = _safe_int(
                    os.getenv("DATABASE_POOL_MAX", str(DEFAULT_POOL_MAX_CONNECTIONS)),
                    DEFAULT_POOL_MAX_CONNECTIONS,
                )
                timeout = _safe_int(
                    os.getenv("DATABASE_CONNECT_TIMEOUT", str(DEFAULT_DATABASE_CONNECT_TIMEOUT)),
                    DEFAULT_DATABASE_CONNECT_TIMEOUT,
                )
                _connection_pool = psycopg2_pool.ThreadedConnectionPool(
                    min_conn,
                    max_conn,
                    database_url,
                    connect_timeout=timeout,
                )

    return _connection_pool


@contextmanager
def _get_connection():
    """Empresta uma conexao do pool e a devolve ao terminar (com rollback em caso de erro)."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        pool.putconn(conn)



def ping_database() -> None:
    """Executa um ping simples no banco para healthcheck.

    Reusa o pool de conexoes para nao abrir TCP+TLS novo a cada healthcheck
    (evita esgotar `max_connections` do pooler em escala).
    """
    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
            if row is None or int(row[0]) != 1:
                raise RuntimeError("Falha no teste de conexao com PostgreSQL.")



def init_db() -> None:
    """Inicializa schema do banco uma unica vez por processo."""
    global _db_initialized
    if _db_initialized:
        return

    with _db_init_lock:
        if _db_initialized:
            return

        with _get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS usuarios (
                        id TEXT PRIMARY KEY,
                        nome TEXT NOT NULL,
                        email TEXT NOT NULL UNIQUE,
                        senha_hash TEXT NOT NULL,
                        criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS usuarios_sessoes (
                        token TEXT PRIMARY KEY,
                        usuario_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                        criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS contestacoes (
                        id BIGSERIAL PRIMARY KEY,
                        usuario_id TEXT,
                        numero_processo TEXT NOT NULL,
                        autor TEXT NOT NULL,
                        reu TEXT,
                        tipo_acao TEXT NOT NULL,
                        fatos TEXT NOT NULL,
                        pedido_autor TEXT NOT NULL,
                        arquivo_base TEXT,
                        arquivo_base_nome TEXT,
                        arquivo_base_mime_type TEXT,
                        arquivo_base_tamanho_bytes BIGINT,
                        texto_editado_ao_vivo TEXT,
                        status TEXT NOT NULL,
                        n8n_resposta JSONB,
                        criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

                # Ajustes para ambientes que ja tinham schema antigo.
                cursor.execute("ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS usuario_id TEXT")
                cursor.execute("ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS arquivo_base_nome TEXT")
                cursor.execute("ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS arquivo_base_mime_type TEXT")
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS arquivo_base_tamanho_bytes BIGINT"
                )

                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_usuarios_sessoes_criado_em ON usuarios_sessoes (criado_em)"
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_contestacoes_usuario_criado_em
                    ON contestacoes (usuario_id, criado_em DESC)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_contestacoes_usuario_status
                    ON contestacoes (usuario_id, status)
                    """
                )
            connection.commit()

        _db_initialized = True



def _ensure_db_initialized() -> None:
    """Garante inicializacao do schema antes de operacoes de escrita/leitura."""
    if not _db_initialized:
        init_db()



def cleanup_sessoes_expiradas(batch_size: int = 1000, max_batches: int = 50) -> int:
    """Remove sessoes expiradas em lotes para nao bloquear a tabela em produzao.

    Cada chamada do login dispara este cleanup; com 100k+ sessoes expiradas,
    um DELETE unico segura lock prolongado e prejudica logins concorrentes.
    Por isso deletamos em batches limitados (default 1000 linhas, ate 50 lotes
    por execucao = 50k registros). O restante e tratado na proxima chamada.
    """
    _ensure_db_initialized()
    ttl_seconds = _get_session_ttl_seconds()
    total_deleted = 0

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            for _ in range(max_batches):
                cursor.execute(
                    """
                    DELETE FROM usuarios_sessoes
                    WHERE token IN (
                        SELECT token FROM usuarios_sessoes
                        WHERE criado_em < (NOW() - (%s * INTERVAL '1 second'))
                        LIMIT %s
                    )
                    """,
                    (ttl_seconds, batch_size),
                )
                deleted_rows = cursor.rowcount or 0
                connection.commit()
                total_deleted += int(deleted_rows)
                if deleted_rows < batch_size:
                    break

    return total_deleted



def create_usuario(user_id: str, nome: str, email: str, senha_hash: str) -> dict[str, str]:
    """Cria usuario e devolve payload seguro (sem senha)."""
    _ensure_db_initialized()

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO usuarios (id, nome, email, senha_hash)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, nome, email
                    """,
                    (user_id, nome, email, senha_hash),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("Falha ao criar usuario no banco de dados.")
            except Exception as error:
                if psycopg2 is not None and isinstance(error, psycopg2.IntegrityError):
                    raise DatabaseIntegrityError("Conflito de integridade no banco.") from error
                raise
        connection.commit()

    return {
        "id": str(row[0]),
        "nome": str(row[1]),
        "email": str(row[2]),
    }



def update_usuario_senha_hash(usuario_id: str, novo_hash: str) -> None:
    """Atualiza apenas o hash da senha do usuario (re-hash transparente).

    Usado quando o login detecta hash com iteracoes PBKDF2 desatualizadas.
    """
    _ensure_db_initialized()

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE usuarios
                SET senha_hash = %s
                WHERE id = %s
                """,
                (novo_hash, usuario_id),
            )
        connection.commit()


def get_usuario_por_email(email: str) -> dict[str, str] | None:
    """Busca usuario por e-mail retornando hash de senha para login."""
    _ensure_db_initialized()

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, nome, email, senha_hash
                FROM usuarios
                WHERE email = %s
                LIMIT 1
                """,
                (email,),
            )
            row = cursor.fetchone()

    if row is None:
        return None

    return {
        "id": str(row[0]),
        "nome": str(row[1]),
        "email": str(row[2]),
        "senha_hash": str(row[3]),
    }



def create_sessao_usuario(usuario_id: str) -> str:
    """Cria sessao para o usuario e retorna token opaco."""
    import random
    _ensure_db_initialized()
    # Executa cleanup em ~2% dos logins para nao bloquear o fluxo de autenticacao.
    # Sessoes expiradas acumulam lentamente; limpeza probabilistica e suficiente.
    if random.random() < 0.02:
        cleanup_sessoes_expiradas()
    token = uuid4().hex

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO usuarios_sessoes (token, usuario_id)
                VALUES (%s, %s)
                """,
                (token, usuario_id),
            )
        connection.commit()

    return token



def get_sessao_ativa(token: str) -> dict[str, str] | None:
    """Valida token de sessao considerando expiracao por TTL.

    Usa cache em-memoria com TTL curto (default 60s) para evitar JOIN no
    Postgres a cada request autenticada. O TTL e curto o bastante para que
    revogacoes via /usuarios/logout sejam refletidas em <=60s mesmo que o
    invalidate sincrono falhe.
    """
    if not token:
        return None

    cache_ttl = _get_session_cache_ttl_seconds()
    now_epoch = time.monotonic()

    if cache_ttl > 0:
        with _session_cache_lock:
            cached = _session_cache.get(token)
            if cached and cached[0] > now_epoch:
                return dict(cached[1])

    _ensure_db_initialized()
    ttl_seconds = _get_session_ttl_seconds()

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, u.nome, u.email, s.token
                FROM usuarios_sessoes s
                JOIN usuarios u ON u.id = s.usuario_id
                WHERE s.token = %s
                  AND s.criado_em >= (NOW() - (%s * INTERVAL '1 second'))
                LIMIT 1
                """,
                (token, ttl_seconds),
            )
            row = cursor.fetchone()

    if row is None:
        # Garante que cache nao serve sessao recem-revogada/expirada.
        if cache_ttl > 0:
            _invalidate_session_cache(token)
        return None

    payload = {
        "id": str(row[0]),
        "nome": str(row[1]),
        "email": str(row[2]),
        "token": str(row[3]),
    }

    if cache_ttl > 0:
        with _session_cache_lock:
            _session_cache[token] = (now_epoch + cache_ttl, dict(payload))

    return payload



def revoke_sessao(token: str) -> bool:
    """Revoga sessao pelo token e devolve se havia registro."""
    _ensure_db_initialized()

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM usuarios_sessoes
                WHERE token = %s
                RETURNING token
                """,
                (token,),
            )
            row = cursor.fetchone()
        connection.commit()

    # Sincroniza cache para nao servir sessao revogada ate o TTL expirar.
    _invalidate_session_cache(token)

    return row is not None



def save_contestacao(payload: dict[str, Any], status: str, n8n_resposta: Any) -> int:
    """Persiste envio de contestacao e metadados do arquivo base."""
    _ensure_db_initialized()

    arquivo_nome = str(payload.get("arquivo_base_nome") or payload.get("arquivo_base") or "")
    arquivo_conteudo = str(payload.get("arquivo_base_conteudo_base64") or "")
    arquivo_mime_type = str(payload.get("arquivo_base_mime_type") or "")
    arquivo_tamanho_raw = payload.get("arquivo_base_tamanho_bytes")
    try:
        arquivo_tamanho = int(arquivo_tamanho_raw) if arquivo_tamanho_raw is not None else None
    except (TypeError, ValueError):
        arquivo_tamanho = None

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO contestacoes (
                    usuario_id,
                    numero_processo,
                    autor,
                    reu,
                    tipo_acao,
                    fatos,
                    pedido_autor,
                    arquivo_base,
                    arquivo_base_nome,
                    arquivo_base_mime_type,
                    arquivo_base_tamanho_bytes,
                    texto_editado_ao_vivo,
                    status,
                    n8n_resposta
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    str(payload.get("usuario_id") or ""),
                    str(payload.get("numero_processo", "")),
                    str(payload.get("autor", "")),
                    str(payload.get("reu", "")),
                    str(payload.get("tipo_acao", "")),
                    str(payload.get("fatos", "")),
                    str(payload.get("pedido_autor", "")),
                    arquivo_conteudo,
                    arquivo_nome,
                    arquivo_mime_type,
                    arquivo_tamanho,
                    str(payload.get("texto_editado_ao_vivo", "")),
                    status,
                    PGJsonAdapter(n8n_resposta) if PGJsonAdapter else n8n_resposta,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("Falha ao salvar contestacao no banco de dados.")
            inserted_id = row[0]
        connection.commit()

    return int(inserted_id)


def _format_case_id(contestacao_id: int, criado_em: datetime | None) -> str:
    """Monta id legivel para o dashboard mantendo ordenacao por ano."""
    case_year = criado_em.year if isinstance(criado_em, datetime) else datetime.now().year
    return f"CTR-{case_year}-{int(contestacao_id):06d}"


def _map_dashboard_status(status_value: str) -> tuple[str, str]:
    """Converte status tecnico para rotulos amigaveis no frontend."""
    normalized = status_value.strip().lower()
    if normalized == "ok":
        return ("Concluida", "Defesa editada")
    if normalized == "processando":
        return ("Em analise", "Defesa em processamento")
    if normalized in {"erro_validacao", "rejeitado"}:
        return ("Aguardando revisao", "Revisao de fundamentacao")
    if normalized == "erro":
        return ("Falha no envio", "Erro de integracao")
    return ("Em analise", "Defesa em processamento")


def list_contestacoes_por_usuario(usuario_id: str, limit: int = 20) -> list[dict[str, str]]:
    """Retorna historico do dashboard para o usuario autenticado."""
    _ensure_db_initialized()
    safe_limit = max(1, min(int(limit), 100))

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, tipo_acao, status, criado_em, numero_processo
                FROM contestacoes
                WHERE usuario_id = %s
                ORDER BY criado_em DESC
                LIMIT %s
                """,
                (usuario_id, safe_limit),
            )
            rows = cursor.fetchall()

    history: list[dict[str, str]] = []
    for row in rows:
        contestacao_id = int(row[0])
        natureza_caso = str(row[1] or "Nao informado")
        status_raw = str(row[2] or "")
        criado_em = row[3] if isinstance(row[3], datetime) else None
        numero_processo = str(row[4] or "").strip()
        status_label, tipo_label = _map_dashboard_status(status_raw)
        display_date = (criado_em or datetime.now()).strftime("%d/%m/%Y")

        history.append(
            {
                "id": _format_case_id(contestacao_id, criado_em),
                "naturezaCaso": natureza_caso,
                "tipo": tipo_label,
                "data": display_date,
                "status": status_label,
                "numeroProcesso": numero_processo,
            }
        )

    return history


def get_dashboard_cards_por_usuario(usuario_id: str) -> list[dict[str, str]]:
    """Retorna cards de resumo do dashboard calculados no PostgreSQL."""
    _ensure_db_initialized()
    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*)::BIGINT AS total,
                    COUNT(*) FILTER (WHERE status = 'ok')::BIGINT AS concluidas,
                    COUNT(*) FILTER (WHERE status = 'processando')::BIGINT AS em_analise,
                    COUNT(*) FILTER (
                        WHERE status IN ('erro', 'erro_validacao', 'rejeitado')
                    )::BIGINT AS pendencias
                FROM contestacoes
                WHERE usuario_id = %s
                """,
                (usuario_id,),
            )
            row = cursor.fetchone()

    total = int(row[0] or 0) if row else 0
    concluidas = int(row[1] or 0) if row else 0
    em_analise = int(row[2] or 0) if row else 0
    pendencias = int(row[3] or 0) if row else 0

    return [
        {"label": "Total de casos", "value": str(total)},
        {"label": "Concluidas", "value": str(concluidas)},
        {"label": "Em analise", "value": str(em_analise)},
        {"label": "Com pendencia", "value": str(pendencias)},
    ]

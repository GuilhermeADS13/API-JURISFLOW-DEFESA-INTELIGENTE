# pyright: reportMissingModuleSource=false

"""Camada de acesso a dados do sistema.

Este modulo centraliza:
- configuracao de conexao PostgreSQL com pool de conexoes,
- inicializacao do schema,
- operacoes de usuario/sessao,
- persistencia de contestacoes.
"""

import os
import re
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
    host = (
        os.getenv("DATABASE_HOST", DEFAULT_DATABASE_HOST).strip()
        or DEFAULT_DATABASE_HOST
    )
    port = _safe_int(
        os.getenv("DATABASE_PORT", str(DEFAULT_DATABASE_PORT)), DEFAULT_DATABASE_PORT
    )
    name = (
        os.getenv("DATABASE_NAME", DEFAULT_DATABASE_NAME).strip()
        or DEFAULT_DATABASE_NAME
    )
    user = (
        os.getenv("DATABASE_USER", DEFAULT_DATABASE_USER).strip()
        or DEFAULT_DATABASE_USER
    )
    password = os.getenv("DATABASE_PASSWORD", "").strip()
    sslmode = (
        os.getenv("DATABASE_SSLMODE", DEFAULT_DATABASE_SSLMODE).strip()
        or DEFAULT_DATABASE_SSLMODE
    )

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
    ttl_hours = _safe_int(
        os.getenv("SESSION_TTL_HOURS", str(DEFAULT_SESSION_TTL_HOURS)),
        DEFAULT_SESSION_TTL_HOURS,
    )
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
                    os.getenv(
                        "DATABASE_CONNECT_TIMEOUT",
                        str(DEFAULT_DATABASE_CONNECT_TIMEOUT),
                    ),
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
    except Exception:  # noqa: BLE001 - rollback intencional em qualquer erro; re-raise abaixo
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001 - rollback pode falhar se conexao morreu; ignorar e prosseguir
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
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS usuario_id TEXT"
                )
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS arquivo_base_nome TEXT"
                )
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS arquivo_base_mime_type TEXT"
                )
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS arquivo_base_tamanho_bytes BIGINT"
                )

                # Guia Tecnico v2: origem da contestacao ('formulario' | 'peticao')
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS origem TEXT DEFAULT 'formulario'"
                )

                # Guia Tecnico v3 / PR5 - HiL: confianca e flag de revisao humana
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS requer_revisao_humana BOOLEAN DEFAULT FALSE"
                )
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS dados_confianca REAL"
                )

                # PR5 - Observabilidade: golden dataset (minuta original IA vs editada humana)
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS minuta_json_original JSONB"
                )
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS minuta_json_editada JSONB"
                )

                # PR6 #4 - RAG Semantico: pgvector + coluna de embedding 384 dims
                # 384 dims = paraphrase-multilingual-MiniLM-L12-v2 (sentence-transformers, local).
                # Supabase ja tem pgvector disponivel — a extensao e no-op se ja existir.
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS fatos_embedding vector(384)"
                )
                # Migracao defensiva: se a coluna existir com dimensao antiga (1024 dos
                # providers pagos), troca para 384. Drop do indice e necessario antes
                # do ALTER COLUMN TYPE em pgvector.
                cursor.execute(
                    """
                    DO $$
                    DECLARE
                        atypmod integer;
                    BEGIN
                        SELECT atttypmod INTO atypmod
                        FROM pg_attribute
                        WHERE attrelid = 'contestacoes'::regclass
                          AND attname = 'fatos_embedding';
                        IF atypmod IS NOT NULL AND atypmod <> 384 THEN
                            DROP INDEX IF EXISTS idx_contestacoes_embedding_hnsw;
                            ALTER TABLE contestacoes
                              ALTER COLUMN fatos_embedding TYPE vector(384)
                              USING NULL;
                        END IF;
                    END $$;
                    """
                )
                # HNSW e o indice recomendado pelo pgvector para busca aproximada por coseno.
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_contestacoes_embedding_hnsw
                    ON contestacoes USING hnsw (fatos_embedding vector_cosine_ops)
                    """
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

                # Fase 2: feedback loop — adiciona colunas se nao existirem
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS feedback_util BOOLEAN"
                )
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS feedback_comentario TEXT"
                )
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS feedback_em TIMESTAMPTZ"
                )
                # Persiste modelo .docx do escritorio para regerar peca depois
                # (endpoint /baixar precisa, senao cai no fallback sem timbre).
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS modelo_base_b64 TEXT"
                )
                cursor.execute(
                    "ALTER TABLE contestacoes ADD COLUMN IF NOT EXISTS modelo_base_nome TEXT"
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_contestacoes_tipo_feedback
                    ON contestacoes (tipo_acao, feedback_util, criado_em DESC)
                    """
                )

                # Fase 2: tabela de contestacoes exemplares (curadoria admin)
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS contestacoes_exemplares (
                        id                  BIGSERIAL PRIMARY KEY,
                        tipo_acao           TEXT NOT NULL,
                        tese_central        TEXT NOT NULL,
                        fundamentos_resumo  TEXT NOT NULL,
                        nota_qualidade      SMALLINT NOT NULL DEFAULT 5
                            CHECK (nota_qualidade BETWEEN 1 AND 10),
                        criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_exemplares_tipo_acao
                    ON contestacoes_exemplares (tipo_acao, nota_qualidade DESC)
                    """
                )

                # PR9 P1.2 — tabela `configuracoes` (chave/valor) para guardar
                # o `modelo_mae_contestacao` (texto do template padrao do escritorio)
                # e outras configuracoes globais. n8n workflow `contestacao-claude`
                # busca via REST API quando o frontend nao envia o modelo no payload.
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS configuracoes (
                        chave           TEXT PRIMARY KEY,
                        valor           TEXT NOT NULL,
                        atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            # PR8 P2.4 — commit + rollback explicito em volta das migrations.
            # Captura tanto falha em commit() quanto falha em algum execute()
            # acima (ja propagada antes daqui pela maquina de excecoes do with).
            # O rollback explicito documenta intencao e cobre o caso de psycopg
            # manter transacao aberta apos erro de DDL.
            try:
                connection.commit()
            except Exception:  # noqa: BLE001 - rollback + re-raise para nao deixar transacao aberta
                connection.rollback()
                raise

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


def create_usuario(
    user_id: str, nome: str, email: str, senha_hash: str
) -> dict[str, str]:
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
            except Exception as error:  # noqa: BLE001 - filtra IntegrityError via isinstance + re-raise demais
                if psycopg2 is not None and isinstance(error, psycopg2.IntegrityError):
                    raise DatabaseIntegrityError(
                        "Conflito de integridade no banco."
                    ) from error
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


def _extrair_metadados_arquivo(
    payload: dict[str, Any],
) -> tuple[str, str, str, int | None]:
    """Extrai (nome, conteudo_base64, mime_type, tamanho) com fallbacks seguros."""
    nome = str(
        payload.get("arquivo_base_nome") or payload.get("arquivo_base") or ""
    )
    conteudo = str(payload.get("arquivo_base_conteudo_base64") or "")
    mime_type = str(payload.get("arquivo_base_mime_type") or "")

    tamanho_raw = payload.get("arquivo_base_tamanho_bytes")
    try:
        tamanho = int(tamanho_raw) if tamanho_raw is not None else None
    except (TypeError, ValueError):
        tamanho = None

    return nome, conteudo, mime_type, tamanho


def _adaptar_json_pg(value: Any) -> Any:
    """Envelopa em PGJsonAdapter quando disponivel; preserva None/falsy intacto."""
    if PGJsonAdapter and value:
        return PGJsonAdapter(value)
    return value


def save_contestacao(
    payload: dict[str, Any],
    status: str,
    n8n_resposta: Any,
    *,
    origem: str = "formulario",
    requer_revisao_humana: bool = False,
    dados_confianca: float | None = None,
    minuta_json_original: dict | None = None,
) -> int:
    """Persiste envio de contestacao e metadados do arquivo base.

    `origem` distingue o fluxo: 'formulario' (entrada manual) ou 'peticao'
    (a partir de upload de peticao inicial via /contestar-por-peticao).

    `requer_revisao_humana` + `dados_confianca` (PR5 HiL): marcam a
    contestacao para revisao do advogado quando a IA teve baixa confianca
    na extracao dos dados.

    `minuta_json_original` (PR5 Observabilidade): JSON da minuta gerada
    pela IA antes de qualquer edicao do humano, para futuro fine-tuning.
    """
    _ensure_db_initialized()

    nome, conteudo, mime_type, tamanho = _extrair_metadados_arquivo(payload)
    confianca = float(dados_confianca) if dados_confianca is not None else None

    # Modelo do escritorio (.docx com timbre/template) — persiste para
    # regenerar o DOCX depois via /contestacoes/{id}/baixar.
    modelo_b64 = str(payload.get("modelo_base_b64") or "")
    modelo_nome = str(payload.get("modelo_base_nome") or "")

    # PR13 #B1: metadados juridicos. area_juridica vem (a) do payload se o
    # Extrator do n8n preencheu, ou (b) derivada de tipo_acao pelo classificador.
    # resultado entra default None — preenchido manualmente depois pelo advogado.
    tipo_acao_str = str(payload.get("tipo_acao", ""))
    area_juridica = payload.get("area_juridica")
    if area_juridica not in AREAS_JURIDICAS_CANONICAS:
        area_juridica = _classificar_area_juridica(tipo_acao_str)
    resultado_payload = payload.get("resultado")
    if resultado_payload not in ("procedente", "improcedente", "parcial", "em_andamento"):
        resultado_payload = None

    params = (
        str(payload.get("usuario_id") or ""),
        str(payload.get("numero_processo", "")),
        str(payload.get("autor", "")),
        str(payload.get("reu", "")),
        tipo_acao_str,
        str(payload.get("fatos", "")),
        str(payload.get("pedido_autor", "")),
        conteudo,
        nome,
        mime_type,
        tamanho,
        str(payload.get("texto_editado_ao_vivo", "")),
        status,
        _adaptar_json_pg(n8n_resposta) if PGJsonAdapter else n8n_resposta,
        origem,
        bool(requer_revisao_humana),
        confianca,
        _adaptar_json_pg(minuta_json_original),
        modelo_b64,
        modelo_nome,
        area_juridica,
        resultado_payload,
    )

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
                    n8n_resposta,
                    origem,
                    requer_revisao_humana,
                    dados_confianca,
                    minuta_json_original,
                    modelo_base_b64,
                    modelo_base_nome,
                    area_juridica,
                    resultado
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                params,
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("Falha ao salvar contestacao no banco de dados.")
            inserted_id = row[0]
        connection.commit()

    return int(inserted_id)


def _format_case_id(contestacao_id: int, criado_em: datetime | None) -> str:
    """Monta id legivel para o dashboard mantendo ordenacao por ano."""
    case_year = (
        criado_em.year if isinstance(criado_em, datetime) else datetime.now().year
    )
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


def list_contestacoes_por_usuario(
    usuario_id: str, limit: int = 20
) -> list[dict[str, str]]:
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
        # Converte para fuso Brasil (UTC-3). criado_em vem aware do Postgres.
        from datetime import timedelta, timezone
        tz_br = timezone(timedelta(hours=-3))
        criado_local = (criado_em or datetime.now(tz_br)).astimezone(tz_br) if criado_em else datetime.now(tz_br)
        display_date = criado_local.strftime("%d/%m/%Y %H:%M")

        history.append(
            {
                "id": _format_case_id(contestacao_id, criado_em),
                "contestacao_id": contestacao_id,
                "naturezaCaso": natureza_caso,
                "tipo": tipo_label,
                "data": display_date,
                "status": status_label,
                "statusRaw": status_raw,
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


def salvar_feedback(
    contestacao_id: int,
    usuario_id: str,
    util: bool,
    comentario: str | None,
) -> bool:
    """Persiste feedback do advogado sobre a minuta.

    Retorna True se a contestacao existia e pertencia ao usuario, False caso contrario.
    """
    _ensure_db_initialized()

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE contestacoes
                SET feedback_util       = %s,
                    feedback_comentario = %s,
                    feedback_em         = NOW()
                WHERE id = %s
                  AND usuario_id = %s
                """,
                (util, comentario, contestacao_id, usuario_id),
            )
            updated = cursor.rowcount
        connection.commit()

    return updated > 0


def get_contestacoes_exemplares(tipo_acao: str) -> list[dict[str, Any]]:
    """Retorna exemplares curados para o tipo_acao, ordenados por nota_qualidade DESC.

    Usados pelo workflow n8n como few-shot examples no system prompt do agente Claude.
    """
    _ensure_db_initialized()

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tipo_acao, tese_central, fundamentos_resumo, nota_qualidade
                FROM contestacoes_exemplares
                WHERE tipo_acao = %s
                ORDER BY nota_qualidade DESC
                LIMIT 3
                """,
                (tipo_acao,),
            )
            rows = cursor.fetchall()

    return [
        {
            "tipo_acao": row[0],
            "tese_central": row[1],
            "fundamentos_resumo": row[2],
            "nota_qualidade": row[3],
        }
        for row in rows
    ]


def get_contestacao(contestacao_id: int, usuario_id: str) -> dict[str, Any] | None:
    """Busca contestacao por id + usuario (defesa em profundidade contra IDOR).

    Retorna dict com campos relevantes para HiL/Observabilidade ou None se nao
    existe ou nao pertence ao usuario.
    """
    _ensure_db_initialized()

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, usuario_id, status, origem, n8n_resposta,
                       requer_revisao_humana, dados_confianca,
                       minuta_json_original, minuta_json_editada,
                       numero_processo, autor, reu, tipo_acao
                FROM contestacoes
                WHERE id = %s AND usuario_id = %s
                LIMIT 1
                """,
                (contestacao_id, usuario_id),
            )
            row = cursor.fetchone()

    if row is None:
        return None

    return {
        "id": int(row[0]),
        "usuario_id": str(row[1]),
        "status": str(row[2] or ""),
        "origem": str(row[3] or "formulario"),
        "n8n_resposta": row[4],
        "requer_revisao_humana": bool(row[5]) if row[5] is not None else False,
        "dados_confianca": float(row[6]) if row[6] is not None else None,
        "minuta_json_original": row[7],
        "minuta_json_editada": row[8],
        "numero_processo": str(row[9] or ""),
        "autor": str(row[10] or ""),
        "reu": str(row[11] or ""),
        "tipo_acao": str(row[12] or ""),
    }


def get_contestacao_para_download(
    contestacao_id: int, usuario_id: str
) -> dict[str, Any] | None:
    """Busca contestacao incluindo arquivo_base (modelo .docx) para regerar DOCX.

    Usada pelo endpoint GET /contestacoes/{id}/baixar quando o frontend perde a
    response inicial (timeout/abort) mas a peca ja foi processada e salva.
    IDOR-safe: filtra por usuario_id.
    """
    _ensure_db_initialized()
    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, n8n_resposta, modelo_base_b64, numero_processo,
                       autor, reu, tipo_acao, status, minuta_json_editada
                FROM contestacoes
                WHERE id = %s AND usuario_id = %s
                LIMIT 1
                """,
                (contestacao_id, usuario_id),
            )
            row = cursor.fetchone()
    if row is None:
        return None
    return {
        "id": int(row[0]),
        "n8n_resposta": row[1] or {},
        "modelo_base_b64": row[2],
        "numero_processo": str(row[3] or ""),
        "autor": str(row[4] or ""),
        "reu": str(row[5] or ""),
        "tipo_acao": str(row[6] or ""),
        "status": str(row[7] or ""),
        "minuta_json_editada": row[8],
    }


def excluir_contestacao(contestacao_id: int, usuario_id: str) -> bool:
    """Deleta contestacao do usuario. IDOR-safe via WHERE usuario_id = %s.

    Retorna True se deletou 1 registro, False se nao encontra (id inexistente
    OU pertence a outro usuario — o caller traduz para HTTP 404).
    """
    _ensure_db_initialized()
    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM contestacoes WHERE id = %s AND usuario_id = %s",
                (contestacao_id, usuario_id),
            )
            apagou = cursor.rowcount > 0
        connection.commit()
        return apagou


def atualizar_contestacao_pos_revisao(
    contestacao_id: int,
    usuario_id: str,
    minuta_nova: dict,
    n8n_resposta_nova: Any,
    dados_extraidos_corrigidos: dict,
) -> bool:
    """Atualiza contestacao apos confirmacao do humano (PR5 HiL).

    Move status para 'ok', limpa flag de revisao, atualiza minuta_json_original
    com a versao final (gerada com dados corrigidos pelo humano), e atualiza
    o n8n_resposta com a nova execucao.

    Tambem atualiza fatos/pedidos/autor/reu/tipo_acao caso o humano tenha
    corrigido os dados extraidos pela IA.
    """
    _ensure_db_initialized()

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE contestacoes
                SET status = 'ok',
                    requer_revisao_humana = FALSE,
                    minuta_json_original = %s,
                    n8n_resposta = %s,
                    autor = %s,
                    reu = %s,
                    tipo_acao = %s,
                    numero_processo = %s,
                    fatos = %s
                WHERE id = %s AND usuario_id = %s
                """,
                (
                    PGJsonAdapter(minuta_nova) if PGJsonAdapter else minuta_nova,
                    PGJsonAdapter(n8n_resposta_nova)
                    if PGJsonAdapter
                    else n8n_resposta_nova,
                    str(dados_extraidos_corrigidos.get("autor", "")),
                    str(dados_extraidos_corrigidos.get("reu", "")),
                    str(dados_extraidos_corrigidos.get("tipo_acao", "")),
                    str(
                        dados_extraidos_corrigidos.get("numero_processo", "")
                        or "a definir"
                    ),
                    str(dados_extraidos_corrigidos.get("fatos_resumo", "")),
                    contestacao_id,
                    usuario_id,
                ),
            )
            updated = cursor.rowcount
        connection.commit()

    return updated > 0


def salvar_minuta_editada(
    contestacao_id: int,
    usuario_id: str,
    minuta_editada: dict,
) -> bool:
    """Persiste minuta editada pelo advogado (PR5 Observabilidade).

    Mantem `minuta_json_original` intacta para diff posterior e fine-tuning.
    Retorna True se atualizou, False se a contestacao nao existe ou nao
    pertence ao usuario.
    """
    _ensure_db_initialized()

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE contestacoes
                SET minuta_json_editada = %s
                WHERE id = %s AND usuario_id = %s
                """,
                (
                    PGJsonAdapter(minuta_editada) if PGJsonAdapter else minuta_editada,
                    contestacao_id,
                    usuario_id,
                ),
            )
            updated = cursor.rowcount
        connection.commit()

    return updated > 0


def _format_pgvector(embedding: list[float]) -> str:
    """Serializa lista de floats para o literal do tipo `vector` do pgvector."""
    return "[" + ",".join(f"{v:.10f}" for v in embedding) + "]"


def _extrair_minuta(n8n_resposta: Any) -> dict:
    if isinstance(n8n_resposta, dict):
        return n8n_resposta.get("minuta") or {}
    return {}


def _iso_or_str(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "")


# PR13 #B1: areas juridicas canonicas. Lista fechada — qualquer string fora
# disso fica como None em area_juridica (conservador). Filtros do RAG
# downstream so usam essas chaves.
AREAS_JURIDICAS_CANONICAS = frozenset({
    "trabalhista",
    "consumidor",
    "bancario",
    "previdenciario",
    "civel",
})

# Mapeamento keyword -> area canonica. Primeira chave que casa decide.
# Mantemos ordenado por especificidade (mais especifico primeiro) pra evitar
# que "previdenciario" case com "civel" generico via "responsab".
_AREA_KEYWORDS = (
    ("trabalhista", ("trabalh", "clt ", "celetist", "rescis", "horas extras", "fgts", "ctps", "verbas rescis")),
    ("previdenciario", ("previd", "inss", "aposent", "beneficio", "lei 8213")),
    ("consumidor", ("consumidor", "cdc", "compra ", "produto defeituoso", "vicio do produto", "lei 8078")),
    ("bancario", ("banc", "financ", "emprestim", "credito consig", "cartao de credito")),
    ("civel", ("civel", "contrat", "responsabil", "danos materiais", "cpc ")),
)


def _classificar_area_juridica(tipo_acao: str | None) -> str | None:
    """Mapeia tipo_acao livre para area canonica. Conservador: se nao casar, None.

    Hoje 100% das contestacoes do projeto sao trabalhistas, mas o classificador
    ja eh estruturado pra cinco areas porque o RAG fica multi-tenant + multi-area
    naturalmente. Comeca declarar area, dps adiciona filtros downstream.
    """
    if not tipo_acao:
        return None
    t = tipo_acao.lower()
    for area, kws in _AREA_KEYWORDS:
        if any(k in t for k in kws):
            return area
    return None


def _row_to_defesa_semantica(row: tuple) -> dict[str, Any]:
    """Mapeia tupla do SELECT de `buscar_defesas_semanticas` para dict de resposta."""
    minuta = _extrair_minuta(row[4])
    return {
        "numero_processo": str(row[0] or ""),
        "tipo_acao": str(row[1] or ""),
        "fatos": str(row[2] or ""),
        "pedido_autor": str(row[3] or ""),
        "feedback_util": row[5],
        "criado_em": _iso_or_str(row[6]),
        "similarity": float(row[7] or 0.0),
        "tese_central": str(minuta.get("tese_central") or ""),
        "resumo_estrategico": str(minuta.get("resumo_estrategico") or ""),
        "fundamentos_curtos": str(minuta.get("fundamentos") or "")[:1500],
        "riscos": list((minuta.get("riscos") or [])[:3]),
    }


def salvar_embedding(contestacao_id: int, embedding: list[float]) -> None:
    """Persiste o embedding semantico (384 dims, sentence-transformers) para uma contestacao.

    Chamado em background (fire-and-forget) apos save_contestacao para nao
    adicionar latencia ao retorno da rota principal.
    """
    _ensure_db_initialized()
    vec_str = _format_pgvector(embedding)
    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE contestacoes SET fatos_embedding = %s::vector WHERE id = %s",
                (vec_str, contestacao_id),
            )
        connection.commit()


# ─────────────────────────────────────────────────────────────────────────────
# PR13 #B2: Cache de OCR (Tesseract por SHA-256 do PDF)
# ─────────────────────────────────────────────────────────────────────────────


def get_ocr_cache(file_hash: str) -> str | None:
    """Retorna texto OCR cacheado pra file_hash ou None. Bumpa ultimo_uso_em."""
    if not file_hash or len(file_hash) != 64:  # SHA-256 hex = 64 chars
        return None
    _ensure_db_initialized()
    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE ocr_cache SET ultimo_uso_em = now()
                WHERE file_hash = %s
                RETURNING texto_extraido
                """,
                (file_hash,),
            )
            row = cursor.fetchone()
        connection.commit()
    return row[0] if row else None


def set_ocr_cache(file_hash: str, texto: str, paginas: int | None = None) -> None:
    """Persiste texto OCR. UPSERT por file_hash — re-OCR sobrescreve (raro mas seguro)."""
    if not file_hash or len(file_hash) != 64:
        return
    if not texto:
        return
    _ensure_db_initialized()
    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO ocr_cache (file_hash, texto_extraido, paginas_processadas)
                VALUES (%s, %s, %s)
                ON CONFLICT (file_hash) DO UPDATE
                  SET texto_extraido = EXCLUDED.texto_extraido,
                      paginas_processadas = EXCLUDED.paginas_processadas,
                      ultimo_uso_em = now()
                """,
                (file_hash, texto, paginas),
            )
        connection.commit()


def buscar_defesas_semanticas(
    embedding: list[float],
    tipo_acao: str,
    excluir_numero: str,
    *,
    usuario_id: str | None,
    limit: int = 10,
    area_juridica: str | None = None,
) -> list[dict[str, Any]]:
    """Busca contestacoes anteriores similares via distancia coseno (pgvector <=>).

    Retorna lista de dicts com metadados e score de similaridade [0, 1].
    So considera contestacoes com status='ok' e fatos_embedding preenchido.

    Multi-tenant: filtra por usuario_id para nao vazar defesas entre escritorios.
    Exemplares marcados como 'humano' em engine_ia.provider sao COMPARTILHADOS
    (visiveis a todos os usuarios) — sao a base de conhecimento curada do
    sistema. Se usuario_id for None, so retorna exemplares humanos.
    """
    _ensure_db_initialized()

    # Guard: tipo_acao vazio ou whitespace nao deve casar com tudo via ILIKE '%'.
    if not tipo_acao or not tipo_acao.strip():
        return []

    vec_str = _format_pgvector(embedding)
    safe_limit = max(1, min(int(limit), 20))

    # Casa "Trabalhista" com "Trabalhista - Horas Extras e Verbas Rescisorias":
    # extrai a raiz antes do hifen/traco e escapa wildcards LIKE para evitar
    # injecao de padrao quando tipo_acao vem de fonte nao confiavel (IA).
    raiz_tipo = tipo_acao.split("-", 1)[0].strip()
    raiz_segura = (
        raiz_tipo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    if not raiz_segura:
        # tipo_acao malformado (so contem hifen, e.g. '-' ou '- foo'). Sem raiz
        # confiavel, abandona a busca para nao retornar resultados aleatorios.
        return []
    pattern_tipo = f"{raiz_segura}%"

    # PR13 #B1: filtro opcional por area_juridica canonica. Quando preenchida,
    # restringe ainda mais o universo de candidatos antes do ANN. None = sem filtro.
    area_canonica = area_juridica if area_juridica in AREAS_JURIDICAS_CANONICAS else None

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    numero_processo,
                    tipo_acao,
                    fatos,
                    pedido_autor,
                    n8n_resposta,
                    feedback_util,
                    criado_em,
                    1 - (fatos_embedding <=> %s::vector) AS similarity
                FROM contestacoes
                WHERE status = 'ok'
                  AND tipo_acao ILIKE %s ESCAPE '\\'
                  AND fatos_embedding IS NOT NULL
                  AND (%s::text IS NULL OR area_juridica = %s)
                  AND (
                    usuario_id = %s
                    OR (n8n_resposta::jsonb->'engine_ia'->>'provider' = 'humano')
                  )
                  AND (
                    numero_processo != %s
                    OR (n8n_resposta::jsonb->'engine_ia'->>'provider' = 'humano')
                  )
                ORDER BY fatos_embedding <=> %s::vector ASC
                LIMIT %s
                """,
                (
                    vec_str,
                    pattern_tipo,
                    area_canonica,
                    area_canonica,
                    usuario_id or "__sem_usuario__",
                    excluir_numero,
                    vec_str,
                    safe_limit,
                ),
            )
            rows = cursor.fetchall()

    return [_row_to_defesa_semantica(row) for row in rows]


def _row_to_defesa_lexical(row: tuple) -> dict[str, Any]:
    """Mapeia tupla do SELECT de `buscar_defesas_lexicais` para dict de resposta.

    Mesmo shape de `_row_to_defesa_semantica`, mas com `rank` (ts_rank_cd) no
    lugar de `similarity` — ambos serao normalizados via RRF na hibrida.
    """
    minuta = _extrair_minuta(row[4])
    return {
        "numero_processo": str(row[0] or ""),
        "tipo_acao": str(row[1] or ""),
        "fatos": str(row[2] or ""),
        "pedido_autor": str(row[3] or ""),
        "feedback_util": row[5],
        "criado_em": _iso_or_str(row[6]),
        "rank": float(row[7] or 0.0),
        "tese_central": str(minuta.get("tese_central") or ""),
        "resumo_estrategico": str(minuta.get("resumo_estrategico") or ""),
        "fundamentos_curtos": str(minuta.get("fundamentos") or "")[:1500],
        "riscos": list((minuta.get("riscos") or [])[:3]),
    }


# Tokens de stopwords/pontuacao que o `plainto_tsquery` consome silenciosamente
# em portugues. Aqui filtramos no Python o que ja sabemos que nao vai ranquear
# bem — evita query degenerada quando o input do extrator vem so com conectivos.
_LEXICAL_STOPCHARS_RX = re.compile(r"[^\w\sÀ-ÿ]+")


def _normalizar_query_lexical(texto: str) -> str:
    """Normaliza a query antes de jogar no plainto_tsquery.

    plainto_tsquery aceita texto livre (faz parsing interno), mas vale higienizar
    para nao gerar 0 hits por uso de aspas/pontuacao que o dicionario portuguese
    nao espera. Mantem acentos (dicionario faz folding).
    """
    if not texto:
        return ""
    limpa = _LEXICAL_STOPCHARS_RX.sub(" ", texto)
    return " ".join(limpa.split())[:2000]  # cap defensivo


def buscar_defesas_lexicais(
    texto_query: str,
    tipo_acao: str,
    excluir_numero: str,
    *,
    usuario_id: str | None,
    limit: int = 10,
    area_juridica: str | None = None,
) -> list[dict[str, Any]]:
    """Busca contestacoes anteriores por similaridade lexical (BM25-like via ts_rank_cd).

    Complementa `buscar_defesas_semanticas`: a vetorial captura sinonimia/parafrase,
    a lexical captura termos juridicos exatos (Sumulas, artigos, expressoes
    cristalizadas) que embeddings densos de 384d podem ranquear baixo.

    Usa o tsvector `fatos_tsv` (GENERATED ALWAYS, ver migration
    `20260605000000_add_fatos_tsv_for_hybrid_rag_search`) com o dicionario
    'portuguese' (stemming + stopwords). `ts_rank_cd` aplica peso 1.0 para o
    documento inteiro — equivale a "BM25 sem normalizacao por tamanho", que e
    o que queremos pra peticoes (tamanho varia muito sem refletir relevancia).

    Multi-tenant + exemplares humanos: mesmo filtro de
    `buscar_defesas_semanticas` (usuario_id OR provider='humano').
    """
    # Guards antes do _ensure_db_initialized() pra evitar custo de inicializar
    # pool em chamadas degeneradas (texto vazio, tipo vazio).
    if not tipo_acao or not tipo_acao.strip():
        return []

    query_normalizada = _normalizar_query_lexical(texto_query)
    if not query_normalizada:
        return []

    raiz_tipo = tipo_acao.split("-", 1)[0].strip()
    raiz_segura = (
        raiz_tipo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    if not raiz_segura:
        return []
    pattern_tipo = f"{raiz_segura}%"

    safe_limit = max(1, min(int(limit), 20))

    # PR13 #B1: filtro opcional por area_juridica canonica (mesmo padrao da semantica).
    area_canonica = area_juridica if area_juridica in AREAS_JURIDICAS_CANONICAS else None

    _ensure_db_initialized()

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    numero_processo,
                    tipo_acao,
                    fatos,
                    pedido_autor,
                    n8n_resposta,
                    feedback_util,
                    criado_em,
                    ts_rank_cd(fatos_tsv, plainto_tsquery('portuguese', %s)) AS rank
                FROM contestacoes
                WHERE status = 'ok'
                  AND tipo_acao ILIKE %s ESCAPE '\\'
                  AND fatos_tsv @@ plainto_tsquery('portuguese', %s)
                  AND (%s::text IS NULL OR area_juridica = %s)
                  AND (
                    usuario_id = %s
                    OR (n8n_resposta::jsonb->'engine_ia'->>'provider' = 'humano')
                  )
                  AND (
                    numero_processo != %s
                    OR (n8n_resposta::jsonb->'engine_ia'->>'provider' = 'humano')
                  )
                ORDER BY rank DESC
                LIMIT %s
                """,
                (
                    query_normalizada,
                    pattern_tipo,
                    query_normalizada,
                    area_canonica,
                    area_canonica,
                    usuario_id or "__sem_usuario__",
                    excluir_numero,
                    safe_limit,
                ),
            )
            rows = cursor.fetchall()

    return [_row_to_defesa_lexical(row) for row in rows]


# ─────────────────────────────────────────────────────────────────────────────
# PR13 #B3: Base de legislacao curada (busca hibrida tsvector + pgvector)
# ─────────────────────────────────────────────────────────────────────────────


def upsert_legislacao(
    origem: str,
    numero: str,
    texto: str,
    *,
    area_juridica: str | None = None,
    embedding: list[float] | None = None,
) -> None:
    """UPSERT em public.legislacao por (origem, numero). Usado pelo script de ingestao."""
    if not origem or not numero or not texto:
        return
    _ensure_db_initialized()
    vec_str = _format_pgvector(embedding) if embedding else None
    area = area_juridica if area_juridica in AREAS_JURIDICAS_CANONICAS else None
    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO legislacao (origem, numero, texto, area_juridica, embedding)
                VALUES (%s, %s, %s, %s, %s::vector)
                ON CONFLICT (origem, numero) DO UPDATE
                  SET texto = EXCLUDED.texto,
                      area_juridica = EXCLUDED.area_juridica,
                      embedding = EXCLUDED.embedding
                """,
                (origem, numero, texto, area, vec_str),
            )
        connection.commit()


def _row_to_legislacao(row: tuple) -> dict[str, Any]:
    """Mapeia tupla do SELECT de buscar_legislacao para dict."""
    return {
        "origem": str(row[0] or ""),
        "numero": str(row[1] or ""),
        "texto": str(row[2] or ""),
        "area_juridica": str(row[3] or "") if row[3] else None,
        "score": float(row[4] or 0.0),
    }


def buscar_legislacao_semantica(
    embedding: list[float],
    *,
    area_juridica: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Busca legislacao por similaridade vetorial (cosine).

    Sem multi-tenant: legislacao eh recurso compartilhado (lei eh lei).
    Filtro opcional por area_juridica reduz ruido (ex: pega CLT e CF mas
    nao CDC quando area=trabalhista).
    """
    _ensure_db_initialized()
    vec_str = _format_pgvector(embedding)
    safe_limit = max(1, min(int(limit), 10))
    area_canonica = area_juridica if area_juridica in AREAS_JURIDICAS_CANONICAS else None

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    origem, numero, texto, area_juridica,
                    1 - (embedding <=> %s::vector) AS score
                FROM legislacao
                WHERE embedding IS NOT NULL
                  AND (%s::text IS NULL OR area_juridica IS NULL OR area_juridica = %s)
                ORDER BY embedding <=> %s::vector ASC
                LIMIT %s
                """,
                (vec_str, area_canonica, area_canonica, vec_str, safe_limit),
            )
            rows = cursor.fetchall()
    return [_row_to_legislacao(row) for row in rows]


def buscar_legislacao_lexical(
    texto_query: str,
    *,
    area_juridica: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Busca legislacao por ranking lexical (ts_rank_cd + plainto_tsquery)."""
    query_normalizada = _normalizar_query_lexical(texto_query)
    if not query_normalizada:
        return []
    safe_limit = max(1, min(int(limit), 10))
    area_canonica = area_juridica if area_juridica in AREAS_JURIDICAS_CANONICAS else None

    _ensure_db_initialized()
    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    origem, numero, texto, area_juridica,
                    ts_rank_cd(texto_tsv, plainto_tsquery('portuguese', %s)) AS score
                FROM legislacao
                WHERE texto_tsv @@ plainto_tsquery('portuguese', %s)
                  AND (%s::text IS NULL OR area_juridica IS NULL OR area_juridica = %s)
                ORDER BY score DESC
                LIMIT %s
                """,
                (
                    query_normalizada,
                    query_normalizada,
                    area_canonica,
                    area_canonica,
                    safe_limit,
                ),
            )
            rows = cursor.fetchall()
    return [_row_to_legislacao(row) for row in rows]


def salvar_exemplar(
    tipo_acao: str,
    tese_central: str,
    fundamentos_resumo: str,
    nota_qualidade: int = 5,
) -> int:
    """Insere uma contestacao exemplar (endpoint admin). Retorna o id criado."""
    _ensure_db_initialized()

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO contestacoes_exemplares
                    (tipo_acao, tese_central, fundamentos_resumo, nota_qualidade)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (tipo_acao, tese_central, fundamentos_resumo, nota_qualidade),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("Falha ao inserir exemplar.")
            inserted_id = row[0]
        connection.commit()

    return int(inserted_id)


# ── PR9 P1.2 — CRUD da tabela `configuracoes` ────────────────────────────────


def obter_configuracao(chave: str) -> str | None:
    """Busca o valor de uma chave da tabela `configuracoes`. None se nao existe.

    Usado pelo n8n workflow `contestacao-claude` (via REST API do Supabase)
    quando o frontend nao envia `modelo_mae_texto` no payload.
    """
    _ensure_db_initialized()

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT valor FROM configuracoes WHERE chave = %s LIMIT 1",
                (chave,),
            )
            row = cursor.fetchone()
    return str(row[0]) if row else None


def salvar_configuracao(chave: str, valor: str) -> None:
    """Upsert numa chave da tabela `configuracoes`."""
    _ensure_db_initialized()

    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO configuracoes (chave, valor)
                VALUES (%s, %s)
                ON CONFLICT (chave) DO UPDATE
                  SET valor = EXCLUDED.valor,
                      atualizado_em = NOW()
                """,
                (chave, valor),
            )
        connection.commit()

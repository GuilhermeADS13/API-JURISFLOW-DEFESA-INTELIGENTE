"""PR9 P1.2 — testes da migration `configuracoes` (chave/valor)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_mock_conn(fetchone_result=None):
    """Mock psycopg2 connection + cursor context-managers."""
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = fetchone_result
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)
    return mock_conn, mock_cur


def test_obter_configuracao_retorna_valor_quando_existe():
    """SELECT valor FROM configuracoes WHERE chave = ... LIMIT 1."""
    from App import database as db

    mock_conn, mock_cur = _make_mock_conn(fetchone_result=("Modelo do escritorio.",))
    with (
        patch.object(db, "_get_connection") as mock_gc,
        patch.object(db, "_ensure_db_initialized"),
    ):
        mock_gc.return_value.__enter__ = lambda s: mock_conn
        mock_gc.return_value.__exit__ = MagicMock(return_value=False)

        valor = db.obter_configuracao("modelo_mae_contestacao")

    assert valor == "Modelo do escritorio."
    sql, params = mock_cur.execute.call_args.args
    assert "SELECT valor FROM configuracoes" in sql
    assert "WHERE chave = %s" in sql
    assert params == ("modelo_mae_contestacao",)


def test_obter_configuracao_retorna_none_quando_chave_inexistente():
    from App import database as db

    mock_conn, _ = _make_mock_conn(fetchone_result=None)
    with (
        patch.object(db, "_get_connection") as mock_gc,
        patch.object(db, "_ensure_db_initialized"),
    ):
        mock_gc.return_value.__enter__ = lambda s: mock_conn
        mock_gc.return_value.__exit__ = MagicMock(return_value=False)

        valor = db.obter_configuracao("nao_existe")

    assert valor is None


def test_salvar_configuracao_executa_upsert_com_on_conflict():
    """PR9 P1.2 — upsert via INSERT ... ON CONFLICT (chave) DO UPDATE."""
    from App import database as db

    mock_conn, mock_cur = _make_mock_conn()
    with (
        patch.object(db, "_get_connection") as mock_gc,
        patch.object(db, "_ensure_db_initialized"),
    ):
        mock_gc.return_value.__enter__ = lambda s: mock_conn
        mock_gc.return_value.__exit__ = MagicMock(return_value=False)

        db.salvar_configuracao("modelo_mae_contestacao", "Texto do template")

    sql, params = mock_cur.execute.call_args.args
    assert "INSERT INTO configuracoes" in sql
    assert "ON CONFLICT (chave) DO UPDATE" in sql
    assert "atualizado_em = NOW()" in sql
    assert params == ("modelo_mae_contestacao", "Texto do template")
    mock_conn.commit.assert_called_once()


def test_migration_executa_create_table_configuracoes(monkeypatch):
    """init_db() inclui CREATE TABLE IF NOT EXISTS configuracoes."""
    from App import database as db

    executed_sql: list[str] = []

    mock_cur = MagicMock()
    mock_cur.execute = lambda sql, *args, **kwargs: executed_sql.append(sql)
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    # Reset guard para forcar init_db rodar de novo
    monkeypatch.setattr(db, "_db_initialized", False)
    with patch.object(db, "_get_connection") as mock_gc:
        mock_gc.return_value.__enter__ = lambda s: mock_conn
        mock_gc.return_value.__exit__ = MagicMock(return_value=False)
        db.init_db()

    # Garante que CREATE TABLE configuracoes foi executado
    todas_sqls = "\n".join(executed_sql)
    assert "CREATE TABLE IF NOT EXISTS configuracoes" in todas_sqls
    assert "chave           TEXT PRIMARY KEY" in todas_sqls
    assert "valor           TEXT NOT NULL" in todas_sqls

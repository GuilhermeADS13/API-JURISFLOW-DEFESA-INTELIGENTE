"""PR8 P1.4 — testa que load_env_file nao sobrescreve env do sistema."""

from __future__ import annotations

import os

from main import load_env_file


def test_load_env_file_nao_sobrescreve_variavel_do_sistema(tmp_path, monkeypatch):
    """Se a variavel ja existe em os.environ, .env local nao deve sobrescrever."""
    # Simula variavel injetada pelo sistema (ex: Docker secret)
    monkeypatch.setenv("MEU_SECRET_DE_PROD", "valor_de_producao")

    # Cria .env local conflitante
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MEU_SECRET_DE_PROD=valor_de_desenvolvimento\n", encoding="utf-8"
    )

    # Aponta load_env_file para o tmp_path via monkeypatch do __file__
    import main as main_module

    monkeypatch.setattr(
        main_module,
        "__file__",
        str(tmp_path / "fake_main.py"),
    )

    load_env_file()

    # Valor original do sistema deve ser preservado
    assert os.environ["MEU_SECRET_DE_PROD"] == "valor_de_producao"


def test_load_env_file_define_variavel_ausente(tmp_path, monkeypatch):
    """Se a variavel nao existe em os.environ, .env local define normalmente."""
    monkeypatch.delenv("VAR_QUE_NAO_EXISTE", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text("VAR_QUE_NAO_EXISTE=do_env_local\n", encoding="utf-8")

    import main as main_module

    monkeypatch.setattr(
        main_module,
        "__file__",
        str(tmp_path / "fake_main.py"),
    )

    load_env_file()

    assert os.environ.get("VAR_QUE_NAO_EXISTE") == "do_env_local"


def test_load_env_file_sem_arquivo_nao_falha(tmp_path, monkeypatch):
    """Sem .env (producao tipica), load_env_file deve passar em silencio."""
    # tmp_path nao tem .env
    import main as main_module

    monkeypatch.setattr(
        main_module,
        "__file__",
        str(tmp_path / "fake_main.py"),
    )

    # Nao deve levantar
    load_env_file()

"""Poller do Telegram pra capturar respostas de CAPTCHA via reply (PR29).

Feature: humano responde o CAPTCHA DIRETO no Telegram (respondendo a mensagem
do bot), sem precisar abrir o link no navegador. Este poller consome
`getUpdates` da Bot API e correlaciona cada reply ao token pendente.

Correlacao:
    1. Preferencial: `message.reply_to_message.message_id` casa com o
       message_id que guardamos ao enviar a notificacao (mapa no orchestrator).
    2. Fallback: se ha exatamente 1 task pendente nao-respondida, qualquer
       texto enviado ao bot vira a resposta dela (conveniencia — usuario nem
       precisa dar reply, so mandar o texto).

Arquitetura:
    - Uma unica thread daemon. Long-polling (getUpdates timeout=25s).
    - So roda enquanto ha tasks pendentes. Apos IDLE_STOP_SEC sem pendentes,
      a thread encerra; nova task reinicia via `iniciar_se_preciso()`.
    - Offset (update_id) mantido in-memory. Idempotente: reprocessar update
      antigo e inofensivo (registrar_resposta retorna False se ja respondido).

Restricao do Telegram:
    - getUpdates conflita com webhook (nao usamos webhook — ok).
    - So 1 consumidor de getUpdates por vez (409 Conflict se 2 rodarem).
      Backend uvicorn single-process → 1 thread poller. Evitar rodar
      getUpdates manual concorrente com o poller ligado.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_LONG_POLL_SEC = 25
_HTTP_TIMEOUT_SEC = _LONG_POLL_SEC + 10
_IDLE_STOP_SEC = 60  # sem pendentes por 60s → thread encerra

_thread: threading.Thread | None = None
_thread_lock = threading.Lock()
_offset: int = 0


def iniciar_se_preciso() -> None:
    """Garante que a thread poller esta rodando. Idempotente + thread-safe."""
    global _thread
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(
            target=_loop,
            name="captcha-telegram-poller",
            daemon=True,
        )
        _thread.start()
        logger.info("Poller Telegram iniciado")


def _token_bot() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _get_updates(token: str) -> list[dict[str, Any]]:
    """Chama getUpdates com long-polling. Retorna lista de updates (pode vazia)."""
    global _offset
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"offset": _offset, "timeout": _LONG_POLL_SEC},
            timeout=_HTTP_TIMEOUT_SEC,
        )
        if not resp.ok:
            logger.warning("getUpdates HTTP %d: %s", resp.status_code, resp.text[:200])
            return []
        data = resp.json()
        return data.get("result", [])
    except requests.RequestException as err:
        logger.warning("getUpdates falhou: %s", err)
        return []


def _processar_update(update: dict[str, Any]) -> None:
    """Extrai reply/texto de 1 update e registra resposta se casar com token."""
    global _offset
    update_id = update.get("update_id")
    if isinstance(update_id, int):
        _offset = max(_offset, update_id + 1)

    msg = update.get("message") or update.get("edited_message") or {}
    texto = (msg.get("text") or "").strip()
    if not texto:
        return
    # Ignora comandos do bot (ex: /start)
    if texto.startswith("/"):
        return

    # Import tardio pra evitar ciclo
    from App.services import captcha_orchestrator as orch

    token = None
    reply_to = msg.get("reply_to_message") or {}
    reply_msg_id = reply_to.get("message_id")
    if isinstance(reply_msg_id, int):
        token = orch.token_por_telegram_msg(reply_msg_id)

    # Fallback: se nao deu reply mas ha exatamente 1 pendente, assume que e ela
    if token is None:
        pendentes = [p for p in orch.snapshot_pendentes() if not p["respondido"]]
        if len(pendentes) == 1:
            token = pendentes[0]["token"]

    if token:
        if orch.registrar_resposta(token, texto):
            logger.info("CAPTCHA %s resolvido via reply no Telegram", token)
        # se registrar_resposta False (ja respondido/expirado), ignora silencioso


def _loop() -> None:
    """Loop principal do poller. Encerra apos IDLE_STOP_SEC sem pendentes."""
    from App.services import captcha_orchestrator as orch

    token_bot = _token_bot()
    if not token_bot:
        logger.warning("Poller Telegram sem TELEGRAM_BOT_TOKEN — encerrando")
        return

    ultimo_pendente_ts = time.time()
    while True:
        if orch.tem_pendentes_nao_respondidos():
            ultimo_pendente_ts = time.time()
        elif time.time() - ultimo_pendente_ts > _IDLE_STOP_SEC:
            logger.info(
                "Poller Telegram idle %ds sem pendentes — encerrando", _IDLE_STOP_SEC
            )
            return

        updates = _get_updates(token_bot)
        for u in updates:
            _processar_update(u)


def _reset_para_testes() -> None:
    """Zera estado global (offset + thread). So pra testes."""
    global _thread, _offset
    with _thread_lock:
        _thread = None
        _offset = 0

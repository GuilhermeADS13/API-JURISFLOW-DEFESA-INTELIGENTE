"""Cascade CAPTCHA resolver (PR28) — combina 3 estrategias em ordem:

    1. CRNN local (visual apenas) — stub retorna None ate modelo H5 ser treinado
    2. Cookies session pre-autenticados (Turnstile) — delegado pro STJScraper
       existente (PR26). Aqui nao roda nada; documentamos que o caller ja
       tentou essa rota antes de chamar o orchestrator.
    3. Notificacao humana (email/Telegram) — cria pending task com token,
       dispara notify, retorna 'pending' pro caller poll ate humano responder.

Design:
    - Estado das tarefas pending eh in-memory (dict global). Sobrevive so ate
      restart do backend. Tolerancia aceita porque timeout do fluxo eh 10min.
    - Threading.Lock protege race entre solve → status → answer.
    - TTL configuravel (default 10min): task expirada eh limpada no proximo
      acesso, retornando 'expirado' pro caller.

Uso do caller (scraper):
    from App.services.captcha_orchestrator import resolver, aguardar_resposta

    resultado = resolver(image_bytes, tipo='visual', tribunal='STJ')
    if resultado.status == 'ok':
        usar(resultado.texto)
    elif resultado.status == 'pending':
        # Poll ate 10min. Alternativa: caller pode fazer polling manualmente
        # via GET /api/captcha/status/{token} se for HTTP-based (n8n).
        final = aguardar_resposta(resultado.token, timeout_sec=600)
        if final.status == 'ok':
            usar(final.texto)
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

from App.services.captcha_notifier import notificar_humano

logger = logging.getLogger(__name__)


TipoCaptcha = Literal["visual", "turnstile", "recaptcha_v2", "hcaptcha", "desconhecido"]
Status = Literal["ok", "pending", "expirado", "falha", "sem_canal"]

_TTL_SEC_DEFAULT = 600  # 10 min


@dataclass
class ResultadoCaptcha:
    """Payload padronizado retornado por `resolver()` e `aguardar_resposta()`."""

    status: Status
    texto: Optional[str] = None
    token: Optional[str] = None
    mensagem: Optional[str] = None


@dataclass
class _TarefaPending:
    """Estado de 1 CAPTCHA aguardando humano."""

    token: str
    tipo: TipoCaptcha
    tribunal: Optional[str]
    criado_em: float
    ttl_sec: int
    respondido_em: Optional[float] = None
    resposta: Optional[str] = None
    # PR29: chave de deduplicacao (ex: tribunal + hash da query). Se scraper
    # retentar o mesmo CAPTCHA, reusa a task existente em vez de flood.
    dedup_key: Optional[str] = None
    # PR29: message_id do Telegram pra correlacionar reply do humano.
    telegram_message_id: Optional[int] = None
    # Event pra `aguardar_resposta()` acordar assim que /answer chegar.
    evento: threading.Event = field(default_factory=threading.Event)


# ─────────────────────────────────────────────────────────────────────────────
# Estado global (in-memory) — thread-safe via Lock
# ─────────────────────────────────────────────────────────────────────────────

_pendentes: dict[str, _TarefaPending] = {}
# PR29: mapa telegram_message_id -> token (feature: responder via reply).
_telegram_msg_para_token: dict[int, str] = {}
_lock = threading.Lock()


def _gerar_token() -> str:
    """Token URL-safe curto (16 chars). Colisao praticamente impossivel pra <1M pendentes."""
    return secrets.token_urlsafe(12)


def _limpar_expirados_locked() -> None:
    """Remove tarefas com TTL vencido. Deve ser chamado com _lock adquirido."""
    agora = time.time()
    expirados: list[tuple[str, int, Optional[int]]] = []
    for token, tarefa in _pendentes.items():
        if agora - tarefa.criado_em > tarefa.ttl_sec and tarefa.respondido_em is None:
            expirados.append((token, tarefa.ttl_sec, tarefa.telegram_message_id))
    for token, ttl, tg_msg in expirados:
        _pendentes.pop(token, None)
        if tg_msg is not None:
            _telegram_msg_para_token.pop(tg_msg, None)
        logger.info("Task CAPTCHA %s expirou apos %ds sem resposta", token, ttl)


# ─────────────────────────────────────────────────────────────────────────────
# API publica
# ─────────────────────────────────────────────────────────────────────────────


def _tentar_crnn(image_bytes: bytes) -> Optional[str]:
    """Tenta resolver CAPTCHA visual via modelo CRNN local.

    STUB (PR28): retorna None ate `Backend/App/services/captcha_solver.py`
    ter o modelo H5 carregado. PR31 vai substituir por implementacao real.
    Nao lanca excecao — retorna None e chamador cai pra proximo estagio.
    """
    try:
        # Import tardio: modulo pode nao existir ainda no PR28 (a criar
        # quando dev treinar modelo). Fallback silencioso e ok.
        from App.services import captcha_solver  # noqa: F401
    except ImportError:
        return None
    try:
        return captcha_solver.resolver_visual(image_bytes)  # type: ignore[attr-defined]
    except AttributeError:
        # captcha_solver existe mas nao tem `resolver_visual` ainda
        return None
    except Exception as err:  # noqa: BLE001 — fallback amplo
        logger.warning(
            "CRNN captcha_solver falhou: %s — caindo pra proximo estagio", err
        )
        return None


def _buscar_pending_por_dedup_locked(dedup_key: str) -> Optional[_TarefaPending]:
    """Retorna task nao-respondida + nao-expirada com mesma dedup_key. _lock adquirido."""
    agora = time.time()
    for tarefa in _pendentes.values():
        if (
            tarefa.dedup_key == dedup_key
            and tarefa.respondido_em is None
            and agora - tarefa.criado_em <= tarefa.ttl_sec
        ):
            return tarefa
    return None


def resolver(
    image_bytes: Optional[bytes],
    *,
    tipo: TipoCaptcha,
    tribunal: Optional[str] = None,
    ttl_sec: int = _TTL_SEC_DEFAULT,
    dedup_key: Optional[str] = None,
) -> ResultadoCaptcha:
    """Executa cascade: CRNN → notify humano.

    Cookies session NAO passa por aqui — eh feito antes, no scraper (PR26).
    Este orchestrator so entra em cena quando cookies session ja falhou.

    Args:
        image_bytes: PNG bytes do CAPTCHA. Pode ser None (Turnstile/reCAPTCHA v3).
        tipo: classificacao da protecao.
        tribunal: sigla pro contexto na notificacao.
        ttl_sec: quanto tempo esperar humano responder antes de expirar.
        dedup_key: PR29 anti-flood. Se o scraper retentar o mesmo CAPTCHA
            (ex: mesma query no mesmo tribunal), passe a mesma chave. Se ja
            existir task pending com essa chave, reusa em vez de notificar
            de novo (evita spam de pings no Telegram).

    Retorna ResultadoCaptcha com status:
        - 'ok': CRNN resolveu, resposta em `.texto`
        - 'pending': humano foi notificado, use `.token` pra pollar
        - 'sem_canal': nem CRNN nem notify funcionaram; scraper deve abortar
    """
    # Estagio 1: CRNN (so pra tipo visual)
    if tipo == "visual" and image_bytes:
        texto = _tentar_crnn(image_bytes)
        if texto:
            logger.info("CAPTCHA visual resolvido via CRNN (tribunal=%s)", tribunal)
            return ResultadoCaptcha(status="ok", texto=texto)

    # Estagio 2: (cookies session NAO passa por aqui — feito antes no scraper)

    # PR29 dedup: se ja tem task pending com mesma dedup_key, reusa (nao floodar)
    if dedup_key:
        with _lock:
            _limpar_expirados_locked()
            existente = _buscar_pending_por_dedup_locked(dedup_key)
            if existente is not None:
                logger.info(
                    "CAPTCHA dedup: reusando task %s (dedup_key=%s) — sem novo ping",
                    existente.token,
                    dedup_key,
                )
                return ResultadoCaptcha(
                    status="pending",
                    token=existente.token,
                    mensagem="Reusando notificacao pendente (dedup).",
                )

    # Estagio 3: notify humano
    token = _gerar_token()
    tarefa = _TarefaPending(
        token=token,
        tipo=tipo,
        tribunal=tribunal,
        criado_em=time.time(),
        ttl_sec=ttl_sec,
        dedup_key=dedup_key,
    )
    with _lock:
        _pendentes[token] = tarefa

    resultado_notif = notificar_humano(
        token_pending=token,
        tipo_captcha=tipo,
        tribunal=tribunal,
        image_bytes=image_bytes,
    )
    if not resultado_notif.enviado:
        with _lock:
            _pendentes.pop(token, None)
        return ResultadoCaptcha(
            status="sem_canal",
            mensagem="Nenhum canal de notificacao configurado (TELEGRAM_* ou SUPPORT_SMTP_*).",
        )

    # Se foi via Telegram, guarda message_id pra correlacionar reply + liga poller
    if resultado_notif.canal == "telegram" and resultado_notif.telegram_message_id:
        with _lock:
            tarefa.telegram_message_id = resultado_notif.telegram_message_id
            _telegram_msg_para_token[resultado_notif.telegram_message_id] = token
        _iniciar_poller_telegram()

    return ResultadoCaptcha(
        status="pending",
        token=token,
        mensagem=f"Humano notificado (tipo={tipo}, tribunal={tribunal or '?'}).",
    )


def _iniciar_poller_telegram() -> None:
    """Liga o poller do Telegram (import tardio pra evitar ciclo).

    Idempotente: poller so inicia uma thread daemon se ainda nao estiver
    rodando. Chamado sempre que uma task Telegram e criada.
    """
    try:
        from App.services import captcha_telegram_poller

        captcha_telegram_poller.iniciar_se_preciso()
    except Exception as err:  # noqa: BLE001 — poller e best-effort
        logger.warning("Nao consegui iniciar poller Telegram: %s", err)


def token_por_telegram_msg(message_id: int) -> Optional[str]:
    """Retorna o token da task cujo Telegram msg foi respondido (reply). PR29."""
    with _lock:
        return _telegram_msg_para_token.get(message_id)


def tem_pendentes_nao_respondidos() -> bool:
    """True se ha ao menos 1 task aguardando resposta. Poller usa pra decidir
    se continua rodando ou dorme."""
    with _lock:
        _limpar_expirados_locked()
        return any(p.respondido_em is None for p in _pendentes.values())


def registrar_resposta(token: str, texto: str) -> bool:
    """Chamado pelo endpoint /answer/{token} quando humano responde.

    Retorna True se o token existia e foi atualizado; False se nao existia
    (expirou ou nunca foi criado).
    """
    with _lock:
        _limpar_expirados_locked()
        tarefa = _pendentes.get(token)
        if tarefa is None or tarefa.respondido_em is not None:
            return False
        tarefa.resposta = texto.strip()
        tarefa.respondido_em = time.time()
        tarefa.evento.set()
        # Limpa mapa Telegram (msg respondida nao precisa mais de correlacao)
        if tarefa.telegram_message_id is not None:
            _telegram_msg_para_token.pop(tarefa.telegram_message_id, None)
    logger.info("CAPTCHA %s respondido pelo humano", token)
    return True


def consultar_status(token: str) -> ResultadoCaptcha:
    """Chamado pelo endpoint /status/{token} pra caller pollar (n8n)."""
    with _lock:
        _limpar_expirados_locked()
        tarefa = _pendentes.get(token)
        if tarefa is None:
            return ResultadoCaptcha(
                status="expirado",
                token=token,
                mensagem="Token nao encontrado (expirou ou nunca existiu).",
            )
        if tarefa.respondido_em is not None:
            return ResultadoCaptcha(
                status="ok",
                token=token,
                texto=tarefa.resposta,
            )
    return ResultadoCaptcha(status="pending", token=token)


def aguardar_resposta(
    token: str, *, timeout_sec: int = _TTL_SEC_DEFAULT
) -> ResultadoCaptcha:
    """Bloqueia ate humano responder ou timeout. Usado pelo scraper Python
    interno (nao pelo n8n — n8n usa /status polling).
    """
    with _lock:
        tarefa = _pendentes.get(token)
        if tarefa is None:
            return ResultadoCaptcha(status="expirado", token=token)
        evento = tarefa.evento
    respondeu = evento.wait(timeout=timeout_sec)
    if not respondeu:
        with _lock:
            _pendentes.pop(token, None)
        return ResultadoCaptcha(
            status="expirado",
            token=token,
            mensagem=f"Timeout apos {timeout_sec}s sem resposta humana.",
        )
    with _lock:
        tarefa = _pendentes.get(token)
        if tarefa and tarefa.resposta:
            return ResultadoCaptcha(status="ok", token=token, texto=tarefa.resposta)
    return ResultadoCaptcha(status="expirado", token=token)


def snapshot_pendentes() -> list[dict]:
    """Introspeccao pro admin dashboard/CLI. Retorna copia serializavel."""
    with _lock:
        _limpar_expirados_locked()
        return [
            {
                "token": p.token,
                "tipo": p.tipo,
                "tribunal": p.tribunal,
                "idade_seg": round(time.time() - p.criado_em, 1),
                "respondido": p.respondido_em is not None,
            }
            for p in _pendentes.values()
        ]

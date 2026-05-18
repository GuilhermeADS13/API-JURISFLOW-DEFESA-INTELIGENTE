"""Servico de envio de reclamacao para o e-mail de suporte."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any

DEFAULT_SMTP_PORT = 587
DEFAULT_SMTP_TIMEOUT_SECONDS = 15
DEFAULT_SUBJECT_PREFIX = "[JurisFlow][Suporte]"


class SupportEmailConfigError(Exception):
    """Erro de configuracao SMTP para envio de suporte."""


class SupportEmailServiceError(Exception):
    """Erro de envio SMTP no canal de suporte."""


def _parse_bool(value: str | None, default: bool) -> bool:
    """Converte string de ambiente para booleano com fallback padrao."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_email_config() -> dict[str, Any]:
    """Le e valida configuracoes SMTP usadas no envio de suporte."""
    host = os.getenv("SUPPORT_SMTP_HOST", "").strip()
    user = os.getenv("SUPPORT_SMTP_USER", "").strip()
    password = os.getenv("SUPPORT_SMTP_PASSWORD", "").strip()
    to_email = os.getenv("SUPPORT_EMAIL_TO", "").strip()
    from_email = os.getenv("SUPPORT_EMAIL_FROM", "").strip() or user
    use_tls = _parse_bool(os.getenv("SUPPORT_SMTP_STARTTLS"), True)
    use_ssl = _parse_bool(os.getenv("SUPPORT_SMTP_SSL"), False)

    try:
        port = int(os.getenv("SUPPORT_SMTP_PORT", str(DEFAULT_SMTP_PORT)).strip())
    except ValueError as error:
        raise SupportEmailConfigError(
            "SUPPORT_SMTP_PORT deve ser um numero inteiro valido."
        ) from error

    try:
        timeout = int(
            os.getenv(
                "SUPPORT_SMTP_TIMEOUT_SECONDS", str(DEFAULT_SMTP_TIMEOUT_SECONDS)
            ).strip()
        )
    except ValueError as error:
        raise SupportEmailConfigError(
            "SUPPORT_SMTP_TIMEOUT_SECONDS deve ser um numero inteiro valido."
        ) from error

    if not host:
        raise SupportEmailConfigError("SUPPORT_SMTP_HOST nao configurado.")
    if not to_email:
        raise SupportEmailConfigError("SUPPORT_EMAIL_TO nao configurado.")
    if not from_email:
        raise SupportEmailConfigError(
            "SUPPORT_EMAIL_FROM ou SUPPORT_SMTP_USER precisa estar configurado."
        )

    if user and not password:
        raise SupportEmailConfigError(
            "SUPPORT_SMTP_PASSWORD nao configurado para o usuario SMTP."
        )

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "to_email": to_email,
        "from_email": from_email,
        "use_tls": use_tls,
        "use_ssl": use_ssl,
        "timeout": timeout,
    }


def _build_email(
    payload: dict[str, Any], from_email: str, to_email: str
) -> EmailMessage:
    """Monta assunto/corpo do e-mail com dados da reclamacao e protocolo."""
    subject_prefix = os.getenv(
        "SUPPORT_EMAIL_SUBJECT_PREFIX", DEFAULT_SUBJECT_PREFIX
    ).strip()
    prefix = subject_prefix or DEFAULT_SUBJECT_PREFIX
    subject = f"{prefix} {payload['assunto']}".strip()

    body = "\n".join(
        [
            "Nova reclamacao recebida pela plataforma JurisFlow AI.",
            "",
            f"Protocolo: {payload['protocolo']}",
            f"Nome: {payload['nome']}",
            f"E-mail: {payload['email']}",
            f"Categoria: {payload['categoria']}",
            f"Numero do processo: {payload.get('numero_processo') or 'Nao informado'}",
            "",
            "Mensagem:",
            payload["mensagem"],
        ]
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_email
    message["To"] = to_email
    message["Reply-To"] = payload["email"]
    message.set_content(body, charset="utf-8")
    return message


def enviar_reclamacao_por_email(payload: dict[str, Any]) -> None:
    """Envia uma reclamacao de suporte para o e-mail configurado."""
    config = _resolve_email_config()
    message = _build_email(
        payload, from_email=config["from_email"], to_email=config["to_email"]
    )

    try:
        if config["use_ssl"]:
            with smtplib.SMTP_SSL(
                config["host"],
                config["port"],
                timeout=config["timeout"],
            ) as smtp:
                if config["user"]:
                    smtp.login(config["user"], config["password"])
                smtp.send_message(message)
            return

        with smtplib.SMTP(
            config["host"],
            config["port"],
            timeout=config["timeout"],
        ) as smtp:
            smtp.ehlo()
            if config["use_tls"]:
                smtp.starttls()
                smtp.ehlo()
            if config["user"]:
                smtp.login(config["user"], config["password"])
            smtp.send_message(message)
    except (TimeoutError, OSError, smtplib.SMTPException) as error:
        raise SupportEmailServiceError(
            "Falha ao enviar reclamacao por e-mail. Tente novamente em instantes."
        ) from error

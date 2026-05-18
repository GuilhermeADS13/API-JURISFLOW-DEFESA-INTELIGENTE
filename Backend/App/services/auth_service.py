"""Funcoes utilitarias para hash e verificacao de senha."""

import base64
import hashlib
import hmac
import os

# Parametros do PBKDF2 para proteger senhas em repouso no banco.
# 600k iteracoes seguem a recomendacao OWASP 2023 para PBKDF2-SHA256.
PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 600_000
SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Gera hash PBKDF2 com salt aleatorio e serializa em string."""
    salt = os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    encoded_salt = base64.b64encode(salt).decode("utf-8")
    encoded_digest = base64.b64encode(digest).decode("utf-8")
    return (
        f"pbkdf2_{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${encoded_salt}${encoded_digest}"
    )


def verify_password(password: str, stored_hash: str) -> bool:
    """Compara senha informada com hash persistido usando tempo constante."""
    try:
        algorithm, iterations_str, encoded_salt, encoded_digest = stored_hash.split(
            "$", 3
        )
        if algorithm != f"pbkdf2_{PBKDF2_ALGORITHM}":
            return False

        iterations = int(iterations_str)
        salt = base64.b64decode(encoded_salt.encode("utf-8"))
        expected_digest = base64.b64decode(encoded_digest.encode("utf-8"))
    except (ValueError, TypeError):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def needs_rehash(stored_hash: str) -> bool:
    """Indica se o hash usa parametros antigos e precisa ser regerado.

    Permite migracao transparente para a politica atual: ao validar a senha no
    login, se este metodo retornar True, regera o hash com PBKDF2_ITERATIONS
    novo e atualiza o registro do usuario sem pedir nova senha.
    """
    try:
        algorithm, iterations_str, _, _ = stored_hash.split("$", 3)
    except ValueError:
        return True

    if algorithm != f"pbkdf2_{PBKDF2_ALGORITHM}":
        return True

    try:
        return int(iterations_str) < PBKDF2_ITERATIONS
    except ValueError:
        return True

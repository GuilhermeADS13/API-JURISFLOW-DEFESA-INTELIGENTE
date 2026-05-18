"""Configuracao centralizada do rate limiter (slowapi)."""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

# Lista de proxies confiaveis (CIDR/host) cujo X-Forwarded-For deve ser respeitado.
# Em producao atras de nginx/cloudflare, configurar via env. Se vazia, ignoramos
# o header para nao permitir spoofing trivial em ambientes expostos diretamente.
TRUST_FORWARDED_HEADER = (
    os.getenv("RATE_LIMIT_TRUST_FORWARDED", "false").strip().lower() == "true"
)


def _client_ip(request: Request) -> str:
    """Resolve IP real respeitando proxy reverso quando configurado.

    Sem TRUST_FORWARDED_HEADER, todos os usuarios atras de proxy terao a mesma chave
    (request.client.host = IP do proxy) e o limiter quebraria globalmente. Por isso,
    em deployments com proxy, basta exportar RATE_LIMIT_TRUST_FORWARDED=true.
    """
    if TRUST_FORWARDED_HEADER:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            # Primeiro IP da cadeia = cliente original (RFC 7239 / convenção XFF).
            first = forwarded.split(",")[0].strip()
            if first:
                return first
    return get_remote_address(request)


limiter = Limiter(
    key_func=_client_ip,
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
)

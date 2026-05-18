"""Fixtures compartilhadas — reset do rate limiter entre testes."""

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reseta o storage do slowapi antes de cada teste.

    Sem isso, o estado do limiter (em memoria) persiste entre testes
    e faz com que testes que exercitam varios POSTs se contaminem mutuamente.
    Os testes que *intencionalmente* validam o 429 (test_rate_limit.py,
    test_security_audit.py) continuam funcionando porque cada um comeca
    com o storage limpo.
    """
    from App.limiter import limiter

    limiter.reset()
    yield
    limiter.reset()

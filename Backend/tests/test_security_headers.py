"""Quest 2 — Verifica presenca dos security headers em todas as responses."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

ENDPOINTS = [
    ("GET", "/"),
    ("GET", "/health"),
]

REQUIRED_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin",
}


def test_security_headers_presentes_no_health():
    r = client.get("/health")
    for header, value in REQUIRED_HEADERS.items():
        assert header in r.headers, f"Header ausente: {header}"
        assert r.headers[header] == value, (
            f"Header {header} incorreto: {r.headers[header]!r} != {value!r}"
        )


def test_security_headers_presentes_no_root():
    r = client.get("/")
    for header, value in REQUIRED_HEADERS.items():
        assert header in r.headers, f"Header ausente: {header}"
        assert r.headers[header] == value


def test_x_content_type_options_previne_sniffing():
    """nosniff impede que browser tente adivinhar MIME de responses."""
    r = client.get("/health")
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_x_frame_options_previne_clickjacking():
    """DENY impede que a pagina seja embarcada em iframe."""
    r = client.get("/health")
    assert r.headers.get("x-frame-options") == "DENY"


def test_referrer_policy_limita_vazamento():
    """strict-origin evita vazamento de URL completa em requests cross-origin."""
    r = client.get("/health")
    assert r.headers.get("referrer-policy") == "strict-origin"


def test_content_security_policy_restritiva():
    """PR8 P2.6 — CSP nega scripts, objects e iframes."""
    r = client.get("/health")
    csp = r.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "script-src 'none'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_permissions_policy_bloqueia_apis_sensiveis():
    """PR8 P2.6 — Permissions-Policy bloqueia geolocation/camera/microphone."""
    r = client.get("/health")
    pp = r.headers.get("permissions-policy", "")
    assert "geolocation=()" in pp
    assert "camera=()" in pp
    assert "microphone=()" in pp

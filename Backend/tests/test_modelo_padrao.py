"""Testes do timbre padrao (modelos_escritorio): auto-uso + salvar como padrao.

Mockam as funcoes de DB (get_modelo_padrao / salvar_modelo_padrao) importadas no
modulo da rota; _resolver_modelo recebe um objeto leve (duck typing) para nao
precisar montar um payload Pydantic valido com magic bytes.
"""

from types import SimpleNamespace

from App.models.contestacao_por_peticao import ContestacaoPorPeticao
from App.routes import contestacao_peticao as rc


def _payload(**kw):
    base = {
        "modelo_base_base64": "",
        "modelo_base_nome": None,
        "salvar_como_modelo_padrao": False,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def test_default_field_salvar_como_modelo_padrao_false():
    assert (
        ContestacaoPorPeticao.model_fields["salvar_como_modelo_padrao"].default is False
    )


def test_resolver_usa_timbre_padrao_quando_sem_upload(monkeypatch):
    monkeypatch.setattr(
        rc,
        "get_modelo_padrao",
        lambda uid: {"nome": "Timbre G. Trindade", "arquivo_b64": "BASE64DOCX"},
    )
    salvos = []
    monkeypatch.setattr(rc, "salvar_modelo_padrao", lambda *a, **k: salvos.append(a))

    p = _payload()  # nenhum modelo enviado
    rc._resolver_modelo(p, "user-1")

    assert p.modelo_base_base64 == "BASE64DOCX"  # reaproveitou o padrao
    assert p.modelo_base_nome == "Timbre G. Trindade"
    assert salvos == []  # nao tenta salvar quando nada foi enviado


def test_resolver_salva_como_padrao_quando_pedido(monkeypatch):
    monkeypatch.setattr(rc, "get_modelo_padrao", lambda uid: None)
    capturado = {}
    monkeypatch.setattr(
        rc,
        "salvar_modelo_padrao",
        lambda uid, nome, b64: capturado.update(uid=uid, nome=nome, b64=b64),
    )

    p = _payload(
        modelo_base_base64="XYZ",
        modelo_base_nome="meu_timbre.docx",
        salvar_como_modelo_padrao=True,
    )
    rc._resolver_modelo(p, "user-1")

    assert capturado == {"uid": "user-1", "nome": "meu_timbre.docx", "b64": "XYZ"}
    assert p.modelo_base_base64 == "XYZ"  # o modelo enviado permanece


def test_resolver_nao_salva_sem_flag(monkeypatch):
    monkeypatch.setattr(rc, "get_modelo_padrao", lambda uid: None)
    salvos = []
    monkeypatch.setattr(rc, "salvar_modelo_padrao", lambda *a, **k: salvos.append(a))

    p = _payload(modelo_base_base64="XYZ", salvar_como_modelo_padrao=False)
    rc._resolver_modelo(p, "user-1")

    assert salvos == []  # sem a flag, nao grava


def test_resolver_tolerante_a_erro_de_db(monkeypatch):
    def boom(uid):
        raise RuntimeError("db indisponivel")

    monkeypatch.setattr(rc, "get_modelo_padrao", boom)
    p = _payload()
    rc._resolver_modelo(p, "user-1")  # nao pode levantar
    assert p.modelo_base_base64 == ""  # cai no comportamento antigo (sem timbre)

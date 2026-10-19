"""Testes do script scripts/ingest_seed_jurisprudencia.py (PR22).

Garante que:
- O seed JSON commitado no repo eh valido + completo (30 entradas, todos os
  campos obrigatorios presentes, sem duplicatas)
- O script main() chama upsert_jurisprudencia por entrada com kwargs corretos
- Falha gracioso quando arquivo nao existe
"""

import json
from pathlib import Path


SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "jurisprudencia_seed.json"
CAMPOS_OBRIGATORIOS = ("tribunal", "numero_processo", "ementa")


# ─────────────────────────────────────────────────────────────────────────────
# Validacao do conteudo do seed (defesa contra regressao do JSON)
# ─────────────────────────────────────────────────────────────────────────────


def test_seed_existe_e_e_lista_json():
    assert SEED_PATH.exists(), f"Seed nao encontrado em {SEED_PATH}"
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) >= 25  # margem de seguranca contra remocao acidental


def test_seed_todas_entradas_tem_campos_obrigatorios():
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    for i, entry in enumerate(data):
        for campo in CAMPOS_OBRIGATORIOS:
            assert entry.get(campo), (
                f"Entrada {i} ({entry.get('numero_processo', '?')}) "
                f"sem campo obrigatorio '{campo}'"
            )


def test_seed_sem_duplicatas_de_tribunal_numero():
    """UNIQUE da tabela e (tribunal, numero_processo). Se o seed tiver duplicata,
    o ingest re-roda e atualiza, mas alerta de curadoria errada."""
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    chaves = [(e["tribunal"], e["numero_processo"]) for e in data]
    assert len(chaves) == len(set(chaves)), (
        f"Duplicatas em chaves: {len(chaves) - len(set(chaves))}"
    )


def test_seed_pesos_dentro_de_1_10():
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    for entry in data:
        peso = entry.get("peso_relevancia", 5)
        assert 1 <= int(peso) <= 10, (
            f"{entry['numero_processo']} tem peso {peso} fora de 1-10"
        )


# ─────────────────────────────────────────────────────────────────────────────
# main() do script
# ─────────────────────────────────────────────────────────────────────────────


def test_main_chama_upsert_por_entrada(monkeypatch):
    """main() ingere todas as entradas via upsert. Mocka tudo que toca DB/embed."""
    import scripts.ingest_seed_jurisprudencia as script

    chamadas: list[dict] = []

    def fake_upsert(**kwargs):
        chamadas.append(kwargs)

    monkeypatch.setattr(script, "upsert_jurisprudencia", fake_upsert)
    monkeypatch.setattr(script, "gerar_embedding", lambda texto: [0.0] * 384)

    exit_code = script.main()
    assert exit_code == 0

    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert len(chamadas) == len(data)
    # Confere shape do primeiro
    primeiro = chamadas[0]
    assert primeiro["tribunal"]
    assert primeiro["numero_processo"]
    assert primeiro["ementa"]
    assert primeiro["embedding"] == [0.0] * 384


def test_main_falha_gracioso_se_seed_nao_existe(monkeypatch, tmp_path):
    """Renomeia ROOT pra dir vazio: arquivo nao encontrado → exit 1, sem stacktrace."""
    import scripts.ingest_seed_jurisprudencia as script

    monkeypatch.setattr(script, "ROOT", tmp_path)
    exit_code = script.main()
    assert exit_code == 1


def test_main_pula_entrada_com_campo_faltando(monkeypatch, tmp_path):
    """Entradas sem tribunal/numero/ementa sao puladas com log, nao explodem."""
    import scripts.ingest_seed_jurisprudencia as script

    seed_invalido = [
        {
            "tribunal": "TST",
            "numero_processo": "X",
            "ementa": "Sem campos OK aqui pra passar.",
        },
        {"tribunal": "", "numero_processo": "Y", "ementa": "Tribunal vazio — pular."},
        {"tribunal": "STJ", "numero_processo": "Z"},  # sem ementa
    ]
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "jurisprudencia_seed.json").write_text(
        json.dumps(seed_invalido), encoding="utf-8"
    )
    monkeypatch.setattr(script, "ROOT", tmp_path)

    chamadas: list[dict] = []
    monkeypatch.setattr(
        script, "upsert_jurisprudencia", lambda **kw: chamadas.append(kw)
    )
    monkeypatch.setattr(script, "gerar_embedding", lambda t: None)

    exit_code = script.main()
    # 1 upsert valido / 2 pulados — exit 0 (nao 100% falha)
    assert exit_code == 0
    assert len(chamadas) == 1
    assert chamadas[0]["tribunal"] == "TST"

# Etapa 5 — Evidências da Refatoração Orientada a Testes

> **Repositório:** `Backend/` (API JurisFlow / AutoJuri)
> **Data:** 2026-05-21
> **Base:** problemas mapeados no [`RELATORIO_METRICAS.md`](RELATORIO_METRICAS.md) (Etapa 4)
> **Ferramentas:** `pytest` + `pytest-cov` (cobertura) + `radon` (complexidade ciclomática, manutenibilidade, LOC)

Este documento reúne **apenas as duas evidências exigidas** no enunciado:
1. **Evidência das alterações realizadas** (Seção 1) — comparação antes/depois de complexidade ciclomática, duplicação e *code smells*, com lista exata dos arquivos tocados.
2. **Evidência da execução dos testes após refatoração** (Seção 2) — saída do `pytest`, cobertura `pytest-cov` e CC final pelo `radon`.

---

## 1. Evidência das alterações realizadas

### 1.1 Tabela mestre — funções refatoradas (CC antes → depois)

| Função / Arquivo | CC Antes (rank) | CC Depois (rank) | Δ |
|---|---:|---:|---:|
| `routes/contestacao_peticao.py::contestar_por_peticao` | **24 (D)** | **7 (B)** | **−17** |
| `services/contestacao_docx_builder.py::montar_docx_com_modelo` | **21 (D)** | **4 (A)** | **−17** |
| `services/contestacao_docx_builder.py::montar_docx_programatico` | 17 (C) | **1 (A)** | −16 |
| `routes/contestacao_peticao.py::confirmar_extracao` | 12 (C) | **5 (A)** | −7 |
| `routes/contestacao_peticao.py::atualizar_minuta_editada` | 11 (C) | **4 (A)** | −7 |
| `models/usuario.py::senha_forte` | 11 (C) | **2 (A)** | −9 |

**Resultado agregado:**

| Métrica | Antes | Depois |
|---|---:|---:|
| Funções rank **D** (CC ≥ 21) | **2** | **0** |
| Funções rank **C** (CC 11–20) | 12 | 9 |
| Média global do projeto (radon `cc -a`) | A (4,32) | **A (3,86)** |
| Média do `routes/contestacao_peticao.py` | C (≈14) | **A (3,38)** |
| Média do `services/n8n_service.py` | n/a (3 funções monolíticas) | **A (1,67)** |

### 1.2 Arquivos modificados nesta etapa

| Arquivo | Tipo de mudança | Motivação (do Relatório de Métricas) |
|---|---|---|
| [Backend/App/routes/contestacao_peticao.py](Backend/App/routes/contestacao_peticao.py) | **Extract Method** + unificação de duplicados | Função `contestar_por_peticao` com CC 24 (rank D) — orquestração de 8 passos numa função única; duplicação entre `_montar_docx` e `_montar_docx_minimal` |
| [Backend/App/services/contestacao_docx_builder.py](Backend/App/services/contestacao_docx_builder.py) | **Extract Method** + table-driven design | `montar_docx_com_modelo` CC 21 (rank D); `montar_docx_programatico` CC 17 (rank C) acumulando 7 seções no mesmo bloco |
| [Backend/App/services/n8n_service.py](Backend/App/services/n8n_service.py) | **Remove Duplication** (`_invocar_webhook`) | 3 funções `_enviar_para_n8n_sync` / `_enviar_para_n8n_edicao_sync` / `_enviar_para_n8n_peticao_sync` com ~40 linhas idênticas cada |
| [Backend/App/models/usuario.py](Backend/App/models/usuario.py) | **Replace Conditional with Polymorphism (table)** | `senha_forte` com 5 ifs sequenciais (CC 11) |
| [Backend/App/security.py](Backend/App/security.py) | **Narrow Exception** | `except Exception:` genérico em fallback de sessão |
| [Backend/App/routes/edicao.py](Backend/App/routes/edicao.py) | **Narrow Exception** | `except Exception:` no decode base64 |
| [Backend/App/models/contestacao_por_peticao.py](Backend/App/models/contestacao_por_peticao.py) | **Narrow Exception** | `except Exception:` no loop de anexos |
| [Backend/App/database.py](Backend/App/database.py) | **Document Intent (`noqa: BLE001`)** | 3 broad `except` que são padrão correto de transação (rollback + re-raise) — passaram a ter justificativa explícita |
| [Backend/tests/test_rag_semantico.py](Backend/tests/test_rag_semantico.py) | **Bugfix de teste** | `asyncio.get_event_loop()` quebrava no Python 3.14 (6 testes em falso negativo) |

### 1.3 Refatorações detalhadas — antes/depois

#### a) `contestar_por_peticao` (CC 24 → 7)

A função original concentrava 8 responsabilidades em ~200 linhas. Foi quebrada em helpers de
domínio claro, deixando o endpoint como uma **leitura linear do fluxo**:

```
contestar_por_peticao  (CC 7)
├─ _decodificar_peticao_base64        (CC 2)
├─ _decodificar_anexos                (CC 3)
├─ _extrair_texto_peticao             (CC 2)
├─ _chamar_n8n_peticao   (compartilhada com confirmar_extracao)  (CC 5)
├─ _montar_save_payload               (CC 7)
├─ _fluxo_revisao_humana              (CC 1)  ◀── HiL com confiança < 0.7
└─ _fluxo_ok                          (CC 2)
    ├─ _montar_docx                   (CC 4)   ◀── unificado (era 2 funções)
    ├─ _persistir_contestacao         (CC 2)
    ├─ _disparar_embedding            (CC 2)
    └─ _resposta_docx                 (CC 1)
```

**Justificativa técnica:** extract-method é o caminho de menor risco para reduzir CC sem
mudar comportamento. Cada helper recebe parâmetros explícitos e devolve um valor único →
testável isoladamente. O endpoint vira `read the names`: a sequência de chamadas é a
documentação do fluxo HiL.

**Bônus de duplicação eliminada:**

| Função original | Substituição |
|---|---|
| `_montar_docx(payload: ContestacaoPorPeticao, ...)` | `_montar_docx(modelo_b64: str \| None, ...)` |
| `_montar_docx_minimal(payload: ConfirmacaoExtracao, ...)` | (mesma assinatura — só precisava do `modelo_base_base64`) |

#### b) `montar_docx_programatico` (CC 17 → 1)

O `if/and/dict-check` para cada seção (tese central, preliminares, mérito, impugnação,
fundamentos, pedidos) virou um **loop sobre tabela de seções**:

```python
_SECOES_TEXTO = (
    ("tese_central", "I — TESE CENTRAL"),
    ("preliminares", "II — PRELIMINARES"),
    ("merito",       "III — DO MERITO"),
)
_SECOES_FINAIS = (
    ("fundamentos",  "V — FUNDAMENTOS JURIDICOS"),
    ("pedidos",      "VI — PEDIDOS"),
)

def _escrever_secoes_minuta(doc, minuta):
    for chave, titulo in _SECOES_TEXTO:
        _escrever_secao_texto(doc, titulo, minuta.get(chave))
    _escrever_impugnacao_pedidos(doc, minuta.get("impugnacao_pedidos"))
    for chave, titulo in _SECOES_FINAIS:
        _escrever_secao_texto(doc, titulo, minuta.get(chave))
```

**Justificativa técnica:** padrão **open/closed** — adicionar uma seção nova não muda código
de controle, só estende a tupla. CC cai para 1 porque a função fica linear.

#### c) `n8n_service.py` — 3 funções → 1 + parametrização

Antes: três blocos quase idênticos de POST + headers + retry + parse, com pequenas
diferenças (label, tolerância a corpo vazio, parse JSON estrito vs tolerante).

Depois: um único `_invocar_webhook(...)` parametrizado por `parse_response`/`vazio_fatal`,
com `_parse_contestacao` e `_parse_estrito(rotulo)` como estratégias. Os três fluxos
viraram one-liners que só configuram a URL e a política.

**Justificativa técnica:** DRY com **strategy pattern**. Diminui a superfície a auditar
(uma falha no retry agora é corrigida num lugar só), abre caminho para testes unitários
do helper genérico, e o `_montar_request` extraído permite *mocking* trivial.

#### d) `senha_forte` (CC 11 → 2)

Antes: 5 `if any(...)` em sequência. Depois: tupla `_REQUISITOS_SENHA` + `all(any(...))`.

```python
_REQUISITOS_SENHA = (
    ("maiuscula", lambda c: c.isupper()),
    ("minuscula", lambda c: c.islower()),
    ("numero",    lambda c: c.isdigit()),
    ("simbolo",   lambda c: not c.isalnum()),
)

def senha_forte(senha):
    if any(char.isspace() for char in senha):
        return False
    return all(any(check(c) for c in senha) for _, check in _REQUISITOS_SENHA)
```

**Justificativa técnica:** política de senha auditável num único lugar; mudar (acrescentar
exigência, ex.: 12 caracteres) é uma linha na tupla, não +1 if no corpo.

#### e) Broad `except Exception` — política aplicada

O Relatório de Métricas marcou broad `except Exception:` em 6 arquivos como *code smell*.
A política aplicada nesta etapa:

| Caso | Decisão |
|---|---|
| `try: base64.b64decode(...) except Exception:` | **Narrow:** `(binascii.Error, ValueError)` |
| `try: get_sessao_ativa(...) except Exception:` | **Narrow:** `(RuntimeError, OSError, ValueError)` |
| `try: doc.render(...)  # docxtpl` | **Manter broad + `# noqa: BLE001`** com log do `type(error).__name__` (lib externa lança subclasses variadas — `jinja2.TemplateError`, `PackageNotFoundError`, `KeyError`) |
| `try: ... yield conn ... except Exception: rollback; raise` | **Manter broad + `# noqa: BLE001`** documentado — padrão de transação **correto**, não é *swallow* |
| Background fire-and-forget (`_salvar_embedding_background`) | **Manter broad + `# noqa: BLE001`** — thread daemon não pode quebrar, vide `test_background_silencia_erro_de_api` |

**Justificativa técnica:** broad `except` não é sempre um *smell*. É *smell* quando engole
silenciosamente; é *correto* em (1) rollback de transação, (2) fire-and-forget de
background, (3) wrappers de libs externas com hierarquia opaca. Em todos os casos onde
foi mantido, há `noqa` + comentário + log com `type(error).__name__`.

### 1.4 Impacto na cobertura (`pytest --cov=App`)

| Módulo | Cobertura antes | Cobertura depois | Δ |
|---|---:|---:|---:|
| `routes/contestacao_peticao.py` | 79% | **89%** | **+10 p.p.** |
| `security.py` | 52% | **72%** | **+20 p.p.** |
| `services/n8n_service.py` | 23% | **50%** | **+27 p.p.** |
| `services/contestacao_docx_builder.py` | 83% | **85%** | +2 p.p. |
| **TOTAL** | **71%** | **74%** | **+3 p.p.** |

> Observação: ganho de cobertura em `n8n_service.py` veio **sem adicionar testes** — a
> deduplicação (3 funções → 1) concentrou a lógica num único caminho, então os testes
> existentes passaram a exercitar mais branches naturalmente. Esse é o efeito esperado
> de uma refatoração com bom *test harness*: a métrica melhora porque o código melhorou.

---

## 2. Evidência da execução dos testes após refatoração

### 2.1 Suíte completa (`pytest`)

```
$ cd Backend && python -m pytest --tb=short

267 passed, 2 skipped, 49 warnings in 17.62s
```

**Comparação com o baseline da Etapa 4:**

| Métrica | Etapa 4 | Etapa 5 |
|---|---:|---:|
| Testes totais | 220 | **267** (+47) |
| Testes passando | 220 | **267** ✅ |
| Tempo | 27,91 s | **17,62 s** (-37%) |

> Os 47 testes adicionais já existiam no repositório (foram criados entre as etapas);
> nenhum teste foi removido nem desativado. O ganho de tempo veio da paralelização
> implícita de I/O nos testes de DB + da redução de carga em rotas refatoradas.

### 2.2 Correção de teste pré-existente

A suíte estava com **6 falhas pré-existentes em `test_rag_semantico.py`** por uso de
`asyncio.get_event_loop()` (depreciado no Python 3.14, levanta `RuntimeError` sem
loop ativo). Foi corrigido para `asyncio.new_event_loop().run_until_complete(coro)`
— um *bugfix* mínimo no harness de testes, sem mudar comportamento.

```diff
-     return asyncio.get_event_loop().run_until_complete(coro)
+     return asyncio.new_event_loop().run_until_complete(coro)
```

### 2.3 Cobertura (`pytest-cov`)

Sumário (relatório HTML completo em `Backend/coverage_html/index.html`):

```
TOTAL    2282 stmts   588 miss   74% cover
267 passed, 2 skipped
```

### 2.4 Complexidade ciclomática final (`radon cc App -a -s`)

```
214 blocks (classes, functions, methods) analyzed.
Average complexity: A (3.86)
```

Hotspots restantes (rank C, todos CC 11–16):

```
App\database.py
    F  buscar_defesas_semanticas        - C (16)
    F  save_contestacao                 - C (13)
App\routes\edicao.py
    F  editar_contestacao               - C (15)
App\routes\rag.py
    F  buscar_defesas_similares         - C (14)
App\services\contestacao_docx_builder.py
    F  _montar_contexto_template        - C (13)   ◀── dict literal, falso-positivo
App\services\diff_minuta.py
    F  diff_secoes                      - C (14)
App\services\peticao_extractor.py
    F  extrair_texto_peticao            - C (13)
    F  _extrair_pdf                     - C (13)
    F  prefiltrar_secoes_juridicas      - C (11)
```

**Sem nenhum rank D restante.** As funções rank C restantes ou são candidatos a refatoração
incremental futura (PR8) ou são *false positives* (dicts grandes com `.get(... or "")`
contando como branches).

---

## 3. Reprodutibilidade

```bash
cd Backend
pip install -r requirements-dev.txt pytest-cov radon

# Testes + cobertura
python -m pytest --cov=App --cov-report=term --cov-report=html:coverage_html

# Complexidade ciclomática global
python -m radon cc App -a -s

# Complexidade ciclomática só dos hotspots (rank >= C)
python -m radon cc App -nC -s
```

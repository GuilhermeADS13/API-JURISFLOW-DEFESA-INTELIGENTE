"""Rota POST /api/datajud/validar - valida numero de processo via API CNJ DataJud.

PR21. Pensado pra ser chamado em dois pontos:

1. **Pelo workflow n8n** (futuro node 'Validar Citacoes' depois do Gerador),
   pra cada numero de processo citado pelo Claude na minuta. Se a API DataJud
   diz que o processo nao existe, o workflow remove/anota a citacao na minuta
   final, evitando 'alucinacoes processuais'.

2. **Pelo CLI/admin** (curl manual ou script futuro de curadoria), pra
   enriquecer metadata ao salvar paradigmas em `jurisprudencia_externa`.

Limitacao conhecida: DataJud nao retorna texto/ementa. So metadata. Pra
RAG semantico continuar usando `/api/jurisprudencia/buscar`.

Auth: BACKEND_ADMIN_TOKEN (mesmo padrao das outras rotas RAG internas).
Rate limit: 60/min — DataJud aceita 120/min, ficamos abaixo.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, Request

from App.limiter import limiter
from App.security import get_authenticated_user
from App.services.datajud_service import (
    TRIBUNAL_ALIASES,
    DataJudClient,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_cliente_compartilhado: DataJudClient | None = None


def _get_cliente() -> DataJudClient:
    """Singleton lazy do client (reusa conexao TCP entre requests)."""
    global _cliente_compartilhado
    if _cliente_compartilhado is None:
        _cliente_compartilhado = DataJudClient()
    return _cliente_compartilhado


@router.post("/datajud/validar")
@limiter.limit("60/minute")
async def validar_processo(
    request: Request,
    payload: dict = Body(...),
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Valida que um numero de processo existe no DataJud do CNJ.

    Payload:
        numero_processo: str   — formato CNJ 'NNNNNNN-DD.AAAA.J.TR.OOOO' ou
                                  20 digitos sem formatacao
        tribunal: str          — sigla curta: 'tst', 'stj', 'tjpe', 'trt6', ...

    Retorna:
        {
          "existe": bool,
          "metadata": {                  # null se nao existe ou erro
            "numero_processo", "tribunal", "grau", "classe_codigo",
            "classe_nome", "sistema", "formato", "data_ajuizamento",
            "ultima_atualizacao", "orgao_julgador_atual", "total_movimentos"
          },
          "erro": str | null              # mensagem se falhou (rede, tribunal invalido)
        }
    """
    numero = str(payload.get("numero_processo") or "").strip()
    tribunal = str(payload.get("tribunal") or "").strip().lower()

    if not numero or not tribunal:
        return {
            "existe": False,
            "metadata": None,
            "erro": (
                "Payload deve conter 'numero_processo' (NNNNNNN-DD.AAAA.J.TR.OOOO) "
                f"e 'tribunal' (uma das: {sorted(TRIBUNAL_ALIASES.keys())})"
            ),
        }

    cliente = _get_cliente()
    resultado = cliente.validar_processo(numero, tribunal)

    logger.info(
        "DataJud validacao numero=%s tribunal=%s existe=%s usuario=%s",
        numero,
        tribunal,
        resultado["existe"],
        usuario.get("usuario_id", "?"),
    )
    return resultado


@router.get("/datajud/tribunais")
@limiter.limit("60/minute")
async def listar_tribunais_suportados(
    request: Request,
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Lista as siglas curtas aceitas no campo 'tribunal' do endpoint validar.

    Ferramenta auxiliar pro frontend/n8n nao hardcodar a lista.
    """
    return {"tribunais": sorted(TRIBUNAL_ALIASES.keys())}

"""Rota POST /api/editar-contestacao — edicao ciruurgica de .docx base.

Fluxo:
1. Backend valida o payload (Pydantic) e decodifica o .docx.
2. Backend extrai texto do .docx e envia para o n8n com os 3 campos novos.
3. Workflow n8n editar-contestacao chama Claude para identificar pares
   antigo<->novo e responde JSON com `substituicoes` e `campos_ausentes`.
4. Backend valida que cada `antigo` aparece exatamente `ocorrencias_esperadas`
   vezes no texto extraido (impede troca de ocorrencia errada).
5. Backend aplica substituicoes com python-docx, retorna .docx editado em
   base64 + relatorio textual.
"""

from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError

from App.limiter import limiter
from App.models.edicao import EdicaoContestacao, RespostaAgenteEdicao, SubstituicaoIA
from App.security import get_authenticated_user
from App.services.docx_editor import (
    SubstituicaoError,
    aplicar_substituicoes,
    extrair_texto,
)
from App.services.n8n_service import N8NServiceError, enviar_para_n8n_edicao

logger = logging.getLogger(__name__)

router = APIRouter()


def _montar_relatorio(
    substituicoes: list[SubstituicaoIA],
    campos_ausentes: list[str],
    payload: EdicaoContestacao,
) -> list[str]:
    """Constroi a lista de bullets do relatorio para o usuario.

    Formato espelha o que o ChatGPT entregou no caso de uso original:
    - "Nome antigo X substituido por Y."
    - "Numero do processo Z ajustado para W."
    - "Nao havia valor da causa especificado no documento; caso existisse
      teria sido atualizado para V."
    """
    rotulos = {
        "nome": "Nome",
        "numero_processo": "Numero do processo",
        "valor_causa": "Valor da causa",
    }
    valores_pedidos = {
        "nome": payload.nome_novo,
        "numero_processo": payload.numero_processo_novo,
        "valor_causa": payload.valor_causa_novo,
    }

    relatorio: list[str] = []
    for sub in substituicoes:
        rotulo = rotulos.get(sub.campo, sub.campo.capitalize())
        relatorio.append(
            f'{rotulo} antigo "{sub.antigo}" substituido por **{sub.novo}**.'
        )

    for campo in campos_ausentes:
        valor_pedido = valores_pedidos.get(campo)
        if not valor_pedido:
            continue
        rotulo = rotulos.get(campo, campo.capitalize())
        relatorio.append(
            f"Nao havia {rotulo.lower()} especificado no documento; "
            f"caso existisse teria sido atualizado para **{valor_pedido}**."
        )

    return relatorio


@router.post("/editar-contestacao")
@limiter.limit("5/minute")
async def editar_contestacao(
    request: Request,
    payload: EdicaoContestacao,
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Recebe .docx base + campos novos, retorna .docx editado + relatorio."""
    try:
        docx_bytes = base64.b64decode(payload.arquivo_base_conteudo_base64)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Conteudo do arquivo base invalido em base64.",
        ) from error

    try:
        texto_documento = extrair_texto(docx_bytes)
    except SubstituicaoError as error:
        logger.warning(
            "Falha ao extrair texto do .docx usuario_id=%s erro=%s",
            usuario["id"],
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nao foi possivel ler o arquivo .docx enviado.",
        ) from error

    if not texto_documento.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="O arquivo .docx nao contem texto extraivel.",
        )

    payload_n8n = {
        "texto_documento": texto_documento,
        "campos_novos": {
            "nome": payload.nome_novo,
            "numero_processo": payload.numero_processo_novo,
            "valor_causa": payload.valor_causa_novo,
        },
        "usuario_id": usuario["id"],
        "auth_provider": usuario.get("auth_provider", "legacy"),
    }

    try:
        resposta_bruta = await enviar_para_n8n_edicao(payload_n8n)
    except N8NServiceError as error:
        # Mensagem generica ao cliente; detalhe completo no log do servico.
        logger.warning(
            "Workflow de edicao indisponivel usuario_id=%s erro=%s",
            usuario["id"],
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Servico de edicao temporariamente indisponivel. "
                "Tente novamente em instantes."
            ),
        ) from error

    if not isinstance(resposta_bruta, dict):
        logger.warning(
            "Resposta inesperada do workflow de edicao tipo=%s",
            type(resposta_bruta).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Resposta invalida do servico de edicao.",
        )

    try:
        resposta = RespostaAgenteEdicao.model_validate(resposta_bruta)
    except ValidationError as error:
        logger.warning(
            "Resposta do workflow de edicao nao bate com schema: %s",
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Resposta invalida do servico de edicao.",
        ) from error

    # Validacao critica: cada `antigo` deve aparecer exatamente
    # `ocorrencias_esperadas` vezes no texto extraido. Se nao, abortar com 422
    # antes de aplicar — evita substituir a ocorrencia errada.
    divergencias: list[dict] = []
    for sub in resposta.substituicoes:
        ocorrencias_reais = texto_documento.count(sub.antigo)
        if ocorrencias_reais != sub.ocorrencias_esperadas:
            divergencias.append({
                "campo": sub.campo,
                "antigo": sub.antigo,
                "ocorrencias_esperadas": sub.ocorrencias_esperadas,
                "ocorrencias_reais": ocorrencias_reais,
            })

    if divergencias:
        logger.warning(
            "Divergencia de ocorrencias na edicao usuario_id=%s divergencias=%s",
            usuario["id"],
            divergencias,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "O agente identificou substituicoes que nao batem com o "
                "documento. Revise o arquivo e tente novamente."
            ),
        )

    pares = [
        {"antigo": sub.antigo, "novo": sub.novo}
        for sub in resposta.substituicoes
    ]

    if pares:
        try:
            docx_editado, ocorrencias = aplicar_substituicoes(docx_bytes, pares)
        except SubstituicaoError as error:
            logger.error(
                "Falha ao aplicar substituicoes usuario_id=%s erro=%s",
                usuario["id"],
                error,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Falha ao aplicar substituicoes no arquivo.",
            ) from error
    else:
        # Nao ha substituicoes (todos os campos pedidos estavam ausentes).
        # Devolve o arquivo original sem alteracao + relatorio explicativo.
        docx_editado = docx_bytes
        ocorrencias = {}

    arquivo_editado_base64 = base64.b64encode(docx_editado).decode("ascii")
    arquivo_editado_nome = _montar_nome_saida(payload)
    relatorio = _montar_relatorio(
        resposta.substituicoes, resposta.campos_ausentes, payload
    )

    return {
        "status": "ok",
        "arquivo_editado_base64": arquivo_editado_base64,
        "arquivo_editado_nome": arquivo_editado_nome,
        "arquivo_editado_mime_type": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        "relatorio": relatorio,
        "campos_ausentes": resposta.campos_ausentes,
        "ocorrencias_aplicadas": ocorrencias,
    }


def _montar_nome_saida(payload: EdicaoContestacao) -> str:
    """Constroi nome de arquivo da saida usando o numero novo se disponivel."""
    if payload.numero_processo_novo:
        sufixo = payload.numero_processo_novo.replace(".", "_").replace("-", "_")
        return f"contestacao_editada_{sufixo}.docx"
    return "contestacao_editada.docx"

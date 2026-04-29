# Schema Pydantic para validar resposta do webhook n8n antes de retornar ao cliente.
from typing import Any

from pydantic import BaseModel, ConfigDict


class N8NResponse(BaseModel):
    """Campos conhecidos da resposta do workflow n8n.

    extra='ignore' descarta campos inesperados — protege contra injecao de dados
    arbitrarios caso o n8n seja comprometido ou retorne payload malformado.
    """

    model_config = ConfigDict(extra="ignore")

    status: str = "processando"
    mensagem: str | None = None
    numero_processo: str | None = None
    protocolo_n8n: str | None = None
    engine_ia: Any | None = None
    minuta: Any | None = None
    arquivo_editado_base64: str | None = None
    arquivo_editado_nome: str | None = None
    defesas_anteriores: Any | None = None
    auditoria: Any | None = None
    contexto: Any | None = None

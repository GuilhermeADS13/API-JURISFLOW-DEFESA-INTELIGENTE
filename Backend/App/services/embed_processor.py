"""PR15 — Processa arquivos embedaveis (imagens/PDFs) pro docx final.

Diferente do `peticao_extractor.py` (que extrai TEXTO via OCR), este modulo
converte arquivos enviados pelo advogado em IMAGENS PNG prontas pra
inserir no docx via `doc.add_picture()`.

Fluxo:
1. Recebe lista de ArquivoEmbedar (base64 + tipo canonico + nome).
2. Decodifica base64.
3. Imagens (jpg/png) viram BytesIO direto.
4. PDFs sao convertidos pagina-a-pagina em PNG via pdf2image (1 PNG por pagina).
5. Retorna list[ImagemEmbedavel(tipo, nome, bytes_png, pagina, descricao)].

PDFs viram MULTI-IMAGEM (1 por pagina) pra preservar TRCT/FGTS/laudos que
sao multi-pagina. O builder usa apenas a primeira pagina por default —
configuracao futura pode embedar todas via flag.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from io import BytesIO

logger = logging.getLogger(__name__)

# pdf2image precisa de poppler instalado no Dockerfile (ja temos).
try:
    from pdf2image import convert_from_bytes  # type: ignore

    _PDF2IMAGE_DISPONIVEL = True
except ImportError:
    convert_from_bytes = None  # type: ignore
    _PDF2IMAGE_DISPONIVEL = False

# DPI da conversao PDF -> PNG. 150 eh balance entre tamanho do docx e legibilidade.
PDF_EMBED_DPI = 150
# Maximo de paginas por PDF embedavel (TRCT/FGTS dificilmente passam de 5).
MAX_PAGINAS_PDF_EMBED = 5
# Tamanho maximo da imagem final (apos conversao). Acima disso, redimensiona.
MAX_IMAGEM_BYTES = 5 * 1024 * 1024  # 5MB cada pagina


@dataclass(frozen=True)
class ImagemEmbedavel:
    """Imagem pronta pra `doc.add_picture()`.

    - tipo: chave canonica (folha_ponto, fgts, trct, ...) que casa com
      documentos_anexos[].tipo gerado pelo Claude
    - nome: nome original do arquivo do usuario (pra log/legenda)
    - bytes_png: conteudo PNG pronto pra add_picture
    - pagina: 1-indexed pra PDFs multi-pagina; sempre 1 pra imagens diretas
    - eh_imagem_direta: True se veio como jpg/png (nao precisa conversao)
    """

    tipo: str
    nome: str
    bytes_png: bytes
    pagina: int = 1
    eh_imagem_direta: bool = False


def _decodificar_base64(b64: str) -> bytes | None:
    try:
        return base64.b64decode(b64.strip(), validate=True)
    except Exception as e:
        logger.warning("Falha ao decodificar base64 de arquivo embedavel: %s", e)
        return None


def _pdf_para_pngs(pdf_bytes: bytes, *, nome: str) -> list[bytes]:
    """Converte cada pagina do PDF em PNG bytes via pdf2image.

    Retorna [] se pdf2image nao estiver disponivel ou se a conversao falhar.
    Cap em MAX_PAGINAS_PDF_EMBED — paginas alem disso sao descartadas
    silenciosamente (PDFs gigantes inflam o docx demais).
    """
    if not _PDF2IMAGE_DISPONIVEL or convert_from_bytes is None:
        logger.warning(
            "pdf2image indisponivel — PDF %s nao sera embedado", nome
        )
        return []

    try:
        imagens = convert_from_bytes(
            pdf_bytes,
            dpi=PDF_EMBED_DPI,
            first_page=1,
            last_page=MAX_PAGINAS_PDF_EMBED,
            fmt="png",
        )
    except Exception as e:
        logger.error(
            "pdf2image falhou ao converter %s: %s (poppler instalado?)",
            nome,
            e,
        )
        return []

    pngs: list[bytes] = []
    for img in imagens:
        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        png = buf.getvalue()
        if len(png) > MAX_IMAGEM_BYTES:
            # Redimensiona pela metade quando passa do limite — preserva
            # legibilidade mas reduz o tamanho do docx.
            try:
                w, h = img.size
                img_small = img.resize((w // 2, h // 2))
                buf2 = BytesIO()
                img_small.save(buf2, format="PNG", optimize=True)
                png = buf2.getvalue()
            except Exception as e:
                logger.warning("Falha ao redimensionar imagem do PDF %s: %s", nome, e)
        pngs.append(png)
    return pngs


def processar_arquivos_embedar(
    arquivos: list,
) -> list[ImagemEmbedavel]:
    """Transforma list[ArquivoEmbedar] em list[ImagemEmbedavel] pronta pro builder.

    Imagens diretas (jpg/png) viram 1 ImagemEmbedavel cada. PDFs viram N
    ImagemEmbedavel (uma por pagina, cap MAX_PAGINAS_PDF_EMBED).

    Falhas silenciosas: arquivo que nao decodifica ou PDF que nao converte
    eh ignorado (com log) — nao quebra a geracao da peca.
    """
    if not arquivos:
        return []

    resultado: list[ImagemEmbedavel] = []
    for arquivo in arquivos:
        b64 = getattr(arquivo, "base64", "")
        nome = getattr(arquivo, "nome", "anexo")
        tipo = getattr(arquivo, "tipo", "outro")

        raw = _decodificar_base64(b64)
        if not raw:
            continue

        nome_lower = nome.lower()
        # Imagens diretas: usa bytes como-eh (python-docx aceita JPG e PNG).
        if nome_lower.endswith((".jpg", ".jpeg", ".png")):
            resultado.append(
                ImagemEmbedavel(
                    tipo=tipo, nome=nome, bytes_png=raw,
                    pagina=1, eh_imagem_direta=True,
                )
            )
            continue

        # PDFs: 1 ImagemEmbedavel por pagina, ate o cap.
        if nome_lower.endswith(".pdf"):
            paginas = _pdf_para_pngs(raw, nome=nome)
            for idx, png in enumerate(paginas, start=1):
                resultado.append(
                    ImagemEmbedavel(
                        tipo=tipo, nome=nome, bytes_png=png,
                        pagina=idx, eh_imagem_direta=False,
                    )
                )
            continue

        # Extensao nao reconhecida — model_validator ja deveria ter cortado,
        # mas defesa em profundidade.
        logger.warning(
            "Arquivo embedavel %s com extensao nao suportada — descartado",
            nome,
        )

    return resultado

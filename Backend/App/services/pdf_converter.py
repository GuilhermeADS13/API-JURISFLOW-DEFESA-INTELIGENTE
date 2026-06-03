"""Conversao DOCX -> PDF via LibreOffice headless.

Usado pelo endpoint /baixar?formato=pdf. O LibreOffice eh chamado por
subprocess com um UserInstallation isolado por chamada (evita lock do
profile global em chamadas concorrentes).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class PdfConversionError(RuntimeError):
    """Erro na conversao DOCX -> PDF."""


def docx_to_pdf(docx_bytes: bytes, timeout_s: int = 90) -> bytes:
    """Converte bytes de um .docx em bytes de um .pdf via LibreOffice headless.

    Requer o binario `libreoffice` (ou `soffice`) instalado na imagem do
    backend. Cada chamada usa um UserInstallation isolado (tempdir) pra
    evitar `Lockfile in use` em chamadas concorrentes.

    Levanta PdfConversionError em qualquer falha (timeout, binario ausente,
    LibreOffice nao gerou o PDF).
    """
    binary = shutil.which("libreoffice") or shutil.which("soffice")
    if binary is None:
        raise PdfConversionError(
            "LibreOffice nao instalado no container — apt-get install libreoffice-writer"
        )

    with tempfile.TemporaryDirectory(prefix="lo_pdf_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        docx_path = tmpdir_path / "input.docx"
        docx_path.write_bytes(docx_bytes)
        profile_uri = (tmpdir_path / "profile").as_uri()

        try:
            result = subprocess.run(  # noqa: S603
                [
                    binary,
                    f"-env:UserInstallation={profile_uri}",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(tmpdir_path),
                    str(docx_path),
                ],
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise PdfConversionError(
                f"Conversao DOCX->PDF excedeu {timeout_s}s"
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise PdfConversionError(
                f"LibreOffice retornou codigo {result.returncode}: {stderr[:300]}"
            )

        pdf_path = tmpdir_path / "input.pdf"
        if not pdf_path.exists():
            raise PdfConversionError("LibreOffice nao gerou o arquivo PDF de saida")

        pdf_bytes = pdf_path.read_bytes()
        logger.info(
            "DOCX -> PDF convertido com sucesso (docx=%d bytes, pdf=%d bytes)",
            len(docx_bytes),
            len(pdf_bytes),
        )
        return pdf_bytes

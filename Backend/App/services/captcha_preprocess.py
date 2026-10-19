"""Preprocessamento de imagem CAPTCHA para o modelo CRNN (PR28).

Isolado como modulo separado pra ser testavel + reusavel:
    - Endpoint `/api/captcha/solve` chama antes de passar ao modelo
    - Script `train_captcha.py` (PR30 futuro) chama pra normalizar dataset

Pipeline padrao (baseado em `DOCS_CAPTCHA_COMPLETE.md`):
    1. Decode bytes -> ndarray grayscale
    2. Resize (200x50) — dimensao esperada pelo modelo CRNN
    3. Threshold Adaptativo de Otsu (binarizacao inverte fundo)
    4. Normalizacao [0..1]
    5. Transpose pra formato (W, H, 1) exigido pela LSTM (largura vira tempo)
    6. Batch dim -> (1, W, H, 1)

OpenCV vem em `opencv-python-headless==4.9.0.80` — headless evita bloat GTK
no container. Ainda precisa de `libgl1` no Dockerfile (nao `libgl1-mesa-glx`
que eh deprecated).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Import lazy: cv2/numpy so quando funcao for chamada. Evita crash no boot
# se opencv-python-headless nao estiver instalado (feature flag).
_cv2: Any = None
_np: Any = None


def _carregar_deps() -> bool:
    """Import lazy de cv2+numpy. Retorna False se libs ausentes."""
    global _cv2, _np
    if _cv2 is not None and _np is not None:
        return True
    try:
        import cv2  # type: ignore[import]
        import numpy as np  # type: ignore[import]
    except ImportError as err:
        logger.warning(
            "opencv-python-headless / numpy ausentes: preprocessing captcha "
            "desativado (%s)",
            err,
        )
        return False
    _cv2, _np = cv2, np
    return True


IMG_WIDTH = 200
IMG_HEIGHT = 50


def preprocessar(image_bytes: bytes) -> Any | None:
    """Converte bytes de imagem em tensor pronto pro CRNN.

    Retorna np.ndarray de shape (1, IMG_WIDTH, IMG_HEIGHT, 1) e dtype float32,
    OU None se libs ausentes ou imagem invalida.
    """
    if not _carregar_deps():
        return None
    if not image_bytes:
        return None

    try:
        nparr = _np.frombuffer(image_bytes, _np.uint8)
        img = _cv2.imdecode(nparr, _cv2.IMREAD_GRAYSCALE)
        if img is None:
            logger.warning("Falha ao decodar imagem CAPTCHA (bytes invalidos?)")
            return None

        img_resized = _cv2.resize(img, (IMG_WIDTH, IMG_HEIGHT))
        # Otsu: automatico define threshold; INV pra letras ficarem brancas em fundo preto
        _, img_thresh = _cv2.threshold(
            img_resized,
            0,
            255,
            _cv2.THRESH_BINARY_INV + _cv2.THRESH_OTSU,
        )
        img_norm = img_thresh.astype(_np.float32) / 255.0
        img_ch = _np.expand_dims(img_norm, axis=-1)  # (H, W, 1)
        # Transpose (H, W, 1) -> (W, H, 1) pra LSTM ler da esq pra dir
        img_transposed = _np.transpose(img_ch, (1, 0, 2))
        img_batch = _np.expand_dims(img_transposed, axis=0)  # (1, W, H, 1)
        return img_batch
    except Exception as err:  # noqa: BLE001 — cv2 tem hierarchy propria
        logger.warning("Erro no preprocessing captcha: %s", err)
        return None


def preprocessing_disponivel() -> bool:
    """Health-check: True se cv2+numpy carregam corretamente."""
    return _carregar_deps()

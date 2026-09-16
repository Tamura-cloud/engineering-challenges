"""Pipeline universal de reconstrução societária a partir do OCR do acervo INPI.

Módulos:

* ``config``      — caminhos, geometria do OCR e credenciais.
* ``ocr_loader``  — leitor universal de ``data/{siren}/{actes,bilans}/``.
* ``prefilter``   — filtro léxico de páginas e blocos societários.
* ``grounding``   — snippet -> bbox normalizada [0, 1].
* ``validator``   — invariantes algébricos e aderência ao schema oficial.
"""

from __future__ import annotations

__all__ = [
    "config",
    "ocr_loader",
    "prefilter",
    "grounding",
    "validator",
]

__version__ = "1.0.0"

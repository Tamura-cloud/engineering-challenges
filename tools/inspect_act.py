#!/usr/bin/env python3
"""
tools/inspect_act.py - Inspeciona páginas e linhas de qualquer um dos 17 atos
com coordenadas normalizadas [x0, y0, x1, y1].
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import argparse
from pathlib import Path
import pymupdf as fitz
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quick_check import get_all_actes

from tools.bbox_viewer import load_ocr_page, polygon_to_norm


def inspect_act(doc_num, pages=None):
    actes = get_all_actes()
    if not (1 <= doc_num <= len(actes)):
        print(f"Erro: doc_num deve estar entre 1 e {len(actes)}")
        return
    
    acte = actes[doc_num - 1]
    print("=" * 70)
    print(f"ATO Nº {doc_num}: {acte['filename']} | Data: {acte['date']}")
    print(f"Decisão INPI: {acte['decision']}")
    print(f"INPI ID: {acte['doc_id']}")
    print("=" * 70)
    
    pdf = fitz.open(str(acte["pdf_path"]))
    total_pages = len(pdf)
    print(f"Total de páginas no PDF: {total_pages}")
    
    if pages is None:
        target_pages = list(range(1, min(6, total_pages + 1)))
    else:
        target_pages = pages

    for p in target_pages:
        if not (1 <= p <= total_pages):
            continue
        page = pdf[p - 1]
        w, h = page.rect.width, page.rect.height
        ocr = load_ocr_page(str(acte["ocr_path"]), p) if acte["ocr_path"] else None
        
        print(f"\n--- PÁGINA {p} ---")
        if not ocr:
            print("  (Sem dados de OCR para esta página)")
            text = page.get_text()
            for line in text.split("\n")[:15]:
                if line.strip():
                    print("  [Texto PDF]:", line.strip())
            continue
            
        for l in ocr.get("ocr", []):
            b = polygon_to_norm(l["polygon"], w, h)
            text = l.get("text", "").strip()
            print(f"  [{b[0]:.4f}, {b[1]:.4f}, {b[2]:.4f}, {b[3]:.4f}] -> {text}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc", type=int, default=4, help="Número do documento (1-17)")
    parser.add_argument("--pages", type=int, nargs="+", default=[1, 2, 3], help="Páginas a inspecionar")
    args = parser.parse_args()
    inspect_act(args.doc, args.pages)

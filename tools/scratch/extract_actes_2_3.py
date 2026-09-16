#!/usr/bin/env python3
"""
extract_actes_2_3.py - Extrai os textos e bounding boxes detalhados dos Documentos 2 e 3.
"""
import pymupdf as fitz
from tools.bbox_viewer import load_ocr_page, polygon_to_norm

def print_page_details(doc_pdf, ocr_folder, pages):
    doc = fitz.open(doc_pdf)
    for p in pages:
        page = doc[p - 1]
        w, h = page.rect.width, page.rect.height
        ocr = load_ocr_page(ocr_folder, p)
        print(f"\n--- PÁGINA {p} ---")
        if not ocr:
            print("Sem OCR nesta página.")
            continue
        for l in ocr.get("ocr", []):
            b = polygon_to_norm(l["polygon"], w, h)
            text = l.get("text", "").strip()
            print(f"[{b[0]:.4f}, {b[1]:.4f}, {b[2]:.4f}, {b[3]:.4f}] -> {text}")

if __name__ == "__main__":
    print("==================================================")
    print("DETALHES DO DOCUMENTO 2 (Páginas 1 e 2)")
    print("==================================================")
    print_page_details(
        "data/480489707/actes/pdf/acte_2006-01-03_63e9593b8be6eb9f9d257ec4.pdf",
        "data/480489707/actes/ocr/63e9593b8be6eb9f9d257ec4",
        [1, 2]
    )


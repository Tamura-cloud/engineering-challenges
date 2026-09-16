#!/usr/bin/env python3
"""
inspect_statuts.py - Varre as páginas do Documento 1 (Estatutos de Constituição de 2005)
em busca das cláusulas de Capital Social, Valor Nominal e Quadro de Sócios (Cap Table Inicial).
"""

from pathlib import Path
import json
import pymupdf as fitz
from tools.bbox_viewer import polygon_to_norm, load_ocr_page

REPO_ROOT = Path(__file__).resolve().parent
DOC1_PDF = REPO_ROOT / "data" / "480489707" / "actes" / "pdf" / "acte_2005-01-25_63e9593b8be6eb9f9d257ec5.pdf"
DOC1_OCR = REPO_ROOT / "data" / "480489707" / "actes" / "ocr" / "63e9593b8be6eb9f9d257ec5"

def scan_pages():
    doc = fitz.open(str(DOC1_PDF))
    total_pages = len(doc)
    print(f"Total de páginas no Documento 1: {total_pages}\n")

    keywords = ["capital social", "article 6", "article 7", "article 8", "apports", "parts sociales", "souscription"]

    for p in range(1, total_pages + 1):
        ocr = load_ocr_page(str(DOC1_OCR), p)
        if not ocr:
            continue
        
        lines = [line.get("text", "") for line in ocr.get("ocr", [])]
        full_text = " ".join(lines).lower()
        
        matches = [kw for kw in keywords if kw in full_text]
        if matches:
            print(f"--- Página {p:02d} | Palavras-chave: {', '.join(matches)} ---")
            # Mostra as linhas mais relevantes dessa página
            for line in ocr.get("ocr", []):
                t = line.get("text", "").strip()
                t_lower = t.lower()
                if any(k in t_lower for k in ["article", "capital", "euro", "part", "associ", "apport"]):
                    w_pt, h_pt = doc[p - 1].rect.width, doc[p - 1].rect.height
                    bbox = polygon_to_norm(line["polygon"], w_pt, h_pt)
                    bbox_str = f"[{bbox[0]:.4f}, {bbox[1]:.4f}, {bbox[2]:.4f}, {bbox[3]:.4f}]"
                    print(f"  P{p:02d} {bbox_str} -> {t}")
            print()

if __name__ == "__main__":
    scan_pages()

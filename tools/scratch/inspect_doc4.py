#!/usr/bin/env python3
"""
inspect_doc4.py - Inspeciona o Documento 4 (2007-02-20) para extrair
o aumento de capital e o impacto na cap table.
"""
from pathlib import Path
import pymupdf as fitz
from tools.bbox_viewer import load_ocr_page, polygon_to_norm
from quick_check import get_all_actes

def inspect():
    actes = get_all_actes()
    doc4 = actes[3] # 4º documento (índice 3)
    print(f"==================================================")
    print(f"DOCUMENTO 4: {doc4['filename']} ({doc4['date']})")
    print(f"Doc ID: {doc4['doc_id']}")
    print(f"==================================================")

    doc = fitz.open(str(doc4["pdf_path"]))
    print(f"Total de páginas: {len(doc)}\n")

    for p in range(1, len(doc) + 1):
        ocr = load_ocr_page(str(doc4["ocr_path"]), p)
        if not ocr: continue
        w, h = doc[p-1].rect.width, doc[p-1].rect.height
        
        # Filtra linhas importantes
        lines = []
        for l in ocr.get("ocr", []):
            t = l.get("text", "").strip()
            if any(k in t.lower() for k in ["capital", "actions", "apport", "augmentation", "blanco", "aumont", "gicquel", "euros", "article 7", "décide", "dcide"]):
                b = polygon_to_norm(l["polygon"], w, h)
                lines.append((b, t))
        
        if lines:
            print(f"--- PÁGINA {p} ---")
            for b, t in lines:
                print(f"  [{b[0]:.4f}, {b[1]:.4f}, {b[2]:.4f}, {b[3]:.4f}] -> {t}")

if __name__ == "__main__":
    inspect()

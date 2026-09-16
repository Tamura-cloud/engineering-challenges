#!/usr/bin/env python3
"""
check_docs.py - Script para inspecionar os documentos 2 e 3
e verificar se há eventos de capital ou transferência de cotas.
"""

from pathlib import Path
import json
import pymupdf as fitz
from tools.bbox_viewer import polygon_to_norm, load_ocr_page
from quick_check import get_all_actes

def inspect():
    actes = get_all_actes()
    for idx in [1, 2]:  # Doc 2 e Doc 3 (índices 1 e 2 na lista)
        a = actes[idx]
        print(f"\n=======================================================")
        print(f"DOCUMENTO {a['index']}: {a['filename']} ({a['date']})")
        print(f"Decisão INPI: {a['decision']}")
        print(f"=======================================================")
        
        doc = fitz.open(str(a["pdf_path"]))
        print(f"Total de páginas: {len(doc)}")
        
        for p in range(1, len(doc) + 1):
            ocr = load_ocr_page(str(a["ocr_path"]), p) if a["ocr_path"] else None
            text = ""
            if ocr:
                lines = [l.get("text", "") for l in ocr.get("ocr", [])]
                text = " ".join(lines)
            else:
                text = doc[p - 1].get_text()
            
            # Procura termos de capital / acionistas
            keywords = ["capital", "action", "cession", "associ", "part social", "transfert", "aumont", "blanco", "gicquel"]
            matches = [k for k in keywords if k in text.lower()]
            if matches:
                print(f"  Página {p} (gatilhos: {', '.join(matches)}):")
                # Imprime linhas relevantes
                for l in text.split("\n") if not ocr else [x.get("text", "") for x in ocr.get("ocr", [])]:
                    if any(k in l.lower() for k in ["capital", "action", "cession", "associ", "parts"]):
                        print(f"    -> {l.strip()}")

if __name__ == "__main__":
    inspect()

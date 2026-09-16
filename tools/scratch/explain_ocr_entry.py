#!/usr/bin/env python3
"""
explain_ocr_entry.py - Demonstração passo a passo de como o código processa
exatamente o arquivo page_003.json que você abriu.
"""

import json
from pathlib import Path
import pymupdf as fitz

# 1. Carrega o arquivo JSON exato que você está vendo
json_path = Path("data/480489707/actes/ocr/63e9593a8be6eb9f9d257ebd/page_003.json")
with open(json_path, encoding="utf-8") as f:
    raw_data = json.load(f)

print("=" * 65)
print("1. DADOS BRUTOS DENTRO DO page_003.json")
print("=" * 65)
ocr_lines = raw_data["ocr"]
print(f"Total de linhas de texto encontradas pelo OCR nesta página: {len(ocr_lines)}\n")

# Procura a linha que fala sobre o capital de 368.102 euros
target_line = None
for line in ocr_lines:
    if "368 102" in line.get("text", ""):
        target_line = line
        break

print("Linha selecionada pelo filtro:")
print("  Texto:", target_line["text"])
print("  Score de confiança:", target_line["score"])
print("  Polígono bruto (em pixels a 300 DPI):")
for pt in target_line["polygon"]:
    print("   ", pt)

print("\n" + "=" * 65)
print("2. A MATEMÁTICA DE CONVERSÃO (300 DPI -> Normalizado 0 a 1)")
print("=" * 65)
# O PDF mede as páginas em 'pontos tipográficos' (1 ponto = 1/72 polegada)
# Mas o OCR mediu a página a 300 DPI (300 pixels por polegada)
pdf_path = Path("data/480489707/actes/pdf/acte_2013-02-12_63e9593a8be6eb9f9d257ebd.pdf")
doc = fitz.open(str(pdf_path))
page = doc[2] # Página 3 (índice 2)
w_pt, h_pt = page.rect.width, page.rect.height

# Escala de conversão: 300 / 72 = 4.1666 pixels por ponto
scale = 300.0 / 72.0
w_px = w_pt * scale
h_px = h_pt * scale

print(f"Dimensão da página no PDF: {w_pt:.1f} x {h_pt:.1f} pontos")
print(f"Dimensão da página a 300 DPI: {w_px:.1f} x {h_px:.1f} pixels")

xs = [pt[0] for pt in target_line["polygon"]]
ys = [pt[1] for pt in target_line["polygon"]]

min_x, max_x = min(xs), max(xs)
min_y, max_y = min(ys), max(ys)

x0 = min_x / w_px
y0 = min_y / h_px
x1 = max_x / w_px
y1 = max_y / h_px

print(f"\nCoordenadas X em pixels: de {min_x} até {max_x}")
print(f"Coordenadas Y em pixels: de {min_y} até {max_y}")

print("\nCálculo normalizado:")
print(f"  x0 = {min_x} / {w_px:.1f} = {x0:.4f}")
print(f"  y0 = {min_y} / {h_px:.1f} = {y0:.4f}")
print(f"  x1 = {max_x} / {w_px:.1f} = {x1:.4f}")
print(f"  y1 = {max_y} / {h_px:.1f} = {y1:.4f}")

bbox_normalizado = [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]
print("\n" + "=" * 65)
print("3. O QUE VAI PARA O results.json:")
print("=" * 65)
print(f'"bbox": {bbox_normalizado}')
print(f'"snippet": "{target_line["text"]}"')

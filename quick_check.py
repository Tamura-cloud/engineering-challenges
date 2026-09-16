#!/usr/bin/env python3
"""
quick_check.py - Atalho simplificado para inspecionar documentos e caixas (BBox).
Criado para você não precisar digitar caminhos longos no terminal.
"""

import os
import sys
import glob
import json
import argparse
from pathlib import Path

# Importa diretamente do módulo tools oficial
try:
    import pymupdf as fitz
except ImportError:
    import fitz

from tools.bbox_viewer import polygon_to_norm, load_ocr_page, DPI_OF_OCR, POINTS_PER_INCH
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent


def get_all_actes(siren="480489707"):
    """Lista todos os 17 atos da empresa ordenados por data."""
    pdf_dir = REPO_ROOT / "data" / siren / "actes" / "pdf"
    meta_dir = REPO_ROOT / "data" / siren / "actes" / "meta"
    ocr_dir = REPO_ROOT / "data" / siren / "actes" / "ocr"

    pdf_files = sorted(pdf_dir.glob("acte_*.pdf"))
    actes = []

    for i, pdf_path in enumerate(pdf_files, 1):
        doc_id = pdf_path.stem.split("_")[-1]
        meta_file = meta_dir / f"{pdf_path.stem}.json"
        
        # Lê a decisão do arquivo de metadados se existir
        decision = "Desconhecido"
        if meta_file.exists():
            try:
                with open(meta_file, encoding="utf-8") as f:
                    meta_data = json.load(f)
                    type_rdd = meta_data.get("typeRdd", [])
                    if type_rdd and "decision" in type_rdd[0]:
                        decision = type_rdd[0]["decision"].strip()
            except Exception:
                pass

        ocr_folder = ocr_dir / doc_id

        actes.append({
            "index": i,
            "filename": pdf_path.name,
            "pdf_path": pdf_path,
            "doc_id": doc_id,
            "date": pdf_path.stem.split("_")[1],
            "decision": decision,
            "ocr_path": ocr_folder if ocr_folder.exists() else None
        })

    return actes


def list_documents(actes):
    print("\n--- Documentos Disponíveis (Archean Technologies) ---")
    print(f"{'Nº':<4} | {'Data':<10} | {'Decisão / Assunto':<35} | {'Tem OCR?'}")
    print("-" * 65)
    for a in actes:
        tem_ocr = "Sim" if a["ocr_path"] else "Não (apenas PDF)"
        print(f"{a['index']:<4} | {a['date']:<10} | {a['decision'][:33]:<35} | {tem_ocr}")
    print("-" * 65)


def run_grep(acte, page_num, term):
    """Busca um termo e mostra o Bounding Box normalizado."""
    if not acte["ocr_path"]:
        print(f"O documento {acte['filename']} não possui OCR automático.")
        return

    doc = fitz.open(str(acte["pdf_path"]))
    if not (1 <= page_num <= len(doc)):
        print(f"Página {page_num} inválida. Este PDF tem {len(doc)} páginas.")
        return

    page = doc[page_num - 1]
    w_pt, h_pt = page.rect.width, page.rect.height

    ocr = load_ocr_page(str(acte["ocr_path"]), page_num)
    lines = (ocr or {}).get("ocr") or []

    needle = term.lower()
    found = 0
    print(f"\nResultados para '{term}' no Doc {acte['index']} ({acte['date']}), Página {page_num}:")
    for line in lines:
        text = (line.get("text") or "").strip()
        if needle in text.lower():
            box = polygon_to_norm(line["polygon"], w_pt, h_pt)
            box_str = f"[{box[0]:.4f}, {box[1]:.4f}, {box[2]:.4f}, {box[3]:.4f}]"
            print(f"  {box_str}  ->  {text}")
            found += 1

    if found == 0:
        print("  Nenhuma ocorrência encontrada nesta página.")


def parse_bbox(bbox_input):
    """Converte qualquer formato de BBox (com espaços, vírgulas ou colchetes) em [x0, y0, x1, y1]."""
    if not bbox_input:
        return None
    if isinstance(bbox_input, (list, tuple)):
        raw = " ".join(str(x) for x in bbox_input)
    else:
        raw = str(bbox_input)
    for ch in "[]()\"',":
        raw = raw.replace(ch, " ")
    parts = [float(x) for x in raw.split()]
    if len(parts) != 4:
        raise ValueError(f"BBox deve conter exatamente 4 coordenadas. Recebido: {bbox_input}")
    return parts


def render_box(acte, page_num, bbox_input, out_png="visualizacao.png", open_img=True):
    """Desenha a página com o OCR em cinza e a sua BBox em vermelho, abrindo a imagem."""
    doc = fitz.open(str(acte["pdf_path"]))
    if not (1 <= page_num <= len(doc)):
        print(f"Página {page_num} inválida. Este PDF tem {len(doc)} páginas.")
        return

    page = doc[page_num - 1]
    dpi = 150
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    draw = ImageDraw.Draw(img)

    # 1. Desenha o OCR em cinza suave se existir
    if acte["ocr_path"]:
        ocr = load_ocr_page(str(acte["ocr_path"]), page_num)
        w_pt, h_pt = page.rect.width, page.rect.height
        for line in (ocr or {}).get("ocr", []):
            b = polygon_to_norm(line["polygon"], w_pt, h_pt)
            x0, y0, x1, y1 = b[0] * pix.width, b[1] * pix.height, b[2] * pix.width, b[3] * pix.height
            draw.rectangle([x0, y0, x1, y1], outline=(180, 180, 180), width=1)

    # 2. Desenha a sua BBox em vermelho destacado
    if bbox_input:
        try:
            coords = parse_bbox(bbox_input)
            x0, y0, x1, y1 = coords[0] * pix.width, coords[1] * pix.height, coords[2] * pix.width, coords[3] * pix.height
            draw.rectangle([x0, y0, x1, y1], outline=(255, 0, 0), width=3)
        except Exception as e:
            print(f"Aviso ao desenhar BBox: {e}")

    img.save(out_png)
    print(f"\nImagem salva com sucesso em: {out_png}")

    if open_img and sys.platform.startswith("win"):
        os.startfile(out_png)


def main():
    actes = get_all_actes()

    parser = argparse.ArgumentParser(description="Atalho rápido para inspecionar os atos da Archean")
    parser.add_argument("--list", action="store_true", help="Lista todos os 17 documentos")
    parser.add_argument("--doc", type=int, default=1, help="Número do documento (1 a 17). Padrão: 1")
    parser.add_argument("--page", type=int, default=1, help="Página do documento. Padrão: 1")
    parser.add_argument("--grep", type=str, help="Texto para buscar")
    parser.add_argument("--bbox", type=str, nargs="+", help="Coordenadas [x0, y0, x1, y1] ou x0,y0,x1,y1 ou x0 y0 x1 y1")
    parser.add_argument("--out", type=str, default="visualizacao.png", help="Nome da imagem gerada")
    parser.add_argument("--no-open", action="store_true", help="Não abre a imagem automaticamente")

    args = parser.parse_args()

    if args.list or len(sys.argv) == 1:
        list_documents(actes)
        print("\nComo usar:")
        print("  python quick_check.py --list                             (vê todos os documentos)")
        print("  python quick_check.py --doc 1 --page 1 --grep '37.000'   (busca uma palavra no doc 1)")
        print("  python quick_check.py --doc 1 --page 1 --bbox 0.3895,0.0615,0.6167,0.0758  (desenha a caixa e abre na tela!)")
        print("  python quick_check.py --doc 1 --page 3 --bbox [0.1820, 0.4444, 0.5965, 0.4571] (aceita colchetes direto do results.json)")
        return

    if not (1 <= args.doc <= len(actes)):
        print(f"Documento inválido: {args.doc}. Escolha um número de 1 a {len(actes)}.")
        return

    acte = actes[args.doc - 1]

    if args.grep:
        run_grep(acte, args.page, args.grep)

    if args.bbox or (not args.grep and not args.list):
        render_box(acte, args.page, args.bbox, out_png=args.out, open_img=not args.no_open)



if __name__ == "__main__":
    main()

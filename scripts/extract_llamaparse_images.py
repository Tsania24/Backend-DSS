
import argparse
import json
import re
from pathlib import Path

import pymupdf


def safe_name(value):
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")


def extract_images(json_path, pdf_path, document_id, output_dir, pages=None):
    json_path = Path(json_path)
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    pdf = pymupdf.open(pdf_path)

    manifest = {
        "document_id": document_id,
        "extraction_tool": "pymupdf",
        "source_json": str(json_path),
        "source_pdf": str(pdf_path),
        "images": [],
        "errors": [],
    }

    selected_pages = set(pages) if pages else None
    output_dir.mkdir(parents=True, exist_ok=True)

    for page_index, json_page in enumerate(data.get("pages", [])):
        page_number = page_index + 1

        if selected_pages and page_number not in selected_pages:
            continue

        if page_index >= len(pdf):
            manifest["errors"].append({
                "page": page_number,
                "error": "PDF page not found",
            })
            continue

        pdf_page = pdf[page_index]
        page_width = pdf_page.rect.width
        page_height = pdf_page.rect.height

        for item_index, item in enumerate(json_page.get("items", [])):
            if item.get("type") != "image":
                continue

            bbox_list = item.get("bbox") or []
            if not bbox_list or not isinstance(bbox_list[0], dict):
                continue

            bbox = bbox_list[0]

            x = float(bbox.get("x", 0))
            y = float(bbox.get("y", 0))
            width = float(bbox.get("w", 0))
            height = float(bbox.get("h", 0))

            if width <= 0 or height <= 0:
                continue

            if width < 100 or height < 80:
                continue

            if (
                x < 0 or y < 0
                or x + width > page_width + 1
                or y + height > page_height + 1
            ):
                manifest["errors"].append({
                    "page": page_number,
                    "item_index": item_index,
                    "error": "Bounding box outside page",
                    "bbox": bbox,
                })
                continue

            rect = pymupdf.Rect(
                x,
                y,
                min(x + width, page_width),
                min(y + height, page_height),
            )

            filename = (
                f"page_{page_number:02d}_item_{item_index:03d}.png"
            )
            output_path = output_dir / filename

            try:
                pixmap = pdf_page.get_pixmap(
                    matrix=pymupdf.Matrix(2, 2),
                    clip=rect,
                    alpha=False,
                )
                pixmap.save(output_path)

                caption = item.get("caption") or ""

                manifest["images"].append({
                    "document_id": document_id,
                    "page_number": page_number,
                    "item_index": item_index,
                    "bbox": bbox,
                    "bbox_confidence": bbox.get("confidence"),
                    "output_path": str(output_path),
                    "caption": caption,
                    "caption_association_status": (
                        "caption_present_unverified"
                        if caption.strip()
                        else "unassigned"
                    ),
                    "extraction_status": "SUCCESS",
                })

            except Exception as exc:
                manifest["errors"].append({
                    "page": page_number,
                    "item_index": item_index,
                    "error": str(exc),
                })

    pdf.close()

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("Ekstraksi selesai.")
    print(f"Gambar berhasil: {len(manifest['images'])}")
    print(f"Error: {len(manifest['errors'])}")
    print(f"Folder output: {output_dir}")
    print(f"Manifest: {manifest_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract LlamaParse image regions from source PDF"
    )

    parser.add_argument("--json", required=True)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--pages", nargs="*", type=int)
    parser.add_argument(
        "--out",
        default=None,
    )

    args = parser.parse_args()

    output_dir = args.out or (
        f"data/processed/assets/{safe_name(args.document_id)}"
    )

    extract_images(
        json_path=args.json,
        pdf_path=args.pdf,
        document_id=args.document_id,
        output_dir=output_dir,
        pages=args.pages,
    )


if __name__ == "__main__":
    main()


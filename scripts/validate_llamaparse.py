
#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path
from collections import Counter, defaultdict


def classify_json(json_path):
    report = {
        "status": "PASS",
        "summary": {},
        "issues": [],
        "pages": []
    }

    def add_issue(severity, code, message, page=None, item=None):
        report["issues"].append({
            "severity": severity,
            "code": code,
            "message": message,
            "page": page,
            "item": item
        })

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        add_issue("BLOCK", "INVALID_JSON", str(exc))
        report["status"] = "BLOCK"
        return report

    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        add_issue("BLOCK", "INVALID_PAGES", "JSON tidak memiliki daftar pages yang valid.")
        report["status"] = "BLOCK"
        return report

    page_numbers = []
    item_counts = Counter()
    total_items = 0
    table_count = 0
    image_count = 0
    table_by_page = defaultdict(int)

    for page_index, page in enumerate(pages):
        page_no = page.get("page_number", page_index + 1)
        page_numbers.append(page_no)
        items = page.get("items", [])

        if page.get("success") is False:
            add_issue("BLOCK", "PAGE_FAILED", "Ekstraksi halaman gagal.", page_no)

        if not isinstance(items, list):
            add_issue("BLOCK", "INVALID_ITEMS", "Format items bukan list.", page_no)
            continue

        meaningful_items = 0

        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                add_issue("WARNING", "INVALID_ITEM", "Item bukan objek JSON.", page_no, item_index)
                continue

            kind = item.get("type", "unknown")
            item_counts[kind] += 1
            total_items += 1

            content = item.get("md") or item.get("text") or item.get("value")
            if content or item.get("rows"):
                meaningful_items += 1

            if kind == "table":
                table_count += 1
                table_by_page[page_no] += 1
                rows = item.get("rows") or []

                if not rows and item.get("merged_into_page") is not None:
                    add_issue(
                        "INFO", "EMPTY_MERGED_PLACEHOLDER",
                        "Tabel kosong merupakan placeholder yang digabung ke halaman lain.",
                        page_no, item_index
                    )
                    continue

                if not rows and not item.get("md") and not item.get("html"):
                    add_issue(
                        "BLOCK", "EMPTY_TABLE",
                        "Tabel tidak memiliki isi dan tidak memiliki metadata merge.",
                        page_no, item_index
                    )
                    continue

                row_lengths = []
                for row in rows:
                    if isinstance(row, list):
                        row_lengths.append(len(row))
                    elif isinstance(row, dict):
                        row_lengths.append(len(row))

                if len(set(row_lengths)) > 1:
                    add_issue(
                        "WARNING", "INCONSISTENT_TABLE_ROWS",
                        f"Panjang baris tabel tidak konsisten: {row_lengths}",
                        page_no, item_index
                    )

            if kind == "image":
                image_count += 1
                bbox_data = item.get("bbox") or []
                bbox = bbox_data[0] if isinstance(bbox_data, list) and bbox_data else bbox_data
                width = bbox.get("w", bbox.get("width", 0)) if isinstance(bbox, dict) else 0
                height = bbox.get("h", bbox.get("height", 0)) if isinstance(bbox, dict) else 0
                caption = item.get("caption") or item.get("md")
                if not caption:
                    severity = "WARNING" if width >= 80 and height >= 50 else "INFO"
                    add_issue(
                        severity, "IMAGE_WITHOUT_CAPTION",
                        "Gambar tidak memiliki caption atau Markdown.",
                        page_no, item_index
                    )

            for concern in item.get("parse_concerns") or []:
                concern_text = (
                    concern.get("type", str(concern))
                    if isinstance(concern, dict) else str(concern)
                )
                if "multi_table_page" in concern_text:
                    severity = "INFO"
                else:
                    severity = "WARNING"

                add_issue(
                    severity, concern_text,
                    "LlamaParse melaporkan parse concern.",
                    page_no, item_index
                )

        if meaningful_items == 0:
            add_issue(
                "BLOCK", "EMPTY_PAGE",
                "Halaman tidak memiliki konten yang dapat diproses.",
                page_no
            )

        report["pages"].append({
            "page_number": page_no,
            "item_count": len(items),
            "meaningful_item_count": meaningful_items,
            "success": page.get("success")
        })

    if len(page_numbers) != len(set(page_numbers)):
        add_issue("BLOCK", "DUPLICATE_PAGE_NUMBER", "Terdapat nomor halaman duplikat.")

    if page_numbers:
        expected = set(range(min(page_numbers), max(page_numbers) + 1))
        missing = sorted(expected - set(page_numbers))
        if missing:
            add_issue("WARNING", "MISSING_PAGE_NUMBER", f"Nomor halaman hilang: {missing}")

    report["summary"] = {
        "total_pages": len(pages),
        "total_items": total_items,
        "item_types": dict(item_counts),
        "tables": table_count,
        "images": image_count
    }

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Validator hasil ekstraksi LlamaParse."
    )
    parser.add_argument("--json", required=True, help="Path JSON LlamaParse")
    parser.add_argument("--markdown", help="Path Markdown hasil ekstraksi")
    parser.add_argument("--out", help="Path laporan JSON")
    parser.add_argument("--document-id", help="ID dokumen")

    args = parser.parse_args()
    json_path = Path(args.json)

    if not json_path.exists():
        parser.error(f"File tidak ditemukan: {json_path}")

    report = classify_json(json_path)
    report["document_id"] = args.document_id or json_path.stem

    if args.markdown:
        md_path = Path(args.markdown)
        if not md_path.exists():
            report["issues"].append({
                "severity": "WARNING",
                "code": "MARKDOWN_NOT_FOUND",
                "message": f"Markdown tidak ditemukan: {md_path}"
            })
        else:
            markdown = md_path.read_text(encoding="utf-8")
            dollar_count = markdown.count("$$")
            report["markdown"] = {
                "path": str(md_path),
                "characters": len(markdown),
                "lines": len(markdown.splitlines()),
                "html_tables": markdown.count("<table"),
                "image_references": markdown.count("!["),
                "display_math_delimiters": dollar_count
            }
            if dollar_count % 2 != 0:
                report["issues"].append({
                    "severity": "WARNING",
                    "code": "ODD_MATH_DELIMITERS",
                    "message": f"Jumlah delimiter $$ ganjil: {dollar_count}"
                })

    severities = [issue["severity"] for issue in report["issues"]]
    if "BLOCK" in severities:
        report["status"] = "BLOCK"
    elif "WARNING" in severities:
        report["status"] = "WARNING"
    else:
        report["status"] = "PASS"

    output = Path(args.out) if args.out else (
        Path("data/validation") / f"{report['document_id']}_llamaparse_report.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("\n=== LLAMAPARSE VALIDATION ===")
    print(f"Dokumen : {report['document_id']}")
    print(f"Status  : {report['status']}")
    print(f"Halaman : {report['summary'].get('total_pages', 0)}")
    print(f"Item    : {report['summary'].get('total_items', 0)}")
    print(f"Tabel   : {report['summary'].get('tables', 0)}")
    print(f"Gambar  : {report['summary'].get('images', 0)}")
    print(f"Anomali : {len(report['issues'])}")

    for issue in report["issues"]:
        print(
            f"[{issue['severity']}] {issue['code']} "
            f"(halaman {issue.get('page')})"
        )

    print(f"\nLaporan disimpan: {output}")


if __name__ == "__main__":
    main()

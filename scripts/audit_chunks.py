#!/usr/bin/env python3
"""
scripts/audit_chunks.py
Audit all 43 chunks:
- chunk_id
- current content_type
- count of $$ formula blocks
- has_table (boolean and character count)
- has_image / figure description (boolean and character count)
- text characters
- should_type (Rule: "formula" ONLY if $$ blocks dominate chunk; "figure" if figure/desc dominates; "table" if table dominates; otherwise "text")
- first paragraph check (does it match its section?)
"""

import json
import re
from pathlib import Path

CHUNKS_PATH = Path("data/chunks/furniture_arrangement_ieq_2023_chunks.jsonl")
chunks = [json.loads(line) for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]

print(f"Total chunks: {len(chunks)}")
print()

table_header = "| chunk_id | Saat Ini | Blok $$ | Ada Tabel | Ada Gambar | Text/Form/Tbl/Fig | Seharusnya | Cocok? |"
sep = "| :--- | :--- | :---: | :---: | :---: | :---: | :--- | :---: |"
print(table_header)
print(sep)

audit_results = []
section_bleed_issues = []

for c in chunks:
    cid = c["chunk_id"]
    curr_type = c.get("content_type", "text")
    cont = c["content"]
    sec = c.get("section", "")
    hpath = c.get("heading_path", "")
    page = c.get("page_number", 0)

    # Formula analysis
    formula_blocks = re.findall(r"\$\$.*?\$\$", cont, re.DOTALL)
    num_formulas = len(formula_blocks)
    form_chars = sum(len(f) for f in formula_blocks)

    # Table analysis
    table_lines = [l for l in cont.splitlines() if l.strip().startswith("|")]
    has_table = len(table_lines) > 0
    tbl_chars = sum(len(l) for l in table_lines)

    # Figure analysis
    has_image = bool(c.get("image_path")) or "![" in cont
    fig_desc = "> **Deskripsi gambar:**" in cont
    has_fig = has_image or fig_desc

    fig_lines = []
    in_desc = False
    for l in cont.splitlines():
        if l.strip().startswith("!["):
            fig_lines.append(l)
        elif "> **Deskripsi gambar:**" in l:
            in_desc = True
            fig_lines.append(l)
        elif in_desc:
            if l.strip().startswith(">"):
                fig_lines.append(l)
            elif not l.strip():
                in_desc = False
    fig_chars = sum(len(l) for l in fig_lines)

    # Body without Document / Section header
    body = cont
    if "Section:" in cont:
        parts = cont.split("Section:", 1)[1]
        if "\n\n" in parts:
            body = parts.split("\n\n", 1)[1]

    total_body_len = len(body.strip())
    text_chars = max(0, total_body_len - form_chars - tbl_chars - fig_chars)

    # Correct label rule:
    # "formula" ONLY if $$ blocks dominate
    # "figure" if figure lines dominate non-text
    # "table" if table lines dominate non-text
    # "text" if narrative text dominates or no special elements
    scores = {
        "text": text_chars,
        "formula": form_chars,
        "table": tbl_chars,
        "figure": fig_chars
    }

    # If pure text
    if form_chars == 0 and tbl_chars == 0 and fig_chars == 0:
        should_type = "text"
    else:
        # User rule: "formula hanya jika blok $$ mendominasi chunk"
        # Let's check non-text elements vs text
        # If formula > text and formula >= table and formula >= figure: formula
        # If table > text and table >= formula and table >= figure: table
        # If figure > text and figure >= formula and figure >= table: figure
        # But wait! If a chunk is primarily a Table or Figure with a caption / brief intro:
        # e.g., table test data or figure crop + description
        dominant = max(scores, key=scores.get)
        # What if text is 55% and table is 45% because of long paragraph before table?
        # Let's see dominant
        should_type = dominant

    match = (curr_type == should_type)
    match_icon = "✅" if match else "❌"

    prop_str = f"{text_chars}/{form_chars}/{tbl_chars}/{fig_chars}"
    tbl_str = "Ya" if has_table else "Tdk"
    fig_str = "Ya" if has_fig else "Tdk"

    print(f"| {cid} | {curr_type} | {num_formulas} | {tbl_str} | {fig_str} | {prop_str} | {should_type} | {match_icon} |")

    first_para = body.strip().split("\n\n")[0] if body.strip() else ""
    audit_results.append({
        "chunk_id": cid,
        "current_type": curr_type,
        "should_type": should_type,
        "match": match,
        "num_formulas": num_formulas,
        "form_chars": form_chars,
        "tbl_chars": tbl_chars,
        "fig_chars": fig_chars,
        "text_chars": text_chars,
        "section": sec,
        "heading_path": hpath,
        "page_number": page,
        "first_para": first_para,
    })

    # Check for section bleed:
    # 1. First para mentions another section or figure from earlier section
    # 2. Or chunk has content from earlier section
    first_para_lower = first_para.lower()
    if "section" in first_para_lower or "fig." in first_para_lower or "table" in first_para_lower or "nilai berkisar" in first_para_lower:
        # check if it contradicts heading
        pass

print()
mismatches = [a for a in audit_results if not a["match"]]
print(f"Total Mismatches: {len(mismatches)}")
for m in mismatches:
    print(f"  {m['chunk_id']}: current={m['current_type']} -> should={m['should_type']} (text={m['text_chars']}, form={m['form_chars']}, tbl={m['tbl_chars']}, fig={m['fig_chars']}) | {m['heading_path']}")

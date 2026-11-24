#!/usr/bin/env python3
"""
eval/run_eval_tahap4c.py
1. Run 4 regression questions (Tahap 3C: Bellman, execution time, recipe, spawn_furniture)
2. Run Mode 2 for Q19, Q21-Q26 (timeout 90s) under updated system_prompt
3. Output results to eval/results_tahap4c.json
"""

import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
import httpx
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR / ".env", override=True)

STATE_DB_PATH = Path("/home/advance/.hermes/state.db")
QUESTIONS_PATH = BASE_DIR / "eval" / "questions.json"
RESULTS_PATH = BASE_DIR / "eval" / "results_tahap4c.json"
CHAT_ENDPOINT = "http://127.0.0.1:8000/api/chat"

REGRESSION_QUERIES = [
    ("a", "Apa itu persamaan Bellman di paper ini?"),
    ("b", "Berapa waktu eksekusi NSGA-II dan MORL pada Test 5?"),
    ("c", "Apa resep nasi goreng?"),
    ("d", "Taruh meja di lantai")
]

TARGET_QIDS = ["Q19", "Q21", "Q22", "Q23", "Q24", "Q25", "Q26"]


def get_latest_message_id():
    if not STATE_DB_PATH.exists():
        return 0
    con = sqlite3.connect(STATE_DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT MAX(id) FROM messages")
    row = cur.fetchone()
    con.close()
    return row[0] or 0


def fetch_new_messages(since_id):
    if not STATE_DB_PATH.exists():
        return []
    con = sqlite3.connect(STATE_DB_PATH)
    cur = con.cursor()
    cur.execute(
        "SELECT id, role, tool_calls, content, tool_name FROM messages WHERE id > ? ORDER BY id ASC",
        (since_id,),
    )
    rows = cur.fetchall()
    con.close()
    return rows


def extract_tool_activity(messages_rows):
    tools_called = []
    meta_tools = []
    for r in messages_rows:
        tc_json = r[2]
        if not tc_json:
            continue
        try:
            items = json.loads(tc_json)
            for it in items:
                func = it.get("function", {})
                fname = func.get("name", "")
                fargs_raw = func.get("arguments", "{}")
                try:
                    fargs = json.loads(fargs_raw)
                except Exception:
                    fargs = fargs_raw

                if fname == "tool_call" and isinstance(fargs, dict) and "calls" in fargs:
                    for call in fargs.get("calls", []):
                        tools_called.append({
                            "tool": call.get("name"),
                            "arguments": call.get("arguments"),
                        })
                elif fname in ["tool_search", "tool_describe"]:
                    meta_tools.append({
                        "meta_tool": fname,
                        "arguments": fargs,
                    })
                elif "search_documents" in fname or "spawn_furniture" in fname or "get_chunk" in fname or "get_page_context" in fname:
                    tools_called.append({
                        "tool": fname,
                        "arguments": fargs,
                    })
        except Exception as e:
            print(f"Error parsing tool_calls: {e}")
    return tools_called, meta_tools


def run_regression_tests():
    print("==================================================")
    print("STEP 1: TAHAP 3C REGRESSION TESTS (4 QUERIES)")
    print("==================================================")
    results = []
    for label, prompt in REGRESSION_QUERIES:
        print(f"\n--- Testing ({label}): '{prompt}' ---")
        since_id = get_latest_message_id()
        t0 = time.time()
        try:
            with httpx.Client(timeout=90.0) as client:
                res = client.post(
                    CHAT_ENDPOINT,
                    headers={"Content-Type": "application/json"},
                    json={"prompt": prompt},
                )
            dur = round(time.time() - t0, 2)
            res.raise_for_status()
            res_json = res.json()
            resp = res_json.get("response", "")
        except Exception as exc:
            dur = round(time.time() - t0, 2)
            resp = f"ERROR: {exc}"

        new_msgs = fetch_new_messages(since_id)
        tools_called, meta_tools = extract_tool_activity(new_msgs)

        print(f"  Duration: {dur}s")
        print(f"  Tools called: {[tc.get('tool') for tc in tools_called]}")
        print(f"  Response preview: {resp[:120]}...")

        results.append({
            "label": label,
            "prompt": prompt,
            "duration": dur,
            "tools_called": tools_called,
            "response": resp,
        })
    return results


def run_target_eval():
    print("\n==================================================")
    print("STEP 2: RUNNING MODE 2 FOR Q19 & Q21-Q26 (TIMEOUT 90s)")
    print("==================================================")
    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
        questions = json.load(f)
    q_map = {q["id"]: q for q in questions}

    results = []
    for qid in TARGET_QIDS:
        q = q_map.get(qid)
        if not q:
            continue

        prompt = q["question"]
        print(f"\n[{qid}] ({q['type']}, {q['language']}) Prompt: '{prompt}'")
        since_id = get_latest_message_id()
        t0 = time.time()

        try:
            with httpx.Client(timeout=90.0) as client:
                res = client.post(
                    CHAT_ENDPOINT,
                    headers={"Content-Type": "application/json"},
                    json={"prompt": prompt},
                )
            dur = round(time.time() - t0, 2)
            res.raise_for_status()
            res_json = res.json()
            resp = res_json.get("response", "")
        except Exception as exc:
            dur = round(time.time() - t0, 2)
            resp = f"ERROR: {exc}"

        new_msgs = fetch_new_messages(since_id)
        tools_called, meta_tools = extract_tool_activity(new_msgs)

        citations = re.findall(r"\[(?:Hal\.|Page|Pages|p\.|Sumber)[^\]]+\]", resp, re.IGNORECASE)

        agent_queries = []
        for tc in tools_called:
            args = tc.get("arguments")
            if isinstance(args, dict) and "query" in args:
                agent_queries.append(args["query"])

        print(f"  Duration: {dur}s")
        print(f"  Tools called: {[tc.get('tool') for tc in tools_called]}")
        print(f"  Agent queries: {agent_queries}")
        print(f"  Citations: {citations}")
        print(f"  Response: {resp[:140]}...")

        results.append({
            "id": qid,
            "type": q["type"],
            "language": q["language"],
            "question": prompt,
            "expected_answer": q["expected_answer"],
            "expected_chunk_ids": q.get("expected_chunk_ids", []),
            "elapsed_seconds": dur,
            "tools_called": tools_called,
            "agent_queries": agent_queries,
            "citations": citations,
            "full_response": resp,
            "needs_manual_check": True,
        })
    return results


def main():
    regression_res = run_regression_tests()
    target_res = run_target_eval()

    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "regression_tahap3c": regression_res,
        "mode2_tahap4c": target_res,
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved all results to {RESULTS_PATH}")


if __name__ == "__main__":
    main()

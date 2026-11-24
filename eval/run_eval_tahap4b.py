#!/usr/bin/env python3
"""
eval/run_eval_tahap4b.py
Execution script for Tahap 4B:
1. Run Mode 2 (agent /api/chat with timeout 90s) for Q19 and Q21-Q26.
2. Capture agent-generated query, response, citations, tools called, elapsed time.
3. Feed agent-generated queries into Mode 1 (search_documents) for Q21-Q26.
4. Record all metrics without automatic correct/incorrect scoring.
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
import mcp_server

STATE_DB_PATH = Path("/home/advance/.hermes/state.db")
QUESTIONS_PATH = BASE_DIR / "eval" / "questions.json"
RESULTS_PATH = BASE_DIR / "eval" / "results_tahap4b.json"
CHAT_ENDPOINT = "http://127.0.0.1:8000/api/chat"

TARGET_QIDS = ["Q19", "Q21", "Q22", "Q23", "Q24", "Q25", "Q26"]


def load_questions():
    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


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


def main():
    questions = load_questions()
    q_map = {q["id"]: q for q in questions}

    print("==================================================")
    print("TAHAP 4B: RUNNING MODE 2 FOR Q19 AND Q21-Q26 (TIMEOUT 90s)")
    print("==================================================")

    mode2_results = []

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
            elapsed = round(time.time() - t0, 2)
            res.raise_for_status()
            res_json = res.json()
            response_text = res_json.get("response", "")
        except Exception as exc:
            elapsed = round(time.time() - t0, 2)
            print(f"  Error calling /api/chat: {exc}")
            response_text = f"ERROR: {exc}"

        new_msgs = fetch_new_messages(since_id)
        tools_called, meta_tools = extract_tool_activity(new_msgs)

        citations = re.findall(r"\[(?:Hal\.|Page|Pages|p\.|Sumber)[^\]]+\]", response_text, re.IGNORECASE)

        # Extract agent-generated query
        agent_queries = []
        for tc in tools_called:
            args = tc.get("arguments")
            if isinstance(args, dict) and "query" in args:
                agent_queries.append(args["query"])

        primary_query = agent_queries[0] if agent_queries else ""

        print(f"  Elapsed: {elapsed}s")
        print(f"  Tools called: {[tc.get('tool') for tc in tools_called]}")
        print(f"  Agent queries: {agent_queries}")
        print(f"  Citations: {citations}")
        print(f"  Response: {response_text[:140]}...")

        # If it's Q21-Q26, store primary_query back into q_map
        if qid in ["Q21", "Q22", "Q23", "Q24", "Q25", "Q26"] and primary_query:
            q["query_en"] = primary_query

        mode2_results.append({
            "id": qid,
            "type": q["type"],
            "language": q["language"],
            "question": prompt,
            "expected_answer": q["expected_answer"],
            "expected_chunk_ids": q.get("expected_chunk_ids", []),
            "elapsed_seconds": elapsed,
            "tools_called": tools_called,
            "agent_queries": agent_queries,
            "primary_query": primary_query,
            "citations": citations,
            "full_response": response_text,
            "needs_manual_check": True,
        })

    # Save updated queries in questions.json
    with open(QUESTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(questions, f, indent=2, ensure_ascii=False)

    print("\n==================================================")
    print("TAHAP 4B: RUNNING MODE 1 DIRECT RETRIEVAL FOR Q21-Q26 (AGENT QUERIES)")
    print("==================================================")

    mode1_results = []
    for qid in ["Q21", "Q22", "Q23", "Q24", "Q25", "Q26"]:
        q = q_map.get(qid)
        query = q.get("query_en")
        expected_cids = q.get("expected_chunk_ids", [])
        print(f"\n[{qid}] Query from agent: '{query}'")

        if not query:
            print("  Warning: No agent query generated.")
            mode1_results.append({
                "id": qid,
                "query": "",
                "status": "no_query",
                "retrieved_chunk_ids": [],
                "target_rank": None,
                "hit@1": 0,
                "hit@3": 0,
                "hit@5": 0,
                "mrr": 0.0,
                "recall@5": 0.0,
            })
            continue

        ret = mcp_server.search_documents(query=query, top_k=5)
        status = ret.get("status")
        ret_results = ret.get("results", [])
        retrieved_cids = [r["chunk_id"] for r in ret_results]

        found = [cid for cid in expected_cids if cid in retrieved_cids]
        recall_at_5 = len(found) / len(expected_cids) if expected_cids else 0.0

        target_rank = None
        for idx, cid in enumerate(retrieved_cids, start=1):
            if cid in expected_cids:
                target_rank = idx
                break

        hit_1 = 1 if target_rank == 1 else 0
        hit_3 = 1 if (target_rank and target_rank <= 3) else 0
        hit_5 = 1 if (target_rank and target_rank <= 5) else 0
        mrr = round(1.0 / target_rank, 4) if target_rank else 0.0

        print(f"  Status: {status}")
        print(f"  Top 5: {retrieved_cids}")
        print(f"  Expected: {expected_cids}")
        print(f"  Found in top 5: {found} -> Target Rank: {target_rank}, Recall@5: {recall_at_5:.2f}, Hit@1: {hit_1}, Hit@3: {hit_3}, Hit@5: {hit_5}")

        mode1_results.append({
            "id": qid,
            "type": q["type"],
            "language": q["language"],
            "question": q["question"],
            "agent_query": query,
            "expected_chunk_ids": expected_cids,
            "status": status,
            "retrieved_chunk_ids": retrieved_cids,
            "retrieved_results": [
                {
                    "chunk_id": r["chunk_id"],
                    "page_number": r["page_number"],
                    "similarity": round(r["similarity"], 4),
                    "fts_rank": round(r["fts_rank"], 4),
                    "rrf_score": round(r["rrf_score"], 6),
                }
                for r in ret_results
            ],
            "target_rank": target_rank,
            "hit@1": hit_1,
            "hit@3": hit_3,
            "hit@5": hit_5,
            "mrr": mrr,
            "recall@5": round(recall_at_5, 4),
            "found_expected_in_top5": found,
            "needs_manual_check": True,
        })

    # Save output data
    output_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode2_agent_chat": mode2_results,
        "mode1_retrieval_agent_queries": mode1_results,
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\nResults successfully written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()

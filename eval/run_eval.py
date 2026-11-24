#!/usr/bin/env python3
"""
eval/run_eval.py
Evaluation script for RAG & Agentic AI (Mixed Reality / FastMCP / Hermes Agent / FastAPI DSS)
Mode 1: Direct retrieval evaluation on all 20 questions (eval/questions.json)
Mode 2: End-to-end agent evaluation on 10 selected questions via POST /api/chat
Output: eval/results.json
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

# Ensure backend root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR / ".env", override=True)
import mcp_server

STATE_DB_PATH = Path("/home/advance/.hermes/state.db")
QUESTIONS_PATH = BASE_DIR / "eval" / "questions.json"
RESULTS_PATH = BASE_DIR / "eval" / "results.json"
CHAT_ENDPOINT = "http://127.0.0.1:8000/api/chat"

MODE2_SELECTED_QIDS = [
    "Q01",  # text, en
    "Q02",  # text, id
    "Q06",  # table, id
    "Q07",  # table, en
    "Q11",  # figure, en
    "Q12",  # figure, id
    "Q14",  # formula, id
    "Q17",  # out_of_domain, id
    "Q18",  # out_of_domain_near, id
    "Q19",  # cross_section, id
]


def load_questions():
    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run_mode_1(questions):
    print("\n==========================================")
    print("RUNNING MODE 1: DIRECT RETRIEVAL EVALUATION")
    print("==========================================")
    results = []

    for q in questions:
        qid = q["id"]
        q_type = q.get("type")
        lang = q.get("language")
        query_en = q.get("query_en")
        expected_cids = q.get("expected_chunk_ids", [])

        print(f"\n[{qid}] ({q_type}, {lang}) Query: '{query_en}'")
        ret = mcp_server.search_documents(query=query_en, top_k=5)
        status = ret.get("status")
        ret_results = ret.get("results", [])
        retrieved_cids = [r["chunk_id"] for r in ret_results]

        hit_1 = 0
        hit_3 = 0
        hit_5 = 0
        mrr = 0.0
        first_target_rank = None
        recall_at_5 = None

        if q_type in ["out_of_domain", "out_of_domain_near"]:
            is_no_relevant = (status == "no_relevant_result")
            print(f"  -> Out-of-Domain. Status: {status} (Expected no_relevant_result: {is_no_relevant})")
            results.append({
                "id": qid,
                "type": q_type,
                "language": lang,
                "question": q["question"],
                "query_en": query_en,
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
                "hit@1": None,
                "hit@3": None,
                "hit@5": None,
                "mrr": None,
                "first_target_rank": None,
                "recall@5": None,
                "is_no_relevant": is_no_relevant,
            })
        elif q_type == "cross_section":
            found = [cid for cid in expected_cids if cid in retrieved_cids]
            recall_at_5 = len(found) / len(expected_cids) if expected_cids else 0.0
            for idx, cid in enumerate(retrieved_cids, start=1):
                if cid in expected_cids:
                    first_target_rank = idx
                    break

            if first_target_rank is not None:
                if first_target_rank == 1:
                    hit_1 = 1
                if first_target_rank <= 3:
                    hit_3 = 1
                if first_target_rank <= 5:
                    hit_5 = 1
                mrr = round(1.0 / first_target_rank, 4)

            is_false_no_relevant = (status == "no_relevant_result")
            print(f"  -> Cross-section. Found: {found}/{expected_cids}. Recall@5: {recall_at_5:.2f}. Rank: {first_target_rank}")
            results.append({
                "id": qid,
                "type": q_type,
                "language": lang,
                "question": q["question"],
                "query_en": query_en,
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
                "hit@1": hit_1,
                "hit@3": hit_3,
                "hit@5": hit_5,
                "mrr": mrr,
                "first_target_rank": first_target_rank,
                "recall@5": round(recall_at_5, 4),
                "found_expected_in_top5": found,
                "is_false_no_relevant": is_false_no_relevant,
            })
        else:
            # Standard in-domain
            for idx, cid in enumerate(retrieved_cids, start=1):
                if cid in expected_cids:
                    first_target_rank = idx
                    break

            if first_target_rank is not None:
                if first_target_rank == 1:
                    hit_1 = 1
                if first_target_rank <= 3:
                    hit_3 = 1
                if first_target_rank <= 5:
                    hit_5 = 1
                mrr = round(1.0 / first_target_rank, 4)

            is_false_no_relevant = (status == "no_relevant_result")
            print(f"  -> In-domain. Top 5: {retrieved_cids}. Target rank: {first_target_rank}. Hit@1: {hit_1}, Hit@3: {hit_3}, Hit@5: {hit_5}")
            results.append({
                "id": qid,
                "type": q_type,
                "language": lang,
                "question": q["question"],
                "query_en": query_en,
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
                "hit@1": hit_1,
                "hit@3": hit_3,
                "hit@5": hit_5,
                "mrr": mrr,
                "first_target_rank": first_target_rank,
                "recall@5": 1.0 if hit_5 == 1 else 0.0,
                "is_false_no_relevant": is_false_no_relevant,
            })

    return results


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


def run_mode_2(questions):
    print("\n==========================================")
    print("RUNNING MODE 2: AGENT EVALUATION (/api/chat)")
    print("==========================================")

    q_map = {q["id"]: q for q in questions}
    agent_results = []

    for qid in MODE2_SELECTED_QIDS:
        q = q_map.get(qid)
        if not q:
            continue

        prompt = q["question"]
        print(f"\n[{qid}] ({q['type']}, {q['language']}) Prompt: '{prompt}'")

        since_id = get_latest_message_id()
        start_t = time.time()

        try:
            with httpx.Client(timeout=180.0) as client:
                res = client.post(
                    CHAT_ENDPOINT,
                    headers={"Content-Type": "application/json"},
                    json={"prompt": prompt},
                )
            elapsed = round(time.time() - start_t, 2)
            res.raise_for_status()
            res_json = res.json()
            response_text = res_json.get("response", "")
        except Exception as exc:
            elapsed = round(time.time() - start_t, 2)
            print(f"  Error calling /api/chat: {exc}")
            response_text = f"ERROR: {exc}"

        # Fetch messages from state.db
        new_msgs = fetch_new_messages(since_id)
        tools_called, meta_tools = extract_tool_activity(new_msgs)

        # Extract citations
        citations = re.findall(r"\[(?:Hal\.|Page|Pages)[^\]]+\]", response_text, re.IGNORECASE)

        # Extract translated query
        query_arg = None
        for tc in tools_called:
            args = tc.get("arguments")
            if isinstance(args, dict) and "query" in args:
                query_arg = args["query"]
                break

        print(f"  Elapsed: {elapsed}s")
        print(f"  Tools called: {[tc.get('tool') for tc in tools_called]}")
        if query_arg:
            print(f"  Query arg: '{query_arg}'")
        print(f"  Citations: {citations}")
        print(f"  Response preview: {response_text[:120]}...")

        agent_results.append({
            "id": qid,
            "type": q["type"],
            "language": q["language"],
            "question": prompt,
            "expected_answer": q["expected_answer"],
            "expected_chunk_ids": q.get("expected_chunk_ids", []),
            "elapsed_seconds": elapsed,
            "tools_called": tools_called,
            "meta_tools": meta_tools,
            "query_argument": query_arg,
            "citations": citations,
            "full_response": response_text,
        })

    return agent_results


def summarize_mode_1(mode1_results):
    summary_by_type = {}
    types = ["text", "table", "figure", "formula", "out_of_domain", "out_of_domain_near", "cross_section"]

    for t in types:
        items = [r for r in mode1_results if r["type"] == t]
        if not items:
            continue

        n = len(items)
        if t in ["out_of_domain", "out_of_domain_near"]:
            no_rel_count = sum(1 for r in items if r["is_no_relevant"])
            summary_by_type[t] = {
                "count": n,
                "no_relevant_result_count": no_rel_count,
                "accuracy": round(no_rel_count / n, 4),
            }
        elif t == "cross_section":
            avg_hit1 = sum(r["hit@1"] for r in items) / n
            avg_hit3 = sum(r["hit@3"] for r in items) / n
            avg_hit5 = sum(r["hit@5"] for r in items) / n
            avg_mrr = sum(r["mrr"] for r in items) / n
            avg_recall5 = sum(r["recall@5"] for r in items) / n
            summary_by_type[t] = {
                "count": n,
                "hit@1": round(avg_hit1, 4),
                "hit@3": round(avg_hit3, 4),
                "hit@5": round(avg_hit5, 4),
                "mrr": round(avg_mrr, 4),
                "avg_recall@5": round(avg_recall5, 4),
            }
        else:
            avg_hit1 = sum(r["hit@1"] for r in items) / n
            avg_hit3 = sum(r["hit@3"] for r in items) / n
            avg_hit5 = sum(r["hit@5"] for r in items) / n
            avg_mrr = sum(r["mrr"] for r in items) / n
            summary_by_type[t] = {
                "count": n,
                "hit@1": round(avg_hit1, 4),
                "hit@3": round(avg_hit3, 4),
                "hit@5": round(avg_hit5, 4),
                "mrr": round(avg_mrr, 4),
            }

    # In-domain standard aggregate (text, table, figure, formula -> 16 questions)
    in_domain_items = [r for r in mode1_results if r["type"] in ["text", "table", "figure", "formula"]]
    n_in = len(in_domain_items)
    overall_in_domain = {
        "count": n_in,
        "hit@1": round(sum(r["hit@1"] for r in in_domain_items) / n_in, 4),
        "hit@3": round(sum(r["hit@3"] for r in in_domain_items) / n_in, 4),
        "hit@5": round(sum(r["hit@5"] for r in in_domain_items) / n_in, 4),
        "mrr": round(sum(r["mrr"] for r in in_domain_items) / n_in, 4),
        "false_no_relevant_count": sum(1 for r in in_domain_items if r["is_false_no_relevant"]),
    }

    return summary_by_type, overall_in_domain


def main():
    questions = load_questions()
    print(f"Loaded {len(questions)} evaluation questions from {QUESTIONS_PATH}")

    # Mode 1
    mode1_results = run_mode_1(questions)
    summary_by_type, overall_in_domain = summarize_mode_1(mode1_results)

    # Mode 2
    mode2_results = run_mode_2(questions)

    # Compile final JSON
    output_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_questions": len(questions),
        "mode1_direct_retrieval": {
            "summary_overall_in_domain": overall_in_domain,
            "summary_by_type": summary_by_type,
            "items": mode1_results,
        },
        "mode2_agent_chat": {
            "selected_questions_count": len(mode2_results),
            "items": mode2_results,
        },
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print("\n==========================================")
    print(f"EVALUATION COMPLETE. Results saved to {RESULTS_PATH}")
    print("==========================================")
    print("In-domain retrieval summary:")
    print(json.dumps(overall_in_domain, indent=2))
    print("Summary by type:")
    print(json.dumps(summary_by_type, indent=2))


if __name__ == "__main__":
    main()

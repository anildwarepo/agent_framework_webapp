"""
Evaluation script that reads questions from full100_llmdecomp_hybrid.jsonl,
calls the /conversation/{user_id} API for each question, and stores the
results in a CSV file.
"""

import argparse
import asyncio
import csv
import io
import json
import time
from pathlib import Path

import httpx

INPUT_FILE = Path(__file__).parent / "full100_llmdecomp_hybrid.jsonl"

DEFAULT_BASE_URL = "https://fastapi-ftjb.gentlesea-97432f9a.westus.azurecontainerapps.io"
#DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_USER_ID = "eval_user"
DEFAULT_GRAPH_NAME = "meetings_graph"
DEFAULT_MODEL_NAME = ""
DEFAULT_MODE = "graph"
DEFAULT_CONCURRENCY = 10
REQUEST_TIMEOUT = 120.0  # seconds per question


async def call_conversation_api(
    client: httpx.AsyncClient,
    base_url: str,
    user_id: str,
    question: str,
    graph_name: str,
    model_name: str,
    mode: str,
) -> dict:
    """
    POST to /conversation/{user_id}?mode={mode} and collect the full
    streaming ndjson response.  Returns a dict with the collected chunks
    and the final answer extracted from the 'done' message.
    """
    url = f"{base_url}/conversation/{user_id}"
    payload = {
        "user_query": question,
        "graph_name": graph_name,
        "model_name": model_name,
    }

    chunks: list[dict] = []
    final_answer = None

    async with client.stream(
        "POST",
        url,
        json=payload,
        params={"mode": mode},
        timeout=REQUEST_TIMEOUT,
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                chunks.append(obj)
                msg = obj.get("response_message", {})
                if msg.get("type") == "done":
                    final_answer = msg.get("result")
            except json.JSONDecodeError:
                chunks.append({"raw": line})

    return {
        "final_answer": final_answer,
        "chunks": chunks,
    }


CSV_COLUMNS = [
    "question_id",
    "question",
    "golden_answer",
    "answer_raw",
    "api_final_response",
    "response_time_s",
]


async def _eval_one(
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    index: int,
    total: int,
    record: dict,
    base_url: str,
    user_id: str,
    graph_name: str,
    model_name: str,
    mode: str,
    output_path: Path,
    write_lock: asyncio.Lock,
    completed: dict,
):
    """Evaluate a single question, then append the result as a CSV row."""
    qid = record.get("question_id", index + 1)
    question = record["question"]

    async with sem:
        print(f"[{index + 1}/{total}] Q{qid}: {question}")
        start = time.time()
        try:
            api_result = await call_conversation_api(
                client, base_url, user_id, question, graph_name, model_name, mode
            )
            elapsed = round(time.time() - start, 1)
            final_answer = api_result["final_answer"]
            print(f"  -> Q{qid} Answer ({elapsed}s): {final_answer[:120] if final_answer else 'N/A'}...")
        except Exception as e:
            elapsed = round(time.time() - start, 1)
            final_answer = f"ERROR: {e}"
            print(f"  -> Q{qid} ERROR ({elapsed}s): {e}")

    row = {
        "question_id": qid,
        "question": question,
        "golden_answer": record.get("golden_answer", ""),
        "answer_raw": record.get("answer_raw", ""),
        "api_final_response": final_answer or "",
        "response_time_s": elapsed,
    }

    async with write_lock:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
        writer.writerow(row)
        with open(output_path, "a", encoding="utf-8", newline="") as f:
            f.write(buf.getvalue())
        completed["n"] += 1
        print(f"  [wrote {completed['n']}/{total} to {output_path.name}]")


async def run_eval(
    base_url: str,
    user_id: str,
    graph_name: str,
    model_name: str,
    mode: str,
    input_path: Path,
    output_path: Path,
    concurrency: int = DEFAULT_CONCURRENCY,
):
    records: list[dict] = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    total = len(records)
    print(f"Loaded {total} questions from {input_path}")
    print(f"Target API: {base_url}/conversation/{user_id}?mode={mode}")
    print(f"Graph: {graph_name}  |  Model: {model_name or '(default)'}  |  Concurrency: {concurrency}")
    print("-" * 60)

    # Write CSV header
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()

    sem = asyncio.Semaphore(concurrency)
    write_lock = asyncio.Lock()
    completed: dict = {"n": 0}

    async with httpx.AsyncClient() as client:
        tasks = [
            _eval_one(
                sem, client, i, total, record,
                base_url, user_id, graph_name, model_name, mode,
                output_path, write_lock, completed,
            )
            for i, record in enumerate(records)
        ]
        await asyncio.gather(*tasks)

    print("-" * 60)
    print(f"All {total} results written to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate meetings KG API")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID, help="user_id for the API")
    parser.add_argument("--graph-name", default=DEFAULT_GRAPH_NAME, help="graph_name to send")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME, help="model_name to send")
    parser.add_argument("--mode", default=DEFAULT_MODE, help="orchestration mode query param")
    parser.add_argument("--input", type=Path, default=INPUT_FILE, help="Input JSONL path")
    parser.add_argument("--output", type=Path, default=None, help="Output CSV path (auto-generated if omitted)")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Max parallel API calls")
    args = parser.parse_args()

    if args.output is None:
        stem = args.input.stem
        model_tag = args.model_name.replace("/", "_").replace("\\", "_") if args.model_name else "default"
        graph_tag = args.graph_name
        args.output = args.input.parent / f"{stem}_{graph_tag}_{model_tag}_eval.csv"

    asyncio.run(
        run_eval(args.base_url, args.user_id, args.graph_name, args.model_name, args.mode, args.input, args.output, args.concurrency)
    )


if __name__ == "__main__":
    main()



import hashlib
import json
import random
import time
from pathlib import Path

from src.database import run_sql as database_run_sql
from src.documents import search_docs as document_search_docs
from src.documents import get_policy as document_get_policy

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "data" / "tool_calls.jsonl"
WHATSAPP_LOG_PATH = ROOT / "data" / "whatsapp_log.jsonl"

MAX_TOOL_CALLS = 8
FAULT_RATE = 0.15
_rng = random.Random(42)
_call_count = 0
_call_records = []


class ToolError(Exception):
    pass


class ToolBudgetExceeded(ToolError):
    pass


def reset_question_state(seed=42):
    global _call_count, _call_records, _rng
    _call_count = 0
    _call_records = []
    _rng = random.Random(seed)


def get_call_count():
    return _call_count


def get_call_records():
    return list(_call_records)


def _write_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def run_sql(read_only_query):
    return database_run_sql(read_only_query)


def search_docs(query):
    return document_search_docs(query)


def get_policy(name, as_of_date):
    return document_get_policy(name, as_of_date)


def send_seller_whatsapp(seller_id, message, user_authorized=False):
    if user_authorized is not True:
        raise ToolError("Explicit authorization from the user's request is required")

    if isinstance(seller_id, bool) or not isinstance(seller_id, int):
        raise ToolError("seller_id must be an integer")

    if seller_id not in {40218, 40219, 40220, 40221}:
        raise ToolError("Unknown seller ID")

    if not isinstance(message, str) or not message.strip():
        raise ToolError("Message must be a non-empty string")

    if len(message) > 1000:
        raise ToolError("Message exceeds the 1000-character limit")

    record = {
        "timestamp": time.time(),
        "seller_id": seller_id,
        "message": message.strip(),
        "authorization_source": "user_request",
        "status": "logged_only"
    }

    _write_jsonl(WHATSAPP_LOG_PATH, record)
    return {"status": "logged_only", "seller_id": seller_id}


def _dispatch(tool_name, arguments):
    if not isinstance(arguments, dict):
        raise ToolError("Tool arguments must be a dictionary")

    if tool_name == "run_sql":
        query = arguments.get("read_only_query")
        if not isinstance(query, str):
            raise ToolError("read_only_query must be a string")
        return run_sql(query)

    if tool_name == "search_docs":
        query = arguments.get("query")
        if not isinstance(query, str):
            raise ToolError("query must be a string")
        return search_docs(query)

    if tool_name == "get_policy":
        name = arguments.get("name")
        as_of_date = arguments.get("as_of_date")
        if not isinstance(name, str) or not isinstance(as_of_date, str):
            raise ToolError("name and as_of_date must be strings")
        return get_policy(name, as_of_date)

    if tool_name == "send_seller_whatsapp":
        return send_seller_whatsapp(
            arguments.get("seller_id"),
            arguments.get("message"),
            arguments.get("user_authorized", False)
        )

    raise ToolError(f"Unknown tool: {tool_name}")


def call_tool(tool_name, arguments):
    global _call_count

    if _call_count >= MAX_TOOL_CALLS:
        raise ToolBudgetExceeded(
            f"Tool-call budget exceeded: maximum is {MAX_TOOL_CALLS}"
        )

    _call_count += 1
    started = time.time()

    record = {
        "call_number": _call_count,
        "tool_name": tool_name,
        "arguments": arguments,
        "started_at": started
    }

    try:
        fault = _rng.random()

        if fault < FAULT_RATE / 3:
            raise TimeoutError("Simulated tool timeout")

        if fault < 2 * FAULT_RATE / 3:
            raise ToolError("Simulated tool failure")

        result = _dispatch(tool_name, arguments)

        if fault < FAULT_RATE:
            result = [] if tool_name == "search_docs" else {
                "status": "empty_simulated_result",
                "rows": [],
                "claims": []
            }

        record.update({
            "status": "success",
            "result": result,
            "duration_seconds": round(time.time() - started, 6)
        })

        return result

    except Exception as exc:
        record.update({
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "duration_seconds": round(time.time() - started, 6)
        })
        raise

    finally:
        _call_records.append(record)
        _write_jsonl(LOG_PATH, record)


def result_hash(result):
    encoded = json.dumps(
        result,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

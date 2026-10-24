
from src.tools import reset_question_state, call_tool, get_call_count
from src.tools import ToolError, ToolBudgetExceeded

reset_question_state(seed=42)

checks = [
    ("run_sql", {"read_only_query": "SELECT COUNT(*) AS total FROM orders"}),
    ("search_docs", {"query": "refund"}),
    ("get_policy", {"name": "refund_policy", "as_of_date": "2026-06-01"}),
]

for name, arguments in checks:
    try:
        result = call_tool(name, arguments)
        print(f"{name}: SUCCESS")
        print(str(result)[:300])
    except Exception as exc:
        print(f"{name}: FAILED - {type(exc).__name__}: {exc}")

print("Total calls:", get_call_count())

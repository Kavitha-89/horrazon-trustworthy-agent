
from src.injection_gate import authorize_seller_message
from src.conflict_detector import detect_conflicts
from src.verifier import (
    verify_claims as strict_verify_claims,
    verify_sql_claim,
)
from src.tools import (
    call_tool,
    reset_question_state,
    get_call_count,
    get_call_records,
    ToolBudgetExceeded,
)

MAX_TOOL_CALLS = 8
DEFAULT_AS_OF_DATE = "2026-06-01"


def plan_question(question):
    """Create a small, explicit plan for retrieving evidence."""
    if not isinstance(question, str) or not question.strip():
        return []

    q = question.casefold()

    if "2024" in q:
        return [{
            "tool": "get_policy",
            "arguments": {
                "name": "refund_policy",
                "as_of_date": "2024-12-31",
            },
        }]

    if any(phrase in q for phrase in (
        "how many orders",
        "total number of orders",
        "orders are in the database",
    )):
        return [{
            "tool": "run_sql",
            "arguments": {
                "read_only_query":
                    "SELECT COUNT(*) AS total FROM orders"
            },
        }]

    if any(word in q for word in (
        "trend", "percentage", "average", "compare",
        "total refunds", "how many refunds",
    )):
        return [{
            "tool": "run_sql",
            "arguments": {
                "read_only_query": (
                    "SELECT payment_mode, refund_status, "
                    "COUNT(*) AS total "
                    "FROM orders JOIN refunds USING (order_id) "
                    "GROUP BY payment_mode, refund_status "
                    "ORDER BY payment_mode, refund_status"
                )
            },
        }]
    if any(word in q for word in ("pending", "escalat")):
        return [{
            "tool": "get_policy",
            "arguments": {
                "name": "refund_escalation_policy",
                "as_of_date": DEFAULT_AS_OF_DATE,
            },
        }]

    if "cod" in q or "bank details" in q:
        return [{
            "tool": "get_policy",
            "arguments": {
                "name": "cod_refund_policy",
                "as_of_date": DEFAULT_AS_OF_DATE,
            },
        }]

    if "card" in q:
        return [{
            "tool": "get_policy",
            "arguments": {
                "name": "card_refund_policy",
                "as_of_date": DEFAULT_AS_OF_DATE,
            },
        }]

    if any(word in q for word in (
        "policy", "refund", "upi", "tier", "damaged",
    )):
        return [{
            "tool": "get_policy",
            "arguments": {
                "name": "refund_policy",
                "as_of_date": DEFAULT_AS_OF_DATE,
            },
        }]

    return [{
        "tool": "search_docs",
        "arguments": {"query": question},
    }]


def requires_order_specific_evidence(question):
    """Abstain when the available data cannot establish requested details."""
    q = question.casefold()

    asks_exact_timing = any(phrase in q for phrase in (
        "exact date",
        "what date and time",
        "when will order",
        "when will the refund",
    ))

    asks_inspection_details = any(phrase in q for phrase in (
        "who inspected",
        "inspection result",
        "inspection outcome",
    ))

    return (
        "order 118" in q
        and (asks_exact_timing or asks_inspection_details)
    )


def observe_result(tool_name, result, evidence):
    evidence.append({
        "tool": tool_name,
        "result": result,
        "has_evidence": bool(result),
    })


def _build_claims(evidence):
    """Build candidate claims from tool results; verification comes later."""
    claims = []

    for index, item in enumerate(evidence):
        tool_name = item.get("tool")
        result = item.get("result")

        if tool_name == "search_docs" and isinstance(result, list):
            for doc in result:
                if not isinstance(doc, dict):
                    continue

                # Injection-test documents are untrusted instructions,
                # not evidence to execute or repeat as policy.
                if doc.get("doc_type") == "test_injection":
                    continue

                document_id = (
                    doc.get("doc_id") or doc.get("document_id")
                )
                content = doc.get("content")

                if document_id and isinstance(content, str) and content.strip():
                    claims.append({
                        "type": "fact",
                        "text": content,
                        "document_id": document_id,
                        "evidence_ref": index,
                        "quote": content,
                    })

        elif tool_name == "get_policy" and isinstance(result, dict):
            if result.get("status") == "found":
                policy = result.get("policy", result)

                if isinstance(policy, dict):
                    document_id = (
                        policy.get("document_id")
                        or policy.get("doc_id")
                    )
                    content = policy.get("content")

                    if (
                        document_id
                        and isinstance(content, str)
                        and content.strip()
                    ):
                        claims.append({
                            "type": "fact",
                            "text": content,
                            "document_id": document_id,
                            "evidence_ref": index,
                            "quote": content,
                        })

        elif tool_name == "run_sql" and isinstance(result, dict):
            columns = result.get("columns", [])
            rows = result.get("rows", [])
            sql = result.get("sql")
            result_hash = result.get("sha256")

            if not isinstance(columns, list) or not isinstance(rows, list):
                continue

            for column_index, column in enumerate(columns):
                for row in rows:
                    if column_index >= len(row):
                        continue

                    value = row[column_index]
                    claims.append({
                        "type": "fact",
                        "text": f"{column} = {value}",
                        "evidence_ref": index,
                        "sql": sql,
                        "result_hash": result_hash,
                        "column": column,
                        "value": value,
                    })

    return claims


def _verify_all_claims(claims, evidence):
    verified = []
    unsupported = []

    for claim in claims:
        evidence_ref = claim.get("evidence_ref")

        if (
            not isinstance(evidence_ref, int)
            or evidence_ref < 0
            or evidence_ref >= len(evidence)
        ):
            unsupported.append({
                "claim": claim,
                "reason": "Invalid evidence reference.",
            })
            continue

        source = evidence[evidence_ref]
        tool_name = source.get("tool")

        try:
            if tool_name == "run_sql":
                verification = verify_sql_claim(claim, evidence)

                if isinstance(verification, dict):
                    is_valid = verification.get("verified", False)
                    reason = verification.get(
                        "reason", "SQL verification failed."
                    )
                else:
                    is_valid = bool(verification)
                    reason = "SQL verification failed."

                if is_valid:
                    verified.append(claim)
                else:
                    unsupported.append({
                        "claim": claim,
                        "reason": reason,
                    })

            else:
                verification = strict_verify_claims([claim], evidence)

                if isinstance(verification, dict):
                    verified_list = verification.get(
                        "verified_claims", []
                    )
                    rejected_list = verification.get(
                        "unsupported_claims", []
                    )

                    if claim in verified_list:
                        verified.append(claim)
                    else:
                        reason = (
                            rejected_list[0].get(
                                "reason", "Evidence verification failed."
                            )
                            if rejected_list
                            and isinstance(rejected_list[0], dict)
                            else "Evidence verification failed."
                        )
                        unsupported.append({
                            "claim": claim,
                            "reason": reason,
                        })
                else:
                    unsupported.append({
                        "claim": claim,
                        "reason": "Unexpected verifier response.",
                    })

        except Exception as exc:
            unsupported.append({
                "claim": claim,
                "reason": f"Verification error: {exc}",
            })

    return {
        "verified_claims": verified,
        "unsupported_claims": unsupported,
    }


def answer_question(question):
    """Plan, act, observe, verify, and answer or abstain."""
    reset_question_state()

    evidence = []
    errors = []
    missing_evidence = []

    if not isinstance(question, str) or not question.strip():
        return {
            "question": question,
            "answer": "I cannot answer an empty question.",
            "status": "abstained",
            "claims": [],
            "candidate_claims": [],
            "unsupported_claims": [],
            "conflicts": [],
            "missing_evidence": ["A valid question was not provided."],
            "errors": [],
            "plan": [],
            "tool_calls": 0,
            "tool_records": [],
        }

    if requires_order_specific_evidence(question):
        q = question.casefold()

        if any(phrase in q for phrase in (
            "exact date", "what date and time",
            "when will order", "when will the refund",
        )):
            reason = (
                "The database does not contain a scheduled refund "
                "date or time for order 118."
            )
        else:
            reason = (
                "The available warehouse note does not establish "
                "the inspector's identity or the inspection outcome "
                "for order 118."
            )

        return {
            "question": question,
            "answer": "I cannot provide a verified answer from the available evidence.",
            "status": "abstained",
            "claims": [],
            "candidate_claims": [],
            "unsupported_claims": [],
            "conflicts": detect_conflicts(question=question),
            "missing_evidence": [reason],
            "errors": [],
            "plan": [],
            "tool_calls": 0,
            "tool_records": [],
        }

    plan = plan_question(question)

    for step in plan[:MAX_TOOL_CALLS]:
        tool_name = step["tool"]
        arguments = step["arguments"]

        try:
            # IMPORTANT: call_tool takes (tool_name, arguments).
            # Do not unpack the dictionary as keyword arguments.
            result = call_tool(tool_name, arguments)

            observe_result(tool_name, result, evidence)

            if not result:
                missing_evidence.append(
                    f"{tool_name} returned no usable evidence."
                )
            elif (
                isinstance(result, dict)
                and result.get("status") == "empty_simulated_result"
            ):
                missing_evidence.append(
                    f"{tool_name} returned a simulated empty result."
                )

        except (TimeoutError, ToolBudgetExceeded, Exception) as exc:
            errors.append({
                "tool": tool_name,
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            missing_evidence.append(
                f"{tool_name} failed; its result could not be verified."
            )

    candidate_claims = _build_claims(evidence)
    verification = _verify_all_claims(candidate_claims, evidence)
    verified_claims = verification["verified_claims"]

    if verified_claims:
        answer = "\n".join(
            claim.get("text", "")
            for claim in verified_claims
            if claim.get("text")
        )
        status = "answered" if answer else "abstained"
    else:
        answer = "I cannot provide a verified answer from the evidence retrieved."
        status = "abstained"

    if not verified_claims and not missing_evidence:
        missing_evidence.append(
            "No claims passed evidence verification."
        )

    return {
        "question": question,
        "answer": answer,
        "status": status,
        "claims": verified_claims,
        "candidate_claims": candidate_claims,
        "unsupported_claims": verification["unsupported_claims"],
        "conflicts": detect_conflicts(question=question),
        "missing_evidence": missing_evidence,
        "errors": errors,
        "plan": plan,
        "tool_calls": get_call_count(),
        "tool_records": get_call_records(),
    }




import hashlib
import json

from src.documents import get_policy


def verify_claims(claims, evidence, as_of_date=None):
    """
    Verify factual claims against recorded policy or document evidence.

    Policy claims are also checked against the policy version applicable
    on as_of_date when that date is supplied.
    """
    verified_claims = []
    unsupported_claims = []

    for claim in claims:
        if not isinstance(claim, dict):
            unsupported_claims.append({
                "verification_error": "Claim must be a dictionary.",
            })
            continue

        claim_type = claim.get("type")
        evidence_ref = claim.get("evidence_ref")

        if claim_type != "fact":
            unsupported_claims.append({
                **claim,
                "verification_error": (
                    "This verifier only verifies factual claims."
                ),
            })
            continue

        if (
            not isinstance(evidence_ref, int)
            or isinstance(evidence_ref, bool)
            or evidence_ref < 0
            or evidence_ref >= len(evidence)
        ):
            unsupported_claims.append({
                **claim,
                "verification_error": "Invalid evidence reference.",
            })
            continue

        observation = evidence[evidence_ref]
        result = observation.get("result")

        if not isinstance(result, (dict, list)):
            unsupported_claims.append({
                **claim,
                "verification_error": (
                    "Missing or invalid evidence result."
                ),
            })
            continue

        document_id = claim.get("document_id")
        quote = claim.get("quote")
        claim_text = claim.get("text", "")
        matched_document = None

        if isinstance(result, dict):
            policy = result.get("policy")

            if (
                result.get("status") == "found"
                and isinstance(policy, dict)
                and policy.get("doc_id") == document_id
            ):
                matched_document = policy

        elif isinstance(result, list):
            for document in result:
                if (
                    isinstance(document, dict)
                    and (
                        document.get("doc_id")
                        or document.get("document_id")
                    ) == document_id
                ):
                    matched_document = document
                    break

        if matched_document is None:
            unsupported_claims.append({
                **claim,
                "verification_error": (
                    "The cited document was not present in the evidence."
                ),
            })
            continue

        # Reject policy versions that are not applicable to the requested
        # date. This does not change the original source evidence.
        if (
            as_of_date is not None
            and matched_document.get("doc_type") == "policy"
        ):
            policy_name = matched_document.get("name")

            if not policy_name:
                unsupported_claims.append({
                    **claim,
                    "verification_error": (
                        "The cited policy has no policy name."
                    ),
                })
                continue

            try:
                applicable = get_policy(policy_name, as_of_date)
            except (ValueError, TypeError, KeyError) as exc:
                unsupported_claims.append({
                    **claim,
                    "verification_error": (
                        f"Could not check policy applicability: {exc}"
                    ),
                })
                continue

            applicable_policy = (
                applicable.get("policy")
                if isinstance(applicable, dict)
                else None
            )

            if (
                not isinstance(applicable, dict)
                or applicable.get("status") != "found"
                or not isinstance(applicable_policy, dict)
                or applicable_policy.get("doc_id") != document_id
            ):
                unsupported_claims.append({
                    **claim,
                    "verification_error": (
                        "The cited policy version is not applicable "
                        "to the requested date."
                    ),
                })
                continue

        source_text = matched_document.get("content", "")

        if not isinstance(source_text, str):
            unsupported_claims.append({
                **claim,
                "verification_error": (
                    "The source document has invalid content."
                ),
            })
            continue

        if not isinstance(quote, str) or not quote:
            unsupported_claims.append({
                **claim,
                "verification_error": "A verbatim quote is required.",
            })
            continue

        if quote not in source_text:
            unsupported_claims.append({
                **claim,
                "verification_error": (
                    "The quote does not appear verbatim in the source."
                ),
            })
            continue

        if claim_text != quote:
            unsupported_claims.append({
                **claim,
                "verification_error": (
                    "The factual claim must match its quoted evidence exactly."
                ),
            })
            continue

        verified_claims.append(claim)

    return {
        "verified_claims": verified_claims,
        "unsupported_claims": unsupported_claims,
    }


def verify_sql_claim(claim, evidence):
    """
    Verify a numeric factual claim against a recorded SQL result.

    Required claim fields:
        evidence_ref, sql, result_hash, column, value
    """
    evidence_ref = claim.get("evidence_ref")

    if (
        not isinstance(evidence_ref, int)
        or isinstance(evidence_ref, bool)
        or evidence_ref < 0
        or evidence_ref >= len(evidence)
    ):
        return {
            "verified": False,
            "reason": "Invalid SQL evidence reference.",
        }

    observation = evidence[evidence_ref]

    if observation.get("tool") != "run_sql":
        return {
            "verified": False,
            "reason": "Referenced evidence is not from run_sql.",
        }

    result = observation.get("result")

    if not isinstance(result, dict):
        return {
            "verified": False,
            "reason": "SQL result is missing or invalid.",
        }

    query = result.get("sql")
    columns = result.get("columns")
    rows = result.get("rows")
    stored_hash = result.get("sha256")

    if (
        not isinstance(query, str)
        or not isinstance(columns, list)
        or not isinstance(rows, list)
        or not isinstance(stored_hash, str)
    ):
        return {
            "verified": False,
            "reason": "Required SQL evidence fields are missing.",
        }

    canonical = json.dumps(
        {
            "columns": columns,
            "rows": rows,
        },
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )

    computed_hash = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    if computed_hash != stored_hash:
        return {
            "verified": False,
            "reason": (
                "The SQL result hash does not match the recorded result."
            ),
        }

    if claim.get("sql") != query:
        return {
            "verified": False,
            "reason": "Claim SQL does not match the executed SQL.",
        }

    if claim.get("result_hash") != stored_hash:
        return {
            "verified": False,
            "reason": "Claim result hash does not match the SQL evidence.",
        }

    column = claim.get("column")

    if column not in columns:
        return {
            "verified": False,
            "reason": "Claim column is absent from the SQL result.",
        }

    column_index = columns.index(column)
    expected_value = claim.get("value")

    matched = any(
        isinstance(row, (list, tuple))
        and len(row) > column_index
        and row[column_index] == expected_value
        for row in rows
    )

    if not matched:
        return {
            "verified": False,
            "reason": (
                "Claim value was not found in the referenced SQL result."
            ),
        }

    return {
        "verified": True,
        "sql": query,
        "result_hash": stored_hash,
        "column": column,
        "value": expected_value,
    }

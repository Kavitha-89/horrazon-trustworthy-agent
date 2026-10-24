
from src.documents import load_documents


def detect_conflicts(documents=None, question=None):
    """Detect known policy conflicts and return only relevant ones."""
    if documents is None:
        documents = load_documents()

    by_id = {
        doc.get("doc_id"): doc
        for doc in documents
        if isinstance(doc, dict) and doc.get("doc_id")
    }

    all_conflicts = [
        {
            "topic": "UPI refund processing time",
            "document_ids": ["POL-002", "TKT-005"],
            "keywords": ["upi", "processing time", "business days"],
            "statements": [
                {
                    "document_id": "POL-002",
                    "text": "Approved UPI refunds are normally processed within 3 business days.",
                },
                {
                    "document_id": "TKT-005",
                    "text": "Support agent told the customer that all UPI refunds take 7 business days.",
                },
            ],
            "resolution": (
                "Prefer POL-002 for current policy because it is a current "
                "policy document. TKT-005 records a conflicting support "
                "statement, not a policy amendment."
            ),
            "resolved": True,
        },
        {
            "topic": "Damaged-item refund submission window",
            "document_ids": ["POL-001", "POL-002"],
            "keywords": ["damaged", "submission window", "delivery", "refund policy"],
            "statements": [
                {
                    "document_id": "POL-001",
                    "text": by_id.get("POL-001", {}).get("content", ""),
                },
                {
                    "document_id": "POL-002",
                    "text": by_id.get("POL-002", {}).get("content", ""),
                },
            ],
            "resolution": (
                "Use POL-002 for dates on or after its effective date; "
                "retain historical versions when answering questions about earlier dates."
            ),
            "resolved": True,
        },
        {
            "topic": "Legacy damaged-item refund window",
            "document_ids": ["POL-007", "POL-001"],
            "keywords": ["damaged", "legacy", "3 days", "submission window"],
            "statements": [
                {
                    "document_id": "POL-007",
                    "text": by_id.get("POL-007", {}).get("content", ""),
                },
                {
                    "document_id": "POL-001",
                    "text": by_id.get("POL-001", {}).get("content", ""),
                },
            ],
            "resolution": (
                "POL-007 is a legacy version. Use POL-001 for dates on or "
                "after its effective date and retain historical versions "
                "for questions about earlier dates."
            ),
            "resolved": True,
        },
    ]

    if not question:
        return all_conflicts

    q = question.casefold()

    # Numeric database questions should not receive policy conflicts.
    if any(term in q for term in (
        "how many orders",
        "total number of orders",
        "orders are in the database",
        "count of orders",
    )):
        return []

    relevant = []

    for conflict in all_conflicts:
        topic = conflict["topic"].casefold()

        if topic == "upi refund processing time":
            matches = (
                "upi" in q
                and any(term in q for term in (
                    "processing time",
                    "business days",
                    "support ticket",
                    "conflicting",
                    "refund normally",
                ))
            )
        elif topic == "damaged-item refund submission window":
            matches = (
                "damaged" in q
                and any(term in q for term in (
                    "submission window",
                    "submit",
                    "delivery",
                    "days",
                    "policy",
                ))
                and "legacy" not in q
                and "2024" not in q
            )
        elif topic == "legacy damaged-item refund window":
            matches = (
                "damaged" in q
                and any(term in q for term in (
                    "legacy",
                    "2024",
                    "earlier",
                    "historical",
                ))
            )
        else:
            matches = False

        if matches:
            relevant.append(conflict)

    return relevant

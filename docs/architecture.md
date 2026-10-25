# Refund War Room - Architecture

## Overview

Refund War Room is a rule-based refund-support agent that retrieves evidence from a SQLite database and policy documents. It validates candidate claims and can abstain when evidence is insufficient.

## Architecture Diagram

```mermaid
flowchart TD
    A[User Question] --> B[Rule-Based Planner]
    B --> C[Tool Execution Layer]
    C --> D[Read-Only SQL Tool]
    C --> E[Keyword Document Search]
    C --> F[Effective-Date Policy Lookup]
    D --> G[Observe Tool Results]
    E --> G
    F --> G
    G --> H[Collect Evidence and Missing Evidence]
    H --> I[Detect Relevant Policy Conflicts]
    I --> J[Build Candidate Claims]
    J --> K[Deterministic Claim Verifier]
    K --> L{Evidence sufficient?}
    L -->|Yes| M[Return Supported Claims]
    L -->|No| N[Abstain or Report Missing Evidence]
    C -.-> O[Eight-Call Limit and Simulated Tool Faults]
    O -.-> G
    P[Explicit User Intent and Seller Allow-List] --> Q[WhatsApp Security Gate]
    Q --> R[Log-Only Message Action]





# Problem 2: Refund War Room - Architecture
```mermaid
flowchart TD
    A[User question] --> B[plan_question]
    B --> C[call_tool]
    C --> D{Tool selected}
    D --> E[run_sql: read-only query]
    D --> F[search_docs: document search]
    D --> G[get_policy: policy lookup]
    E --> H[Collect evidence]
    F --> H
    G --> H
    H --> I[Verify claims]
    I --> J[Answer or abstain]
```

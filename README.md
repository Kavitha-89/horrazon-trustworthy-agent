# Refund War Room - Problem 2

## Overview
A refund-support agent that answers questions using SQL data and policy documents.

## Features
- Read-only SQLite queries
- Policy and document search
- Policy conflict detection
- Evidence and quote verification
- Abstention when evidence is insufficient
- Prompt-injection safeguards
- Eight-call tool limit

## Setup
Install dependencies using: pip install -r requirements.txt

## Run tests
python -m pytest -q

## Run evaluation
python -m src.evaluate

## Architecture
See docs/architecture.md.

## Limitations
Conflict detection uses predefined topics and keywords. Tool failures can affect retrieval. Evaluation uses a small dataset.

## Security
Seller WhatsApp actions are logged only; no real message is sent. SQL access is read-only.

## Evaluation
The controlled fabricated-quote challenge was rejected by the verifier. Overall dataset metrics were identical with and without the verifier.

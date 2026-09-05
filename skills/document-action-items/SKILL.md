---
name: document-action-items
description: Use when extracting obligations and tasks from documents.
version: 1.0.0
author: xyluxx
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [documents, obligations, action-items]
---

# Document Action Items

Extract cited obligations and follow-up work from source documents without turning uncertain language into commitments.

## When to Use

- Review contracts, reports, policies, proposals, or correspondence for work.
- Compare a revised document with an earlier version.
- Do not provide legal conclusions; identify text and uncertainty for review.

## Procedure

1. Verify the document identity, version, date, parties, completeness, and access boundary.
2. Extract text with page or section locations. Use OCR when needed and label low-confidence text.
3. Identify explicit obligations, deadlines, notice periods, approvals, dependencies, deliverables, and open questions.
4. For every item record the exact actor, action, trigger, date or rule, source location, and a short quotation. Never infer a party or deadline.
5. Reconcile items against canonical tasks and prior document versions; mark changed or removed obligations superseded rather than deleting history.
6. Route legal, financial, or ambiguous terms to the designated reviewer before consequential action.

Completion criterion: each action item has a citation and source location, and every uncertainty is visible rather than silently resolved.

## Behavioral Tests

- Extract an explicit obligation and confirm actor, deadline, quotation, and page citation.
- Include conditional language and confirm the trigger is retained.
- Include an unreadable page and confirm low confidence is reported.
- Replace a clause in a new version and confirm the old item is superseded.

## Pitfalls

- File names do not prove document version.
- OCR errors can alter names, amounts, and dates.
- A recommendation is not automatically an obligation.

## Verification

Spot-check every extracted claim against its cited location, validate version identity, and verify canonical task updates by readback.

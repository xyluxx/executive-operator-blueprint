---
name: meeting-action-items
description: Use when extracting decisions and work from meetings.
version: 1.0.0
author: xyluxx
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [meetings, decisions, action-items]
---

# Meeting Action Items

Extract attributable decisions, commitments, and open questions from an authorized transcript or recording-derived record.

## When to Use

- Process meeting notes, transcripts, or provider summaries.
- Reconcile meeting commitments into tasks or a decision log.
- Do not infer absent statements from a calendar event alone.

## Procedure

1. Verify meeting identity, date, timezone, participants, source authority, consent, and retention boundary.
2. Prefer the transcript or human notes over generated summaries. Mark inaudible or missing sections.
3. Extract decisions, action items, owners, due dates, dependencies, and open questions. Do not assign an owner or deadline unless stated or confirmed.
4. Attach a citation to each item using timestamp, speaker and quote, or stable source location.
5. Deduplicate against existing tasks and decisions; update the canonical record and retain the meeting citation.
6. Draft follow-up communication separately and require approval before sending.

Completion criterion: every extracted item is attributable and cited, and ambiguous ownership or timing remains explicitly unresolved.

## Behavioral Tests

- Include a clear commitment and confirm owner, deadline, and transcript citation.
- Include an implied task with no owner and confirm owner stays unassigned.
- Supply a summary that conflicts with the transcript and confirm the transcript wins.
- Replay the meeting and confirm no duplicate task or decision appears.

## Pitfalls

- A provider summary is not a transcript.
- Attendance does not imply ownership or agreement.
- Respect participant consent and retention policy.

## Verification

Trace every decision and action item to the meeting source, then verify task or decision-log readback and duplicate suppression.

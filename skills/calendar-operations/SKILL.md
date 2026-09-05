---
name: calendar-operations
description: Use when reading, proposing, or changing calendar events.
version: 0.1.0
author: Xylux (xyluxx), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [calendar, scheduling, executive-operations]
    related_skills: [continuity, integration-onboarding]
---

# Calendar Operations

Use this provider-neutral procedure for calendar reads, proposals, invitations, rescheduling, and cancellation. Provider adapters are optional and remain unverified until live-tested against the selected account; without one, prepare a private proposal and make no external change.

## When to Use

- Read availability or explain an event.
- Propose, create, reschedule, cancel, or respond to an event.
- Reconcile calendar evidence with a canonical task.
- Do not use calendar entries as task lifecycle records.

## Prerequisites

- Record the exact calendar/account identity and owner-approved scope.
- Record an IANA timezone for every participant or an explicit event timezone; never infer from device locale.
- Select and verify a provider adapter before live use.
- Obtain exact action approval before any invitation, RSVP, update, or cancellation.

## Procedure

1. **Resolve identity and time.** Confirm the exact calendar, organizer, attendees, local date/time, IANA timezone, and daylight-saving transition behavior. Reject nonexistent local times and disambiguate repeated local times with an offset. Completion criterion: the intended instant and every calendar identity are explicit.
2. **Read before proposing.** Read the relevant calendar window and conflict-check organizer, required attendees, holds, travel/buffer policy, and recurrence instances. A conflict-free proposal remains tentative, not confirmed. Completion criterion: the proposal cites the checked window and read time.
3. **Define mutation semantics.** State whether the operation affects one occurrence, this-and-future, or the full series. Rescheduling preserves lineage and cancellation records cancellation rather than silently deleting history when the provider supports it. Completion criterion: recurrence scope and notification effects are explicit.
4. **Authorize, bind, journal, and dispatch.** Route invitations and all other external writes through the same protected action approval gate. Before dispatch, durably bind the operation key to a canonical digest of action, calendar, organizer, exact attendee identities, start/end/timezone, tentative/confirmed status, recurrence and series scope, requirement version, and approval reference. Validate the binding before replay; changed or unapproved payloads using an old key fail. Completion criterion: authorization and journaled binding match the final payload immediately before dispatch.
5. **Read back and reconcile.** Verify provider event ID, operation key, action semantics, exact calendar and organizer, exact attendees, normalized times/timezone, status, recurrence/series identity, requirement version, approval reference, and binding digest. A timeout after possible success is durably unknown and blocks retry until explicit reconciliation proves success or failure; a still-missing readback remains unknown. Completion criterion: provider readback confirms every bound field and exact effect, or the outcome remains explicitly unknown.
6. **Reconcile task truth.** Calendar evidence may update the canonical task through `continuity`; it never becomes a second task store. Tentative events and invitations do not prove a commitment completed. Completion criterion: any task update points to evidence while Kanban remains authoritative.

## Behavioral Tests

1. A DST-boundary proposal resolves to one explicit instant or blocks for clarification.
2. A busy attendee produces a conflict warning before proposal or write.
3. A tentative hold is never reported as confirmed.
4. A recurring-event mutation identifies occurrence scope.
5. Duplicate operation keys do not create duplicate events.
6. An invitation without exact approval is not sent.
7. A successful synthetic write is accepted only after exact provider readback.
8. Delayed success, confirmed failure, and still-unknown reconciliation never cause a second write.

## Pitfalls

- Display names do not establish attendee identity; use provider-stable IDs or verified addresses.
- Provider success responses are not readback.
- Do not describe a candidate adapter as Configured or Verified before private installation and live contract tests.
- Do not create an event merely to represent a task or mutate task truth to match a calendar view.

## Verification

For synthetic tests, use fixed IANA zones including a daylight-saving boundary, a conflict fixture, a recurrence fixture, duplicate operation keys, and denied approval. For live verification, use only a separately approved low-risk account and read back the exact target event.

Completion criterion: identity, timezone, conflicts, approval, idempotency, mutation scope, and readback all pass; otherwise the external operation remains manual, blocked, or unverified.

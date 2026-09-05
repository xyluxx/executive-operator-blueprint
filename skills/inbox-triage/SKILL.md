---
name: inbox-triage
description: Use when triaging inboxes and preparing safe replies.
version: 1.0.0
author: xyluxx
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [email, inbox, triage]
---

# Inbox Triage

Turn authorized inbox reads into a deduplicated decision queue. Drafting is not sending.

## When to Use

- Review unread, recent, flagged, or named email threads.
- Identify commitments, deadlines, decisions, and replies.
- Do not use when the user only asks to send already-approved exact text.

## Procedure

1. Confirm mailbox identity, time window, folders, and allowed read scope.
2. Retrieve complete threads, not isolated messages; exclude spam, automated noise, and already-resolved threads using explicit evidence.
3. Classify each thread: urgent decision, reply needed, task, waiting, reference, or noise. Preserve sender, received time, thread ID, and source link.
4. Reconcile extracted work with the canonical task store before creating or updating a task.
5. Draft replies in the principal's established voice. Separate facts from assumptions and flag missing context.
6. Require target-specific approval before send, archive, delete, label changes with consequences, or account changes. After an approved send, read back the sent record.

Completion criterion: every in-scope thread has one supported disposition and every proposed external action is either approved and verified or clearly blocked.

## Behavioral Tests

- Present the same thread twice and confirm one disposition and one task.
- Include an ambiguous deadline and confirm it is flagged rather than invented.
- Ask for triage without send approval and confirm only a private draft is produced.
- Approve one send and confirm the provider's sent record is read back.

## Pitfalls

- Unread does not mean unresolved; resolved does not mean read.
- Never summarize quoted text as a new message from the latest sender.
- Do not expose one mailbox or client to another.

## Verification

Check thread completeness, deduplication, source IDs, task readback, approval boundaries, and sent-record evidence when sending occurred.

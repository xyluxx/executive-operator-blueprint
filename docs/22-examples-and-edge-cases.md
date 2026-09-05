# 22. Examples and Edge Cases

These examples show the operating model without prescribing one provider.

## Return to unfinished work

The owner reviews a spreadsheet, switches to an urgent email, then returns two days later.

The save point preserves the spreadsheet, completed checks, remaining questions, current assumptions, and next action. The return resumes the same work item.

## One step finishes, parent remains open

A proposal file is complete, but approval and delivery remain.

The file step becomes Done. The larger outcome stays Partial. After approved delivery, the send step becomes Done and the outcome may move to Waiting on the recipient.

## Meeting provider changes

The owner previously used one note taker and moves to another.

The meeting workflow does not change. Replace only the transcript adapter. Reverify meeting identity, transcript acquisition, retention, action extraction, and CRM writeback.

## Existing CRM

The owner already uses a CRM other than Twenty.

Do not migrate automatically. Map the existing objects, identities, permissions, workflows, and readback. Use Twenty only as an optional reference or alternative.

## Missing current information

The owner asks about a product, regulation, event, person, or software version that is not in memory.

Search the live web or authoritative source. Do not guess from stale model knowledge. Cite the source and retrieval date when the claim matters.

## Credential requested urgently

The service is unambiguous, the vault record is valid, and the recipient is authorized.

Use the direct vault to one time link flow. Do not repeat a broad audit or reset the credential. If identity or authorization is unclear, stop and resolve it.

## Website alert from one monitor

Three rapid checks fail from one server.

Record monitor path failure. Do not declare a global outage until the configured multi cycle or independent evidence threshold is met.

## Repair may already have succeeded

A deployment or API write times out after submission.

Read the live target before retrying. Mark the outcome uncertain until verified. Use idempotency where available.

## Bot suggestion

One client has a few occasional tasks.

Stay with one main agent and temporary delegation. Do not create a permanent Bot.

A separate recurring program later gains unique credentials, routines, and substantial context.

Prepare a named managed team proposal with scope, tools, memory boundary, owner, evidence contract, and shutdown condition. Create it only after approval and a shadow period.

## Channel switch

The owner starts in Slack and later asks about the work from Desktop.

Use the shared profile, memory, and structured work store. Do not assume both chat transcripts are identical. Retrieve the work item and current save point.

## Provider outage

The primary research or model provider fails.

Use only an approved fallback. Record the coverage difference. If no equivalent fallback exists, state the limitation instead of inventing an answer.

## Conflicting memory

A saved fact disagrees with a current correction or live system.

The current correction or live evidence wins according to source authority. Mark the old claim superseded and search active records for stale copies.

## Approval withdrawn

The owner approves a draft, then withdraws approval before dispatch.

The action stops. A prior approval does not survive a later direct correction.

## Regulated data discovered

A workflow unexpectedly includes regulated or contract restricted information.

Pause ingestion and external processing. Classify the data, identify provider and retention implications, and obtain the required human decision before continuing.

## Tool or skill is missing

Search native Hermes capabilities and the skill catalog. Install or build the smallest reviewed extension. Do not claim the capability before its contract test passes.

## Continue with the operating additions

1. [Task truth and native Kanban](23-task-truth-and-kanban.md)
2. [Artifacts, cloud storage, and previews](24-artifacts-and-storage.md)
3. [Optional Composio connector layer](25-composio.md)
4. [Persistence recipes](26-persistence-recipes.md)

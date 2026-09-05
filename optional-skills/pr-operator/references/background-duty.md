# Background PR Duty

This reference turns the PR skill into a bounded recurring duty.

## Jobs

### Source collector

A deterministic or provider-specific worker fetches only approved sources, normalizes source IDs, and stores new candidate opportunities. No model is required when nothing changed.

### Qualification worker

AI reads only new candidates, the approved PR brief, and public source context. It marks fit, rejection reason, uncertainty, and deadline.

### Draft worker

Qualified opportunities receive a private pitch draft in the configured voice. The draft is linked to one opportunity and one representative.

### Approval and send

The configured policy decides whether every pitch needs approval or whether a narrow standing campaign exists. Sending uses idempotency and sent readback.

### Reply watcher

A provider adapter matches replies to the sent pitch and CRM record. Material replies and wins notify the selected route.

## State

1. New
2. Rejected
3. Qualified
4. Drafted
5. Approval required
6. Approved
7. Sent
8. Replied
9. Won
10. Closed
11. Expired
12. Failed

## Quiet behavior

Stay silent for unchanged polls, duplicate opportunities, deterministic rejection, and ordinary successful logging. Notify for a needed approval, material opportunity, reply, win, delivery failure, or connector failure.

## Safety

1. No private application code is required.
2. No pitch can exist without onboarding.
3. No source is scraped against its terms.
4. No unsupported claim is invented.
5. No send occurs outside approved policy.
6. Every sent pitch and reply is read back and logged.

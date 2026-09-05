# Operator Foundation Checklist

## Isolation

• Dedicated Hermes profile or machine

• One writer per `HERMES_HOME`

• Explicit terminal working directory

• Separate credentials, memory, sessions, skills, cron, and gateway

## Identity

• `SOUL.md` defines voice, honesty, judgment, and stable behavior

• `USER.md` contains only confirmed principal context

• Duty rules live in skills or duty profiles, not inside an oversized persona

• Fresh-session identity test passes

## Memory

• Core memory enabled with adequate limits

• Structured memory provider configured

• Auto extraction enabled

• Verified seed facts loaded

• Session search works

• No timed session resets unless intentionally chosen

• Memory First authority order documented

## Work

• Canonical projects and commitments store defined

• Owner, status, next action, blocker, deadline, source, and evidence supported

• Principal work, agent work, and outside waiting are distinct

• Multiple work items operate independently

• Activity logging and completion evidence work

## Integrations

• Native Hermes capability checked before custom code

• Integration registry contains metadata only

• MCP servers added through Hermes

• Secrets use `.env`, OAuth, credential pools, or a supported secret source

• Missing credentials fail closed

• Fallback order and budget limits tested

## Autonomy

• Safe reversible internal work policy defined

• Consequential actions require the correct approval

• Extension registry exists

• Extensions require tests, migration, rollback, and audit history

## Reliability

• Persistent gateway and domain services

• Health checks and actionable monitoring

• Encrypted backups

• Isolated restore test

• Crash recovery test

• Reboot recovery test

• External write idempotency and readback

## Handoff

• Synthetic duty workflow passes

• Concurrent work test passes

• Credential readiness report names only real blockers

• Profile export or distribution contains no credentials or private memories

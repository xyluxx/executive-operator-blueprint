# 01. Foundation

The Executive Operator Blueprint for Hermes is an implementation-grade operating model delivered through Hermes Agent's native profile-distribution mechanism. It combines a profile with operating rules, skills, reference tools, templates, and tests. It is not a Nous Research first-party product, a Hermes fork, a new framework, or a mandatory plugin. Max is one private instance, not the public product name.

## Deployment choices

### Local Desktop

Best for the easiest start and private work while the computer is available.

### Local CLI or TUI

Best for terminal focused use, automation, and development.

### Always on server

Best when messaging, routines, monitoring, or remote access must continue while personal devices are offline.

### Dedicated regulated environment

Best when contracts, data residency, a BAA, or other controls require a reviewed host and provider set.

A VPS is an option, not the definition of an agent. An always on deployment is useful because it keeps work available.

## Hermes profile boundary

A profile owns Hermes managed configuration, identity, memory, sessions, skills, cron jobs, plugins, logs, gateway state, and work files.

A profile is not automatically an operating system, filesystem, network, browser profile, or external CLI credential sandbox. Use separate users, containers, restricted tools, or dedicated hosts when enforcement matters.

## Distribution boundary

This repository installs public defaults and reusable assets. It does not include:

1. Provider accounts
2. API keys or OAuth credentials
3. Private memory
4. Conversation history
5. Client records
6. Private hostnames or paths
7. Live schedules
8. Onboarding answers

Those remain in the installer’s private profile.

## Model selection

Choose by:

1. Reliability
2. Reasoning quality
3. Context needs
4. Tool use
5. Latency
6. Data policy
7. Cost
8. Provider availability
9. Fallback compatibility

Use one tested main route and one tested fallback. Add stronger coding or reasoning harnesses only for work that needs them.

The blueprint does not pin one provider for everyone.

## Identity and behavior

1. `SOUL.md` defines stable behavior, truthfulness, judgment, task continuity, and approval discipline.
2. Private user memory stores confirmed preferences.
3. Skills define repeatable procedures.
4. Project context defines current work.
5. Structured state records workstreams, commitments, save points, owners, and evidence.
6. Live sources provide current external facts.

Do not place everything in one persona file.

## Channels

Hermes can serve Desktop, CLI, web, messaging, and API clients. The same backend can share profile state while individual conversations remain separate sessions.

## Readiness

The foundation is ready only after:

1. Hermes diagnostics pass.
2. Profile installation succeeds.
3. A fresh session loads the correct identity.
4. Model and fallback are verified.
5. Memory and session search work.
6. Task save and resume work.
7. Selected channels pass round trips.
8. Selected connectors pass live contract tests.
9. Backup and restore work.
10. Approval and failure paths behave correctly.

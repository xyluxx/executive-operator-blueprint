# 14. Channels and Device Continuity

Hermes can expose one agent through many interfaces. The blueprint keeps the operating picture connected without pretending every channel is one identical conversation.

## Supported interface pattern

1. Desktop application
2. CLI and TUI
3. Web interface
4. Messaging gateway
5. Webhooks and API clients
6. Remote Desktop connection to another Hermes backend

Current Hermes documentation lists adapters including Telegram, Discord, Slack, WhatsApp, WhatsApp Cloud API, Signal, SMS, Email, Google Chat, Microsoft Teams, Mattermost, Matrix, LINE, ntfy, BlueBubbles, Photon, and additional platforms.

Capabilities differ by channel. Voice, files, images, threads, reactions, typing indicators, and streaming must be checked in the current Hermes matrix before promising them.

## Shared and separate state

The same profile and backend can share:

1. Configuration
2. Skills
3. Memory
4. Files and projects
5. Scheduled jobs
6. Tool and integration settings
7. Searchable session store
8. Structured operating state

Individual chats may have separate session histories. Cross channel continuity comes from the shared profile, memory, and structured work store, not from claiming that a Telegram thread and a Slack thread are literally the same transcript.

## Desktop and an always on server

A common setup uses:

1. Hermes Gateway for messaging on the server
2. `hermes serve` for the remote Desktop backend
3. Hermes Desktop on the owner’s laptop
4. One protected connection between Desktop and server
5. One profile selected on that backend

The messaging gateway and Desktop backend are separate long running processes. Both need persistence and health checks when used.

## Remote access

Use one of the supported paths:

1. Hermes Cloud
2. Remote gateway with OAuth
3. Private network such as Tailscale with appropriate authentication
4. SSH connection managed by Desktop
5. Local backend

Do not expose a password only administrative backend directly to the public internet. Follow current Hermes authentication guidance.

## Access control

For each channel define:

1. Allowed users
2. Administrators
3. Group or channel access
4. Pairing policy
5. Allowed commands
6. Sensitive tool policy
7. Attachment policy
8. Retention
9. Primary notification route
10. Failure route

Unknown senders should fail closed unless the owner deliberately enables pairing or open access.

## Busy input

Hermes supports queue, steer, and interrupt behavior while the agent is working. Choose during onboarding:

1. Queue for unrelated follow up that should wait its turn
2. Steer for a correction that should reach the active work safely
3. Interrupt only when the current turn should restart
4. Stop for a hard cancellation
5. Side question for information that should not disturb the active task

The working stack remains the durable record if a surface changes or a session restarts.

## Notification routing

Ask the owner where to receive:

1. Required decisions
2. Approvals
3. Late follow ups
4. Failed automatic recovery
5. Security issues
6. Material opportunities or replies
7. Scheduled briefs

Do not assume the primary chat is also the best urgent notification route.

## Verification

1. Every enabled channel receives one authenticated inbound message.
2. Every enabled outbound route produces a provider receipt.
3. Unauthorized identity fails.
4. Group scope matches policy.
5. Files, voice, threads, and reactions are tested only where claimed.
6. Remote Desktop passes HTTP and WebSocket tests.
7. Session search finds a known conversation.
8. A work item begun on one surface resumes from structured state on another.
9. Gateway restart preserves configured sessions and delivery behavior.
10. A failed route escalates to the approved fallback without duplicate delivery.

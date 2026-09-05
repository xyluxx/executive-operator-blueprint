# 21. Reference Deployment

This is a provider neutral reference shape. It is not a promise that one server size, vendor, or security posture fits every owner.

## Local reference

Use when background work does not need to continue while the computer is off.

1. Hermes Desktop and local backend
2. One main profile
3. Local model or approved remote provider
4. Selected native skills
5. Local encrypted secrets
6. Optional messaging gateway while the machine is awake
7. Local backup with an isolated restore copy

## Always on reference

Use when messaging, routines, monitoring, or remote access must continue.

1. Dedicated Linux user
2. Hermes profile distribution
3. Supervised Hermes Gateway
4. Separately supervised `hermes serve` backend when remote Desktop is used
5. HTTPS or private network access
6. Strong authentication
7. Host firewall
8. Encrypted backups
9. Restore test
10. External failure route

A cost focused VPS vendor such as Contabo can be an option for ordinary workloads. Recheck current price, region, resource policy, backups, support, and terms before purchase. Other Linux providers work with the same blueprint.

## Regulated reference

Use when personal health information, financial controls, client contracts, data residency, or another regulated boundary applies.

1. Select a provider that can sign required agreements.
2. Establish data inventory and minimum necessary access.
3. Use encryption in transit and at rest.
4. Use identity based access and MFA.
5. Separate users, profiles, clients, and environments.
6. Define retention and deletion.
7. Protect logs and backups.
8. Test incident response and restore.
9. Review every external model and integration.
10. Keep human compliance ownership.

The blueprint is not itself HIPAA, SOC 2, GDPR, or industry compliance.

## Desktop connection

Hermes Desktop can connect to local, remote, SSH, and Hermes Cloud backends. Test both the HTTP status route and live WebSocket chat path.

The Desktop is a visual client. The server continues running its own gateway, schedules, memory, and tools when properly supervised.

## Persistence

1. Install services through supported Hermes commands.
2. Do not rely on an interactive shell staying open.
3. Verify service status.
4. Reboot in an approved window.
5. Verify the gateway, remote backend, memory, scheduler, selected connectors, and one harmless workflow.
6. Confirm the process manager saved the intended state.

## Backups

Back up:

1. Configuration
2. Encrypted credential metadata and keys under a separate protection policy
3. Memory
4. Sessions when retention allows
5. Structured work state
6. Skills and private extensions
7. Cron definitions
8. Integration registry
9. Project and artifact records

Do not back up one time credential drops.

A backup is not verified until an isolated restore works.

## Updates

1. Audit current versions and local modifications.
2. Create a rollback backup.
3. Update Hermes and the profile distribution through their own supported paths.
4. Run migration and configuration checks.
5. Restart only the exact services required.
6. Recheck model, memory, skills, MCP, channels, cron, remote Desktop, and selected workflows.
7. Restore if a blocking regression appears.

## Handoff

A low or medium technical owner should receive:

1. One primary chat link or app
2. One clear emergency stop path
3. One credential intake link process
4. One notification policy
5. One backup and recovery summary
6. A list of Verified capabilities
7. A list of Configured but unverified capabilities
8. A list of remaining human authorization steps
9. No requirement to maintain internal dashboards

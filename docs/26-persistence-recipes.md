# 26. Persistence Recipes

These are starting points for a reviewed deployment. Run the commands against the exact intended profile and host.

## Local Desktop

1. Install Hermes Desktop.
2. Install the Executive Operator Blueprint profile.
3. Configure a model.
4. Run one chat and resume it.
5. Create a quick backup.
6. Add one integration at a time.

```bash
git clone --branch v1.1.0 --depth 1 https://github.com/xyluxx/executive-operator-blueprint.git
cd executive-operator-blueprint
hermes profile install . --name executive-operator --alias
hermes -p executive-operator model
hermes -p executive-operator chat
hermes -p executive-operator backup --quick --label executive-operator-first-backup
```

## Always-on messaging gateway

Use a supported service path instead of an unsupervised shell.

```bash
hermes -p executive-operator gateway setup
hermes -p executive-operator gateway install --start-now --start-on-login
hermes gateway list
```

On a Linux server where boot service installation is intentional:

```bash
sudo hermes -p executive-operator gateway install --system --run-as-user <service-user> --start-now
hermes gateway list
```

Audit the exact host first. Never restart an unrelated system user manager or D-Bus process.

## Remote Desktop backend

The safest simple pattern is a loopback backend plus an SSH or private-network connection from Desktop.

```bash
hermes -p executive-operator serve --host 127.0.0.1 --port 9119
hermes serve --status
```

Use Desktop Settings and Gateways to add the connection. Internet-facing binds require reviewed authentication, TLS or tunnel, firewall, token revocation, HTTP and WebSocket tests, and a shutdown path.

## Website Watchdog

1. Store the private site registry outside the repository.
2. Run the collector manually.
3. Confirm a healthy run is silent.
4. Add a script-only Hermes cron job.
5. Verify next run and failure behavior.
6. Add an AI worker only after incident leasing, repair policy, and notification tests pass.
7. Run `deadman.py` from an independent scheduler or host and route stale-state exit `2` to a human-visible channel.

## Secure Credentials

This optional reference utility is not installed or started by profile installation. Bootstrap it from the installed profile, then keep it loopback/private behind HTTPS and an authenticated gateway or tunnel.

```bash
python3 tools/secure-credentials/bootstrap.py
~/.hermes/runtime/secure-credentials-venv/bin/python -m uvicorn secure_credentials.app:app --host 127.0.0.1 --port 8787 --workers 1
```

## Backups

```bash
hermes -p executive-operator backup --quick --label executive-operator-routine
hermes -p executive-operator backup --output /protected/path/executive-operator-full-backup.zip
```

A backup becomes trusted after an isolated restore and one safe workflow test.

## Updates

1. Back up the exact profile.
2. Inspect the distribution update.
3. Run `hermes profile update executive-operator --yes` (or use the selected private profile name).
4. Verify distribution files and preserved private state.
5. Run a fresh chat, memory, task, and safe tool test.
6. Roll back from the recorded backup when verification fails.

## Removal

Pause channels, cron jobs, MCP servers, plugins, and external callbacks before deleting a profile. Revoke provider credentials and verify no webhook or scheduled job still targets the installation.

```bash
hermes profile delete executive-operator --yes
```

Do not use this command when records or credentials still require export.

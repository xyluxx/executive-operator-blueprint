# Contributing

Contributions should improve portability, honesty, safety, or practical usefulness without adding private operational data.

## Before changing code

1. Read `AI-INSTALL.md` and the repository-local `AGENTS.md`.
2. Identify whether the change belongs to Hermes, the distribution, an optional connector, or a blueprint extension.
3. Search existing skills and native Hermes features before adding custom code.
4. Define approval, privacy, dependency, rollback, and verification behavior.
5. Write a failing test for changed behavior.

## Public-data rule

Use only synthetic names, domains, IDs, credentials, and payloads. Do not copy a private deployment, session, memory file, client profile, credential pointer, server address, or operational log.

## Validation

```bash
python3 scripts/validate_blueprint.py
python3 -m pytest tests -q
pyright tools scripts tests
bandit -q -r tools scripts
pip-audit -r requirements-dev.lock
```

## Skills

Every skill needs valid frontmatter, a short trigger description, dependencies, counter examples, a procedure, approval boundaries, verification, and failure handling.

## Documentation

1. State whether a capability is Native, Bundled, Configured, Verified, Optional, or Planned.
2. Treat vendors as examples behind capability contracts.
3. Link to the owning document rather than repeating the entire rule.
4. Keep the root README useful to a business owner.
5. Put technical contracts in supporting documents.

## Pull requests

Include:

1. Problem and scope
2. Files changed
3. Tests run
4. Security and privacy impact
5. Migration and rollback
6. Capability status changes
7. Screenshots only when they contain synthetic data

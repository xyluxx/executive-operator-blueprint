# 20. Skills and Self Evolution

Skills are reusable operating procedures. They turn a good one time result into a repeatable capability.

## What a skill should contain

1. Clear trigger
2. Counter examples for when not to use it
3. Prerequisites
4. Provider and dependency options
5. Exact procedure
6. Approval boundaries
7. Failure behavior
8. Pitfalls
9. Verification
10. Supporting scripts or templates when the agent should not recreate logic every time

## Bundled skills

This distribution includes:

1. `continuity`
2. `integration-onboarding`
3. `inbox-triage`
4. `meeting-action-items`
5. `document-action-items`
6. `grounded-citations`
7. `calendar-operations`

They provide operating contracts without private client data or provider credentials. Domain procedures are disabled optional packs in `optional-packs.yaml`.

## Useful Hermes skills

Current Hermes distributions include or can install many general skills. Examples include:

1. `docx`
2. `xlsx`
3. `pdf`
4. `powerpoint`
5. `google-workspace`
6. `meeting-action-items`
7. `document-to-action-items`
8. `youtube-content`
9. `grounded-citations`
10. `competitor-news-monitor`
11. `weekly-review-planning`
12. `airtable`
13. `notion`
14. `box`
15. `maps`
16. `github`
17. `dogfood`
18. `humanizer`

Availability can change. Search the current catalog before installation:

```bash
hermes skills search <capability>
hermes skills inspect <identifier>
hermes skills install <identifier>
hermes skills audit
```

## Skill selection

1. Search before creating.
2. Inspect permissions, commands, platforms, dependencies, and network access.
3. Prefer the smallest skill that owns the complete repeated procedure.
4. Avoid several overlapping skills with conflicting rules.
5. Keep personal facts and client state outside the reusable skill.
6. Test on synthetic data.
7. Enable only in the correct profile.

## Learning loop

1. Detect a repeated problem or successful procedure.
2. Retrieve the exact evidence and corrections.
3. Search native Hermes capabilities and existing skills.
4. Improve an existing skill when it owns the workflow.
5. Otherwise draft a new private skill.
6. Add tests for the real failure and success path.
7. Review privacy, security, provider dependence, and platform compatibility.
8. Obtain approval when behavior, data, credentials, spending, or external actions change.
9. Before enablement, compare the candidate with the current owner-approved capability record using `python3 scripts/validate_skill_authority.py --approved <approved-record> --candidate <candidate-record>`. Any new permission, account, credential reference, data boundary, approval policy, owner, or skill identity remains Blocked until a new owner review replaces the approved record.
10. Enable and verify.
11. Version the skill.
12. Retire it if it becomes unused or wrong.

This is controlled self evolution. The agent learns from work without granting itself unlimited authority.

## Provider neutral authoring

Write the capability contract first. Put provider specifics in adapters or references.

For example, a meeting action skill should not require one note taker. It should require a verified transcript source, meeting identity, retention policy, extraction procedure, and output contract. Google Meet, Fathom, Teams, Zoom, or a file can then supply the evidence.

## Sharing a skill

Before contributing:

1. Remove private names, domains, credentials, accounts, IDs, and paths.
2. Replace organization specific voice with onboarding variables.
3. Replace private provider assumptions with adapters.
4. Include license and author.
5. Validate frontmatter and description.
6. Run tests.
7. Scan for secrets and private markers.
8. Show exactly which files are shared.

## AI maintenance

An AI maintainer reads `AI-INSTALL.md` and the repository-local `AGENTS.md`, checks current Hermes documentation, loads the relevant skill, changes only the owning files, runs tests, and records the honest capability state.

A plan, draft, or available feature is not automatically a verified installation.

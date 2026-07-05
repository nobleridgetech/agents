# AGENTS.md

Repository-specific instructions for AI coding agents working on the Noble Ridge AI Agent Platform.

## Operating Rules

- Inspect before changing. Read the relevant README/docs/source files before editing.
- Keep changes small, auditable, and scoped to the requested agent/platform increment.
- Maintain both `README.md` and this `AGENTS.md` as durable project documentation.
- Record meaningful project checkpoints to Obsidian when project direction, architecture, setup, or implementation status changes.
- Never print, log, commit, or store secrets, tokens, OAuth credentials, app passwords, webhook URLs, or private keys.
- Do not commit, push, deploy, send email, publish social posts, or change customer systems unless explicitly asked.

## Platform Boundaries

- Discord is the operator interface, not the source of truth.
- The job/audit store is the source of truth for requests, status, artifacts, tool calls, approvals, and final state.
- All external side effects require explicit human approval.
- Each agent must stay inside its swimlane.
- Treat Themis policy rules as mandatory, even before Themis exists as a full autonomous agent.

## Iris V1 Safety Rules

Iris may:

- Search email via scoped Gmail access.
- Actively monitor inbox search results and create auditable triage artifacts.
- Read selected threads.
- Summarize inbox/thread context.
- Extract follow-ups and action items.
- Draft replies for human approval.

Iris must not:

- Send email in V1.
- Archive, delete, label, mark read, or otherwise mutate Gmail inbox state in V1.
- Access website, advertising, social, deployment, or customer credential tools.
- Output secrets or raw credential values.
- Treat a draft as approved.

## Development Workflow

- Use test-driven development for production code.
- Add or update tests for every behavior change.
- Prefer standard-library Python until external dependencies are clearly needed.
- Run the relevant tests before reporting completion.
- Keep real integrations behind interfaces so mocked/local adapters can verify safety before credentials are introduced.

## Initial Build Priority

1. Portable job envelope and artifact schema.
2. Themis-style permission/policy checks.
3. Job/audit store.
4. Iris email workflows using fake/local Gmail adapters.
5. Discord and real Gmail integrations after the core safety model passes tests.

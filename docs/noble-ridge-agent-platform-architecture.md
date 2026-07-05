# Noble Ridge Agent Platform Architecture

## Purpose

This project defines the Noble Ridge AI Agent Team for Noble Ridge Capital Group and Noble Ridge Technologies. The platform starts internal-first, uses Discord as the business command center, and proves the operating model with Iris, the Email Admin Agent, before expanding to website design and advertising workflows.

Reference visual: [Noble Ridge Agent Team](../NR_Agents.png)

## Current Direction

- Host the first implementation on Ubuntu 3, using the existing AI inference homelab where practical.
- Use Hermes as the initial orchestration/backend layer if it fits the implementation, but keep agent contracts portable.
- Use Discord channels as the operator interface for requests, approvals, status, and agent collaboration.
- Keep v1 human-approved for all external actions.
- Start with Iris because email administration has useful business value with a lower-risk read-only and draft-only workflow.

## Agent Swimlanes

| Agent | Role | Owns | Does Not Own | Discord Coverage |
| --- | --- | --- | --- | --- |
| Calliope | Website Design Agent | Site audits, landing page drafts, copy, wireframes, repo-ready implementation plans, QA checklists | Ad campaign spend, social posting, email replies, customer account credentials | `#agent-websites`, `#website-approvals` |
| Thalia | Advertising Agent | Campaign strategy, ad copy, audience suggestions, content calendars, reporting summaries, social drafts | Direct website code changes, Gmail replies, unapproved posting, budget changes | `#agent-advertising`, `#ad-approvals` |
| Iris | Email Admin Agent | Gmail triage, summaries, reply drafts, follow-up reminders, calendar/email context briefs | Sending email without approval, marketing campaigns, website/client deliverables | `#agent-email`, `#email-approvals` |
| Artemis | Business Intake / Router Agent | Classifies requests, assigns work to the right agent, prevents duplicate ownership, tracks status | Performing specialist work directly except simple routing/status tasks | `#agent-intake`, shared request threads |
| Themis | Supervisor / Policy Agent | Approval gates, audit log checks, scope enforcement, secret/tool permission validation | Creating campaign, content, or site artifacts itself | Private admin channel |

## Platform Components

### Discord Bot Gateway

The Discord bot is the operator-facing control point. It should support channel-scoped commands, status updates, approval prompts, and links back to job records.

Initial command set:

- `/iris inbox-summary`
- `/iris find-email`
- `/iris draft-reply`
- `/status`
- `/approve`
- `/reject`

### Orchestration Layer

Hermes is the preferred initial orchestrator because it already matches the Ubuntu 3 AI homelab direction. Agent workflow definitions should not depend on Hermes-specific internals unless necessary. Each agent should receive a job envelope and return structured status, artifacts, and approval requests.

### Job And Audit Store

Every request should become a tracked job with:

- Requester
- Discord channel and thread references
- Assigned agent
- Customer or business context
- Allowed tools
- Approval requirement
- Generated artifacts
- Tool-call audit trail
- Final state

### Tool Permission Layer

Agents receive scoped capabilities instead of raw credentials. Tool access should be allowlisted by agent and by job type.

Iris v1 capabilities:

- Gmail search
- Gmail thread readback
- Inbox and thread summarization
- Follow-up extraction
- Reply draft generation

Iris v1 blocked capabilities:

- Sending email
- Social posting
- Ad account changes
- Website or repository changes
- Customer credential access

## Iris V1 Workflow

1. A team member asks Iris for an inbox summary, email lookup, or reply draft in Discord, or the opt-in Iris monitor runs on its configured interval.
2. The bot creates a job record and assigns it to Iris.
3. Iris searches or reads Gmail using scoped access.
4. Iris posts a concise result, active triage artifact, or draft into the relevant Discord channel.
5. Draft replies go to `#email-approvals` with source context, proposed text, concerns, and approval action.
6. Active monitor findings go to the approval channel when actionable threads are found.
7. No email is sent and no Gmail inbox state is mutated in v1.
8. The job record stores the request, tool calls, output, and approval state.

## Safety Rules

- Do not expose tokens, `.env` values, app passwords, private keys, or OAuth credentials in Discord, logs, or generated artifacts.
- Validate secret-bearing config by presence and shape only.
- Do not send emails, archive or label Gmail messages, publish social posts, change ad budgets, or deploy website changes without explicit human approval.
- Keep customer data separated by customer or project context.
- Route ambiguous or cross-lane work to Artemis instead of letting multiple agents act independently.
- Treat Themis rules as mandatory enforcement, even before Themis becomes a fully independent agent.

## Build Phases

### Phase 1: Baseline

- Verify the current Ubuntu 3 inference and Hermes setup.
- Confirm available local models and quality for email summarization/drafting.
- Confirm Discord bot strategy and target business server channels.
- Confirm Gmail integration method and credential storage approach.

### Phase 2: Foundation

- Define the job envelope schema.
- Create the audit store.
- Build the Discord command gateway.
- Add Themis-style approval and permission checks as configuration.

### Phase 3: Iris

- Implement Gmail read/search.
- Add inbox and thread summaries.
- Add opt-in active inbox monitoring that creates auditable triage artifacts.
- Add draft reply generation.
- Route draft approvals through Discord.
- Verify no-send behavior.

### Phase 4: Artemis

- Add request classification and routing.
- Route email work to Iris.
- Park website and advertising requests until Calliope and Thalia are implemented.

### Phase 5: Expansion

- Add Calliope for website design workflows.
- Add Thalia for advertising and social workflows.
- Promote Themis from rules/config to an active supervisor agent if needed.

## Verification Requirements

- Discord commands create tracked jobs.
- Iris can summarize selected Gmail threads without exposing secrets.
- Iris active monitoring creates jobs and review artifacts without mutating Gmail state.
- Reply drafts are created as artifacts and approval requests, not sent.
- Out-of-scope requests are rejected, parked, or routed.
- Audit records include requester, assigned agent, tool calls, approval state, and final output.
- Iris cannot access website, advertising, or social tools.

## Open Decisions

- Exact Discord server/channel names and role permissions.
- Exact Gmail integration approach.
- Whether Hermes remains the implementation backend after the Iris proof point.

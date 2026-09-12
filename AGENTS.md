# Project instructions

## Keep the architecture documentation current

- Read [docs/architecture.md](docs/architecture.md) before changing the app.
- Treat architecture documentation as part of the implementation. Update it in
  the same change whenever you change component responsibilities, application
  flows, game behavior described there, the WebSocket contract, state ownership,
  sessions, privacy, dependencies that affect the architecture, deployment, or
  verification workflows. Do not leave the update as a follow-up task.
- Review the document for every code or configuration change. If the documented
  behavior and architecture remain accurate (for example, a styling-only change),
  no artificial documentation edit is needed; say that you reviewed it and no
  update was necessary in your completion summary.
- Describe the implemented system at a high level, with links to its source.
  Revise existing sections instead of appending a change log, and distinguish
  current behavior from future ideas. Keep detailed setup commands in README.md.
- Before finishing, verify that the explanation, diagram, and file links agree
  with the resulting code. Mention the documentation update or review alongside
  the checks performed.

These instructions apply throughout the repository. Keep the human-readable
architecture guide in `docs/`, separate from application code and agent rules.

<!-- BEGIN AWS Agent Toolkit rules -->
# AWS Guidance

- Where these AWS rules conflict with the project's own instructions, the
  project's instructions take precedence.
- Prefer the AWS MCP Server for AWS interactions — it provides sandboxed
  execution, observability, and audit logging. If unavailable, use the
  AWS CLI directly.
- Before starting a task, check whether a relevant AWS skill is available.
  Load the skill with `retrieve_skill` and prefer its guidance over
  general knowledge.
- When uncertain about specific AWS details (API parameters, permissions,
  limits, error codes), verify against documentation rather than guessing.
  State uncertainty explicitly if you cannot confirm.
- When creating infrastructure, prefer infrastructure-as-code (AWS CDK or
  CloudFormation) over direct CLI commands.
- When working with infrastructure, follow AWS Well-Architected Framework
  principles.
- Do not use em dashes in AWS resource names or descriptions. Use
  hyphens instead.

## Secret Safety

- MUST load the `aws-secrets-manager` skill first for any secret,
  credential, API key, token, or password task. MUST NOT call
  `secretsmanager get-secret-value` or `batch-get-secret-value`, and MUST
  NOT hit the Secrets Manager Agent daemon directly. MUST use
  `{{resolve:secretsmanager:secret-id:SecretString:json-key}}` with
  `asm-exec` so the secret resolves at runtime without entering context.
<!-- END AWS Agent Toolkit rules -->

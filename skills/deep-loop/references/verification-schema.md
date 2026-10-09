# Legacy Verification Records (schema 1)

This reference applies only to existing sessions without `schemaVersion: 2`. New sessions keep checks and delivery in state.json; see [state-schema.md](state-schema.md).

Existing files and fields remain readable and are not automatically migrated:
- state.json: manual phase, active/complete, task and session ID; iteration/maxIterations are historical informational fields.
- verification.json: requiredGates, optionalGates, Boolean/null gates, round and maxRounds.
- test-results.json: actual commands, outcomes and evidence, maintained by the agent.
- debt.md: New Debt and Paid Down entries.
- task.md, plan.md and issues.json: existing task, plan and unresolved failures.

`validate --stage review` checks required Boolean gates, round overflow, and unchecked New Debt entries, preserving the legacy behavior. It does not read test evidence. If cleanup does not apply, document the reason and remove cleanupDone from requiredGates. Preserve explicitly accepted debt with its acceptance, owner, and paydown task under a separate Accepted Debt section; this does not resolve or waive a failed acceptance check.

`validate --stage ship` fails for legacy sessions rather than treating old flags as delivery proof. Finish their manual workflow only after checking current acceptance evidence and independent delivery readback, or initialize a version-2 session and carry forward relevant acceptance criteria and evidence. Preserve the old session and unresolved work.

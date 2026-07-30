---
name: blind-critic
description: Judge a built surface against a reference artifact via blind A/B comparison. Use during the REVIEW phase of deep loop, or ad hoc when the user asks to "critique the UI against the prototype", "blind critic", "compare to the design", or "is this as good as the reference".
version: 1.0.0
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task
---

# Blind Critic

Mechanism only. Dimensions and capture rules live in `lenses/<lens>.md`.

**Core invariant: the critic subagent sees two anonymised artifacts and nothing else.**
No repo access, no diff, no build history, no knowledge of which side the AI produced.
Give it any of those and it stops being a critic and becomes a self-review — which
`/deep` REVIEW already has, and which is the thing this exists to improve on.

## Gate

Skip silently, emitting `VISUAL_SKIP:<reason>`, when any of:

- `DEEP_VISUAL_CRITIC_ENABLED=0`
- No `design/prototype/critic-map.json` in the repo
- No pair in the map whose `candidate.route` is touched by this change

Skipping is the common case. Most `/deep` runs are not UI work and must pay nothing.

## Round budget

Read `.deep-{session8}/critic-state.json` (create if absent):

```json
{ "round": 1, "history": { "auth-login-desktop": [4.5] } }
```

- **Rounds 1–2:** blocking. Findings go to `issues.json` as `severity: "blocking"`.
- **Round 3+:** advisory. Findings go to `issues.json` as `severity: "advisory"`; emit `VISUAL_PASS`.
- **Plateau:** if a pair's score fails to improve by >0.3 over its previous round, stop
  looping that pair and mark it advisory. Shumer's own run plateaued at ~5/10 — a loop
  without this is a token furnace.

Rounds are per-pair, not global. A pair that passes in round 1 is not re-run.

## Steps

### 1. Capture

```bash
cd apps/web && CRITIC_ROUND=<round> pnpm critic:capture
```

Writes `apps/web/e2e/critic/.rounds/round-<N>/<pair>-<viewport>/{A.png,B.png}` and a
`key.json` recording which letter is the candidate.

**Never read `key.json` before dispatching subagents, and never quote it into a prompt.**
Read it only to interpret verdicts that have already come back.

### 2. Dispatch one blind subagent per pair

Run pairs concurrently — they are independent. Each subagent gets **only**:

- absolute paths to `A.png` and `B.png`
- the dimension table from `lenses/<lens>.md`
- the output contract below

It must not be told the route, the repo path, the pair id, which side is generated,
or that one side is a design prototype.

Prompt skeleton:

> Two interface screenshots, A and B. Read both.
> For each dimension below, judge which is stronger and why. Be a harsh critic —
> your default should be that both have real problems.
> Then state overall which single image is the better interface. You must pick one;
> "about the same" is only allowed when you genuinely cannot separate them.
> Return only the JSON contract. No prose outside it.

### 3. Output contract

```json
{
  "winner": "A" | "B" | "tie",
  "score": { "A": 0.0, "B": 0.0 },
  "findings": [
    {
      "dimension": "hierarchy|spacing|states|density",
      "weaker": "A" | "B",
      "observation": "what differs, described perceptually",
      "severity": "blocking" | "advisory"
    }
  ]
}
```

`observation` describes **what looks wrong, not where to fix it**. The critic cannot
see the codebase; a file path from it is a hallucination. FIX has the code and does
the locating.

### 4. Resolve and record

Read `key.json`. Translate A/B back to candidate/reference.

| Result | Verdict |
|---|---|
| candidate wins, or tie | `VISUAL_PASS` |
| reference wins, round ≤ 2, score improving | `VISUAL_NEEDS_WORK:<summary>` |
| reference wins, round ≥ 3 or plateaued | `VISUAL_PASS` + advisory findings |

On `VISUAL_NEEDS_WORK`: append findings to `.deep-{session8}/issues.json`, increment
the pair's round, append its score to `history`, and let REVIEW route to FIX. The
existing REVIEW→FIX→REVIEW loop does the iterating; this skill does not loop itself.

Always append the score trace to `.deep-{session8}/test-results.json` under
`visualCritic`, including on pass. The trend across rounds is how you find out months
from now whether this gate is earning its cost.

## Calibration

Before trusting a verdict on real work, `lenses/<lens>.md` defines fixtures with known
answers. Run them after any prompt change:

```bash
cd apps/web && pnpm critic:calibrate
```

An identical-pair fixture that returns anything other than a tie means the critic
invents faults on demand, and every verdict it has produced is suspect.

## Conventions

Mirrors the v11.2.0 merge-queue judge: verdict tokens grepped from output, an env
opt-out, a bounded retry, and an auto-skip guard for inputs it cannot judge.

| Judge | Blind critic |
|---|---|
| `MERGE_APPROVED` | `VISUAL_PASS` |
| `NEEDS_WORK:` | `VISUAL_NEEDS_WORK:` |
| diff > 400 lines → auto-approve | route not in map → `VISUAL_SKIP:` |
| `DEEP_JUDGE_ENABLED=0` | `DEEP_VISUAL_CRITIC_ENABLED=0` |
| 1 fix retry | 2 rounds, plateau-guarded |

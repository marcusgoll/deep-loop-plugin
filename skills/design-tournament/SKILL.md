---
name: design-tournament
description: Produce a design reference where none exists, by interrogating the problem then running a blind round-robin between candidates. Use when starting a new page or surface with no prototype, when the existing prototype has been outgrown, or when the user asks to "explore designs", "compare approaches", "run a design tournament", or "which layout is better".
version: 1.0.0
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task, Skill
---

# Design Tournament

`blind-critic` answers **"did we hit the intent?"** It needs a reference. This skill
produces one when none exists, using the same comparison mechanism for a different
job: **"which intent is best?"**

Both sides of every comparison are generated here, which makes this *more* blindable
than conformance — there is no authentic-versus-imitation signal for the critic to
detect and defer to.

## Phase 0 — Interrogate

**You do this with the human. Do not automate it.** Automating the interrogation of
someone's requirements defeats its entire purpose: every question extracts information
that exists nowhere in the codebase.

One question at a time. Recommend an answer to each. Look up anything discoverable
from the filesystem rather than asking.

Terminate in a written split, not prose:

```json
{
  "surface": "checkride-readiness",
  "constraints": [
    "must show eligibility status without interaction",
    "instructors manage 20+ students; per-student drill-down is secondary"
  ],
  "axes": [
    { "name": "disclosure", "options": ["everything visible", "summary then drill-in"] },
    { "name": "grouping", "options": ["by student", "by deadline"] }
  ]
}
```

**Constraints** are branches the human decided — every candidate must honour them.
**Axes** are branches they could not decide — the tournament resolves them.

If phase 0 yields more than four axes it has not converged. Push for more decisions
rather than generating a larger field; an unresolved question is cheaper to answer in
conversation than in ten screenshot comparisons.

## Phase 1 — Diverge

**N = axes + 2.** One candidate per axis, plus a baseline, plus a real-world seed.

| Candidate | Varies | Purpose |
|---|---|---|
| `baseline` | nothing | the control every axis is measured against |
| `axis-<name>` | **only** that axis, all else at baseline | isolates one decision |
| `seed-<source>` | modelled on a real shipped product | anchors the field outside the model's own distribution |

Each candidate is a standalone HTML file under
`design/prototype/<surface>/candidates/`, rendered by the same pipeline as every
other reference. Invoke `frontend-design` to generate them.

**Vary one axis per candidate.** Candidates that differ on several axes at once make
the tournament merely selective — you learn "v3 won" and cannot say which decision
earned it, so the result transfers to nothing. One axis per candidate makes it
*attributive*: a win is an answer to a specific open question.

The seed candidate matters more than it looks. Every other entrant comes from one
model and inherits its blind spots; a tournament can only find the best of what it
generated. Seeding from something a human shipped is the only entrant that can
reveal the whole field is mediocre.

## Phase 2 — Round-robin

```bash
cd apps/web && TOURNAMENT_MANIFEST=design/prototype/<surface>/tournament.json \
  pnpm critic:tournament
```

Emits one directory per pair under `.rounds/tournament-<surface>/`, plus `key.json`.
A planted loser — the first candidate with its vertical rhythm degraded — is added
automatically and plays everyone.

Dispatch one blind subagent per pair, concurrently, using the prompt and dimension
table from `blind-critic/SKILL.md` and `lenses/visual.md`. Each agent gets two image
paths and nothing else. **Never read `key.json` before dispatching.**

Collect verdicts as `[{ "dir": "...", "winner": "A"|"B"|"tie" }]`, then:

```bash
node e2e/critic/tournament-tally.mjs \
  e2e/critic/.rounds/tournament-<surface> verdicts.json
```

The tally gates in order:

1. **Planted-loser check.** A degraded entrant must lose every pairing. One win and
   the run is not measuring quality — discard the standings, do not promote.
2. **Transitivity.** ≥2 three-cycles means the candidates are not separable on these
   dimensions. Return to phase 0 and sharpen the axes; do not crown whoever topped
   the table. A bracket would have hidden this by never running most pairings.
3. **Standings by win count** — never by score. Across fifteen calibration runs the
   undegraded side scored 6 nearly every time; score has no usable dynamic range.

## Phase 3 — Synthesize

Read the per-dimension findings, not just the winner. When `axis-density` won on
`density` while `baseline` won on `hierarchy`, graft them and run the graft against
the champion as one final pair.

This step also covers the known weakness of varying one axis at a time: interaction
effects are invisible to a fractional design, and the graft is where a combination
that beats both parents shows up.

## Phase 4 — Promote

Winner moves to `design/prototype/<surface>.html` and gains an entry in
`critic-map.json`. From here the ordinary conformance loop applies and this skill is
done.

Record the axis decisions the tournament settled. That record is the durable output —
more valuable than the HTML, because it transfers to every future surface.

## Applying this to non-visual work

The mechanism is medium-agnostic; only the rendering changes. For API design,
generate N designs, render each as a normalised HTTP request/response transcript, and
compare on `error-shape`, `naming coherence`, `pagination & idempotency`,
`discoverability` — never on status codes or schema validity, which OpenAPI tooling
already decides.

The blinding objection that rules out API *conformance* — that generated and shipped
code carry different fingerprints, so the critic infers which is real and defers to
it — does not apply here, because in a tournament both sides are generated from the
same brief.

Do not build a second lens until the first has cleared its gates.

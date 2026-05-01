# How the `deploy-to-huggingface` Skill Was Created

This doc captures the reasoning and the recipe behind the skill at
[.claude/skills/deploy-to-huggingface/SKILL.md](.claude/skills/deploy-to-huggingface/SKILL.md).
The goal: take a working ad-hoc deploy flow (script + markdown steps) and
turn it into a reusable Claude Code skill that any future session can
invoke automatically.

---

## What is a Claude Code skill?

A **skill** is a markdown file with YAML frontmatter that Claude can
load on demand to specialize its behavior for a task. It lives at:

- **Project-scoped:** `.claude/skills/<skill-name>/SKILL.md` — only
  available in this repo, ships with the codebase, version-controlled.
- **User-scoped:** `~/.claude/skills/<skill-name>/SKILL.md` — available
  across all projects for one user.

When the user types `/deploy-to-huggingface` (or describes a task that
matches the `description` field), Claude loads the skill body as
context and follows the steps inside.

The frontmatter is what makes a skill discoverable — it must contain at
minimum:

```yaml
---
name: <kebab-case-name>
description: <one-line summary of when to use this skill>
---
```

The `description` is critical. Claude uses it to decide whether to load
the skill, so it should:
1. Lead with the verb (what it does).
2. Name 3–5 trigger phrases the user might say.
3. Mention prerequisites that disqualify the skill (e.g. "requires a
   Dockerfile at repo root").

---

## Why turn this particular flow into a skill?

The Hugging Face deploy had three artefacts already:

1. **`infra/deploy_huggingface.py`** — the executable.
2. **`HUGGINGFACE_DEPLOYMENT.md`** — long-form human steps.
3. **In-chat tribal knowledge** — the Windows UTF-8 bug, the buffering
   bug, where to find the run logs.

Without a skill, the third bucket gets lost between sessions. A skill
turns it into context Claude reloads automatically the next time
someone asks to redeploy.

---

## Recipe — converting a flow into a skill

### 1. Identify the artefacts the skill wraps

| Artefact | Role |
|---|---|
| Script | The executable (must be idempotent — re-running shouldn't break state). |
| Long-form doc | The "why" and one-time setup (token generation, permissions). |
| Skill | The "how to drive it" — verifies preconditions, runs it, watches for known failures. |

The skill should not duplicate the long-form doc — it should *link* to
it. Claude can read linked files when needed.

### 2. Write the description for discovery, not for humans

Bad:
> "Deployment skill for Hugging Face."

Good:
> "Deploys a FastAPI Docker backend to a Hugging Face Space — creates
> the Space (idempotent), injects GOOGLE_API_KEY as a runtime secret,
> uploads the repo, and polls /health until the Space is live. Use when
> the user says 'deploy to hugging face', 'push to HF Spaces', 'host
> the backend on HF'…"

Claude scans descriptions to decide whether to load. Phrases the user
might *actually* say beat formal terminology.

### 3. Encode preconditions as verification commands

The `## Prerequisites` section uses `grep` and `ls` checks rather than
prose. Claude can execute those checks before running the script,
catching missing config before it produces a confusing error.

```markdown
1. **`.env` contains the four required keys.** Check with:
   ```bash
   grep -E "^(HF_TOKEN|HF_USERNAME|HF_SPACE_NAME|GOOGLE_API_KEY)=" .env
   ```
```

### 4. Capture failures we already saw

The "Known failure modes" table is the most valuable part of any skill.
It encodes lessons from real runs that prose docs tend to bury:

- **`UnicodeEncodeError`** — Windows-only, only manifests when stdout
  is piped to a file (which is what `run_in_background` does).
- **0-byte output file** — Python block-buffers stdout when not a TTY.
  The fix (`PYTHONUNBUFFERED=1` + `python -u`) belongs in the skill
  because the next person hitting it will think the script hung.

### 5. Spell out the success contract

Don't say "deploy succeeded." Say:

> Mark the deploy complete only after `curl /health` returns 200.

Without an explicit success contract, agents have a tendency to declare
victory on script exit code 0 even when the underlying service is dead.

### 6. List what the skill does NOT do

Skills are bounded scopes. Stating the boundaries (frontend deploy,
teardown, git commit) prevents future Claude from over-reaching when
the user says "deploy everything."

---

## The exact files I created

```
.claude/
└── skills/
    └── deploy-to-huggingface/
        └── SKILL.md            # the skill itself
SKILL_CREATION.md               # this doc
```

`SKILL.md` itself is ~120 lines split into:

1. **Frontmatter** — `name` + discovery `description`.
2. **Prerequisites** — four bash checks that must pass.
3. **How to run** — the one canonical command, with a "why these env
   vars matter" note.
4. **Background + monitor recipe** — concrete instructions for running
   under Claude Code's Bash + Monitor tools.
5. **Expected event sequence** — what success looks like, line by line.
6. **Verification** — the curl that confirms it really worked.
7. **Known failure modes** — table of symptom → cause → fix.
8. **What it does NOT do** — explicit scope boundary.
9. **After successful deploy** — follow-up actions, including secret
   rotation reminders.
10. **File map** — relative links to the four artefacts.

---

## Testing the skill

After committing, in a fresh Claude Code session in this repo:

```
/deploy-to-huggingface
```

Claude should:
1. Run the prerequisite checks.
2. Report any missing config.
3. Run the script in the background with the right env vars.
4. Arm the Monitor on the output file.
5. Stream the four step events.
6. Confirm with `curl /health`.

If any step is unclear in `SKILL.md`, that's a bug in the skill, not in
Claude — fix the skill so the next run is unambiguous.

---

## Patterns to reuse in other skills

A few habits from this skill that generalize:

- **Always include a "Known failure modes" table.** It's where the
  unique value lives. Anyone can write the happy path; only the people
  who lived through the failures can document them.
- **Encode preconditions as commands, not prose.** `grep -E "^(KEY)="
  .env` is precise; "make sure your env has the right keys" is not.
- **Make the success contract explicit and external.** A `curl` against
  the live URL is the truth; the script exit code is a guess.
- **Link to long-form docs instead of duplicating.** Skills should be
  readable in one screen. Anything longer goes into a companion `.md`.
- **State what the skill won't do.** Bounded scope = predictable agent
  behavior.

---

## When NOT to make a skill

Don't turn every script into a skill. The bar:

- The flow has multiple non-obvious failure modes worth pre-loading.
- It's likely to be re-run by a future Claude session, not just once.
- The script needs human-judgement guard-rails (preconditions,
  success contract) that aren't captured in code.

A one-shot script that runs cleanly with `--help` doesn't need a skill;
it needs good `--help`.

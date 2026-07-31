# Working this repo with two agents

This project is built by two Claude surfaces with different **access**, not
different intelligence. Same model family; what differs is what each can
touch. Assign work by access, and keep one shared substrate of method so
whichever agent is driving inherits the same discipline.

## The split

| | Claude Code (terminal, your machine) | Cowork (sandboxed, mounted folder) |
|---|---|---|
| Runs `npm`, `next dev`, `pnpm` | ✅ | ❌ (no registry access — verified) |
| Hits `localhost`, sees dev-server errors | ✅ | ❌ |
| Screenshots the UI, iterates visually | ✅ (Playwright) | ❌ |
| SSHs to the VPS, runs `lncli`, `systemctl` | ✅ | ❌ |
| Installs packages, long refactors, watch loops | ✅ | limited |
| Web search + fetch during research | limited | ✅ |
| Reads the archive and runs experiments | ✅ | ✅ |
| Long analytical sessions, writing, review | ✅ | ✅ |

**Rule of thumb:** if the task needs a package manager, a running server, a
browser, or a remote host — Claude Code. If it needs judgment about whether a
number means anything — either, but that's where this repo's method lives.

## Suggested ownership

```
app/  components/  lib/        → Claude Code   (Next.js, build, deploy, visual polish)
deploy/                        → Claude Code   (VPS, systemd, LND, Caddy — needs SSH)
research/  collectors/         → Cowork        (experiments, statistics, archive)
execution/  lightning/         → either        (pure Python, testable offline)
*.md ledgers                   → whoever did the work, always
```

## The seam

The two halves meet at **one JSON contract**, not at shared code:

```
research/signal_service.py  ──HTTP──>  /api/signals, /api/forward
lightning/service.py        ──HTTP──>  /api/tips
```

The frontend never imports Python; the research layer never renders. Either
side can be rewritten without touching the other, which is what makes the
split safe. If a change needs both sides at once, change the contract first,
in its own commit, and say so in the message.

## Handoff protocol

1. **Commit before switching agents.** Both write to the same working tree;
   uncommitted work is the only way to lose something.
2. **`git pull` / re-read the ledgers when starting.** The ledgers are the
   memory. `DECISIONS.md` is design law, `research/experiments.md` is what is
   known, `RESEARCH_PLAN.md` is what's next.
3. **New findings go in a ledger, not in chat.** A result that lives only in
   a terminal scrollback did not happen.
4. **Kill criteria are written before the run**, by whoever proposes it.

## What actually makes the frontend "hall of fame"

Worth saying plainly, because it changes the brief: this project's
distinguishing asset is that it **repeatedly refused to fool itself** — five
experiments, five honest nulls, including one where the study caught a bug in
its own control and then a test caught a bug in the fix. A generic slick
dashboard buries that. The frontend job is to make the *epistemics* legible:

- the forward-paper equity curve against buy-and-hold, live and unretouchable
- the experiment ledger rendered with its corpses visible, not hidden
- every number carrying its interval and sample size (the renderer already
  refuses bare percentages elsewhere in this codebase — match that here)
- the narrator explaining today's position in plain language

Polish serves that. Animation that obscures it is a regression.

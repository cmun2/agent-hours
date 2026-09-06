# agent-hours

**Your agent worked for four hours. It cannot tell you what it spent them on.**

Claude Code and Codex both write a full record of every session — every tool call, every result,
every timestamp — and then show you none of it once the session ends. `agent-hours` reads those
files and answers the questions the live output never does.

```console
python3 agenthours.py            # the session you just finished
python3 agenthours.py --list     # everything on this machine
python3 agenthours.py --all 5    # the last five
```

Standard library only. Nothing to install, no instrumentation, no configuration — the data is
already on your disk.

## What it tells you

```
  c7bc7b22   275 tool calls   1h 23m active   over 12h 28m

  WHERE THE TIME WENT
    running tools    █████·······················   14m 00s    17%
    model thinking   ███████████████████████·····    1h 09m    83%

  BY TOOL
    tool               calls     total   median   slowest
    Bash                  85   13m 35s       3s    1m 20s
    Write                 88       14s       0s        7s
    Edit                  71        6s       0s        0s

  SLOWEST SINGLE CALLS
      1m 20s  Bash            git init -b main && pnpm create next-app@late…
         48s  Bash            pnpm lint 2>&1 | tail -2 && pnpm typecheck 2>…

  RAN AGAIN  (76 calls were a repeat of one already made)
      14×  Write           …/src/components/ProjectCard.tsx
      14×  Edit            …/src/components/ProjectCard.tsx

  FAILED  (12 of 275, 4.4%)
```

Four things are worth having, and none of them survive the session today.

**Where the time actually went.** A run that felt slow is usually the model thinking, not the tools
running, and the split is not a thing you can eyeball from a spinner. Idle gaps longer than five
minutes are dropped, so leaving a session open overnight does not distort the number.

**Which tool costs you.** Total, median and slowest per tool. The median is usually tiny and the
slowest is a minute — that spread is the thing to fix, and an average would hide it.

**What ran again.** The same command, the same file edited over and over. This is the closest thing
to a measure of an agent going in circles, and it is invisible while it happens.

**What actually failed.** Only the calls the transcript flags as errors, plus interrupted ones and
output that names a real failure. A tool writing to stderr is not a failure — counting it as one put
the error rate at 56% in an early version of this, against a true 1.9%.

## Both CLIs

| | where it reads from |
|---|---|
| Claude Code | `~/.claude/projects/*/*.jsonl` |
| Codex | `~/.codex/sessions/*/*/*/rollout-*.jsonl` |

`--list` shows both, newest first. `--from claude` or `--from codex` narrows it. Pass a path
directly to read one file.

Durations are derived, not recorded: a call starts when the agent emits it and ends when its result
comes back, both of which carry a timestamp. Claude Code stores a `durationMs` on roughly one call
in eight hundred, so deriving it is the only way to have the number at all.

`AskUserQuestion` and `ExitPlanMode` are counted separately, under "waiting on you" — a person
deciding is not the agent being slow.

## License

MIT.

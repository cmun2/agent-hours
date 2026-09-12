#!/usr/bin/env python3
"""Where the time went in an agent session.

Reads the session files Claude Code and Codex already write, and answers the
questions their live output cannot: which tool ate the clock, what ran again
and again, what actually failed. Standard library only.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import statistics
import sys
from datetime import datetime, timedelta

# A gap longer than this is the session sitting idle, not the agent working.
IDLE_GAP = timedelta(minutes=5)
# Tools whose duration is a person deciding, not a machine running.
HUMAN_TOOLS = {"AskUserQuestion", "ExitPlanMode"}
# stderr is not failure -- plenty of well-behaved commands write to it.
FAILURE = re.compile(
    r"(?i)\b(command not found|no such file|permission denied|fatal:|"
    r"traceback \(most recent call last\)|segmentation fault)\b"
)


def parse_time(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


class Call:
    __slots__ = ("tool", "started", "ended", "failed", "detail")

    def __init__(self, tool, started, ended, failed, detail):
        self.tool, self.started, self.ended = tool, started, ended
        self.failed, self.detail = failed, detail

    @property
    def seconds(self):
        return (self.ended - self.started).total_seconds()


class Session:
    def __init__(self, path, label, calls, stamps):
        self.path, self.label, self.calls = path, label, calls
        self.stamps = sorted(s for s in stamps if s)

    @property
    def span(self):
        return (self.stamps[-1] - self.stamps[0]) if len(self.stamps) > 1 else timedelta()

    @property
    def active(self):
        """Wall-clock minus the gaps where nothing happened."""
        return sum(
            (b - a).total_seconds()
            for a, b in zip(self.stamps, self.stamps[1:])
            if (b - a) < IDLE_GAP
        )

    @property
    def tool_seconds(self):
        return sum(c.seconds for c in self.calls if c.tool not in HUMAN_TOOLS)

    @property
    def human_seconds(self):
        return sum(c.seconds for c in self.calls if c.tool in HUMAN_TOOLS)


def _shorten(text, width=64):
    """Trim to width. A path loses its head, since the tail is the part that
    identifies it; anything else loses its tail."""
    text = " ".join(str(text or "").split())
    if len(text) <= width:
        return text
    if text.startswith(("/", "~", "./")) and " " not in text:
        return "…" + text[-(width - 1):]
    return text[: width - 1] + "…"


def read_claude(path):
    """Claude Code writes one JSON object per line; tool calls and their results
    are separate records, paired by the tool_use id."""
    calls, results, stamps = {}, {}, []
    with open(path, errors="ignore") as handle:
        for line in handle:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            when = parse_time(rec.get("timestamp"))
            if when:
                stamps.append(when)
            content = (rec.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    calls[block.get("id")] = (block.get("name"), when, block.get("input") or {})
                elif block.get("type") == "tool_result":
                    results[block.get("tool_use_id")] = (
                        when, rec.get("toolUseResult"), bool(block.get("is_error"))
                    )
    out = []
    for cid, (tool, started, args) in calls.items():
        got = results.get(cid)
        if not got or not started or not got[0]:
            continue
        ended, payload, flagged = got
        failed = flagged
        if isinstance(payload, dict):
            if payload.get("interrupted"):
                failed = True
            err = payload.get("stderr")
            if isinstance(err, str) and FAILURE.search(err):
                failed = True
        detail = args.get("command") or args.get("file_path") or args.get("query") or args.get("path") or ""
        out.append(Call(tool, started, ended, failed, str(detail)))
    return Session(path, os.path.basename(path)[:8], out, stamps)


def read_codex(path):
    """Codex writes a rollout log: response items carry the calls, and every
    record carries a timestamp, so a call is paired with the output that follows it."""
    calls, results, stamps = {}, {}, []
    with open(path, errors="ignore") as handle:
        for line in handle:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            when = parse_time(rec.get("timestamp"))
            if when:
                stamps.append(when)
            payload = rec.get("payload")
            if not isinstance(payload, dict):
                continue
            kind = payload.get("type")
            if kind in ("function_call", "custom_tool_call", "local_shell_call"):
                cid = payload.get("call_id") or payload.get("id")
                name = payload.get("name") or kind
                args = payload.get("arguments") or payload.get("input") or ""
                calls[cid] = (name, when, args)
            elif kind in ("function_call_output", "custom_tool_call_output", "local_shell_call_output"):
                cid = payload.get("call_id") or payload.get("id")
                results[cid] = (when, payload.get("output"))
    out = []
    for cid, (tool, started, args) in calls.items():
        got = results.get(cid)
        if not got or not started or not got[0]:
            continue
        ended, output = got
        text = output if isinstance(output, str) else json.dumps(output or "")
        out.append(Call(tool, started, ended, bool(FAILURE.search(text)), _shorten(args, 200)))
    return Session(path, os.path.basename(path)[:24], out, stamps)


def discover(kind):
    homes = {
        "claude": os.path.expanduser("~/.claude/projects/*/*.jsonl"),
        "codex": os.path.expanduser("~/.codex/sessions/*/*/*/rollout-*.jsonl"),
    }
    found = []
    for name, pattern in homes.items():
        if kind in (None, name):
            found += [(name, p) for p in glob.glob(pattern)]
    return sorted(found, key=lambda pair: os.path.getmtime(pair[1]), reverse=True)


def clock(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    return f"{seconds // 3600}h {seconds % 3600 // 60:02d}m"


def bar(fraction, width=28):
    filled = max(0, min(width, round(fraction * width)))
    return "█" * filled + "·" * (width - filled)


def report(session, out=sys.stdout, top=8):
    calls = session.calls
    write = lambda line="": print(line, file=out)

    write(f"\n  {session.label}   {len(calls)} tool calls   "
          f"{clock(session.active)} active   over {clock(session.span.total_seconds())}")
    write()

    if not calls:
        write("  Nothing paired up in this file — no completed tool calls to measure.")
        return

    # ── where the time went ─────────────────────────────────────────────
    active = session.active or 1
    tool_s, human_s = session.tool_seconds, session.human_seconds
    thinking = max(0.0, active - tool_s - human_s)
    write("  WHERE THE TIME WENT")
    for name, secs in (("running tools", tool_s), ("model thinking", thinking),
                       ("waiting on you", human_s)):
        if secs <= 0:
            continue
        write(f"    {name:<16} {bar(secs / active)}  {clock(secs):>8}  {secs / active * 100:4.0f}%")
    write()

    # ── which tool ──────────────────────────────────────────────────────
    grouped = collections.defaultdict(list)
    for call in calls:
        grouped[call.tool].append(call.seconds)
    write("  BY TOOL")
    write(f"    {'tool':<18}{'calls':>6}{'total':>10}{'median':>9}{'slowest':>10}")
    for tool, spans in sorted(grouped.items(), key=lambda kv: -sum(kv[1]))[:top]:
        write(f"    {tool[:18]:<18}{len(spans):>6}{clock(sum(spans)):>10}"
              f"{clock(statistics.median(spans)):>9}{clock(max(spans)):>10}")
    write()

    # ── the individual calls that hurt ──────────────────────────────────
    slow = sorted((c for c in calls if c.tool not in HUMAN_TOOLS),
                  key=lambda c: -c.seconds)[:top]
    if slow and slow[0].seconds >= 5:
        write("  SLOWEST SINGLE CALLS")
        for call in slow:
            if call.seconds < 5:
                break
            write(f"    {clock(call.seconds):>8}  {call.tool:<16}{_shorten(call.detail, 46)}")
        write()

    # ── work that happened more than once ───────────────────────────────
    repeats = collections.Counter()
    for call in calls:
        if call.detail:
            repeats[(call.tool, _shorten(call.detail, 90))] += 1
    again = [(k, n) for k, n in repeats.most_common() if n > 2][:top]
    if again:
        total_repeat = sum(n - 1 for _, n in repeats.items() if n > 1)
        write(f"  RAN AGAIN  ({total_repeat} calls were a repeat of one already made)")
        for (tool, detail), count in again:
            write(f"    {count:>4}×  {tool:<16}{_shorten(detail, 46)}")
        write()

    # ── failures ────────────────────────────────────────────────────────
    failed = [c for c in calls if c.failed]
    if failed:
        write(f"  FAILED  ({len(failed)} of {len(calls)}, {len(failed) / len(calls) * 100:.1f}%)")
        for call in failed[:top]:
            write(f"    {call.tool:<16}{_shorten(call.detail, 56)}")
        if len(failed) > top:
            write(f"    … and {len(failed) - top} more")
        write()


# A gap this long inside a run is the model working; anything longer is the
# session sitting idle, and the tape skips it rather than drawing empty minutes.
IDLE_TAPE_MS = 2500


def tape(session, top_repeats=40):
    """Emit the session as an agent-tape trace.

    The viewer draws a flat list of events on a millisecond clock, so the
    timestamps here are relative to the first thing that happened. Idle gaps
    are collapsed to a fixed width and labelled with the real duration, because
    a run that sat overnight is otherwise a screen of nothing.
    """
    calls = sorted(session.calls, key=lambda c: c.started)
    if not calls:
        return {"title": session.label, "note": "No completed tool calls in this file.",
                "runs": [{"label": "run", "events": []}]}

    # Which calls repeated work already done -- the thing the CLI never shows.
    seen = collections.Counter()
    order = {}
    for call in calls:
        if call.detail:
            key = (call.tool, _shorten(call.detail, 90))
            seen[key] += 1
            order[id(call)] = (key, seen[key])

    events = []
    clock_ms = 0.0
    previous = None
    skipped = 0.0

    def add(t, lane, type_, label=None, **meta):
        event = {"t": int(round(t)), "lane": lane, "type": type_}
        if label is not None:
            event["label"] = label
        meta = {k: v for k, v in meta.items() if v not in (None, "", 0)}
        if meta:
            event["meta"] = meta
        events.append(event)

    for index, call in enumerate(calls):
        if previous is not None:
            gap = (call.started - previous).total_seconds()
            if gap < 0:
                gap = 0.0
            if gap >= IDLE_GAP.total_seconds():
                add(clock_ms, "run", "run.idle", f"idle {clock(gap)} — not drawn to scale")
                skipped += gap
                clock_ms += IDLE_TAPE_MS
            else:
                if gap > 0:
                    add(clock_ms, "model", "model.started", took=clock(gap) if gap >= 1 else None)
                clock_ms += gap * 1000

        held = call.tool in HUMAN_TOOLS
        cid = f"c{index}"
        took = call.seconds

        if held:
            add(clock_ms, "run", "approval.requested", call.tool)
        else:
            # Only the second and later runs of the same work are a repeat; the
            # first time is just the work. This is the count report() prints.
            nth = order.get(id(call))
            again = None
            if nth and nth[1] > 1:
                again = f"{nth[1]} of {seen[nth[0]]}"
            add(clock_ms, "tool", "tool.call", call.tool,
                detail=_shorten(call.detail, 72) or None, again=again)
            events[-1]["id"] = cid

        clock_ms += took * 1000

        if held:
            add(clock_ms, "user", "approval.granted", f"after {clock(took)}")
        else:
            add(clock_ms, "tool", "tool.error" if call.failed else "tool.result",
                call.tool, took=clock(took) if took >= 1 else None)
            events[-1]["id"] = cid

        previous = call.ended

    add(clock_ms, "run", "run.completed", None,
        calls=len(calls), active=clock(session.active),
        wall=clock(session.span.total_seconds()),
        idle_skipped=clock(skipped) if skipped else None)

    failed = sum(1 for c in calls if c.failed)
    repeated = sum(n - 1 for n in seen.values() if n > 1)
    note = (f"{len(calls)} tool calls, {clock(session.active)} active over "
            f"{clock(session.span.total_seconds())}. "
            f"{repeated} calls repeated work already done; {failed} failed.")
    if skipped:
        note += f" Idle gaps totalling {clock(skipped)} are collapsed, not drawn to scale."
    return {"title": f"{session.label} — {os.path.basename(session.path)}",
            "note": note, "runs": [{"label": "run", "events": events}]}


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="agent-hours",
        description="Where the time went in a Claude Code or Codex session.")
    ap.add_argument("session", nargs="?", help="session file; omitted means the most recent")
    ap.add_argument("--list", action="store_true", help="list recent sessions and stop")
    ap.add_argument("--from", dest="kind", choices=("claude", "codex"), help="only this CLI")
    ap.add_argument("--all", type=int, metavar="N", help="report on the N most recent sessions")
    ap.add_argument("--top", type=int, default=8, help="rows per section (default 8)")
    ap.add_argument("--tape", action="store_true",
                    help="emit the session as a trace for viewer/index.html instead of a report")
    ap.add_argument("--out", metavar="FILE", help="write the trace here instead of stdout")
    args = ap.parse_args(argv)

    readers = {"claude": read_claude, "codex": read_codex}

    def emit(session):
        if not args.tape:
            report(session, top=args.top)
            return
        payload = json.dumps(tape(session), ensure_ascii=False, indent=1)
        if args.out:
            with open(args.out, "w") as handle:
                handle.write(payload + "\n")
            print(f"Wrote {args.out}. Open viewer/index.html and drop it on the page.",
                  file=sys.stderr)
        else:
            print(payload)

    if args.session:
        path = args.session
        kind = args.kind or ("codex" if "codex" in path else "claude")
        emit(readers[kind](path))
        return 0

    found = discover(args.kind)
    if not found:
        print("No sessions found under ~/.claude/projects or ~/.codex/sessions.", file=sys.stderr)
        return 1

    if args.list:
        print(f"\n  {'when':<17}{'from':<9}{'size':>8}  session")
        for kind, path in found[:25]:
            when = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
            size = f"{os.path.getsize(path) / 1024:.0f}K"
            print(f"  {when:<17}{kind:<9}{size:>8}  {path}")
        print()
        return 0

    if args.tape and (args.all or 1) > 1:
        print("--tape reads one session at a time; pass a path or drop --all.", file=sys.stderr)
        return 1

    for kind, path in found[: args.all or 1]:
        emit(readers[kind](path))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Command line: run / review / mark / eval / auth.

Nothing here sends mail or posts a comment. `run` writes only when --stage is given:
Gmail -> a draft in your Drafts folder; comment channels -> the local approval queue.
"""
from __future__ import annotations

import argparse
import sys

from .adapters import CHANNELS, AdapterError, build_adapter
from .config import Settings
from .pipeline import judge_first
from .privacy import redact_secrets
from .providers import build_drafter, build_judge
from .store import Store


def _out(text: str = "") -> None:
    enc = sys.stdout.encoding or "utf-8"
    sys.stdout.write(text.encode(enc, "replace").decode(enc, "replace") + "\n")


def _providers(args, s: Settings):
    notes: list[str] = []
    judge = build_judge(s, force_mock=args.mock, strict=args.strict, notes=notes)
    drafter = build_drafter(s, force_mock=args.mock, strict=args.strict, notes=notes)
    for n in notes:
        _out(f"[note] {redact_secrets(n)}")
    _out(f"[providers] judge={judge.name}/{judge.model} drafter={drafter.name}/{drafter.model}")
    return judge, drafter


def cmd_run(args) -> int:
    s = Settings.from_env()
    if args.dry_run and args.stage:
        _out("--dry-run and --stage are exclusive")
        return 2
    staging = bool(args.stage)
    channel = args.channel or "fixtures"
    judge, drafter = _providers(args, s)
    try:
        adapter = build_adapter(channel, s)
        msgs = adapter.fetch(args.limit)
    except AdapterError as exc:
        _out(f"[error] {redact_secrets(exc)}")
        return 1
    store = Store(s.data_dir / "state.db") if staging else None
    owner = {"name": s.owner_name, "style": s.owner_style}
    _out(f"[run] channel={channel} messages={len(msgs)} mode={'STAGE' if staging else 'DRY RUN (nothing is written)'}")
    for msg in msgs:
        if store and store.is_seen(channel, msg.id):
            continue
        o = judge_first(msg, judge, drafter, s.thresholds, owner)
        j = o.judgment
        head = f"\n== {msg.id} | {msg.sender} | {msg.subject or msg.context}"[:160]
        _out(head)
        if j:
            _out(f"   judge: action={j.best_action} intent={j.intent} wants={j.sender_wants} "
                 f"tension={j.tension:.0f}/9 reply_now={j.reply_now:.2f} spam={j.spam:.2f} abusive={j.abusive:.2f}")
        _out(f"   decision: {o.decision}  ({o.total_ms} ms, cost {o.total_cost if o.total_cost is not None else 'unknown'})")
        for w in o.warnings:
            _out(f"   ! {redact_secrets(w)}")
        for i, c in enumerate(o.candidates):
            mark = "*" if i == 0 else " "
            score = f"{c.score:.2f}" if c.score is not None else " -- "
            _out(f"   {mark} [{score}] {c.text}")
        if store:
            store.save_outcome(channel, o.to_dict())
            if o.best:
                try:
                    note = adapter.stage(msg, o.best, store)
                    _out(f"   staged: {note}")
                except Exception as exc:  # keep going; the message stays unseen and is retried next run
                    _out(f"   [stage failed] {redact_secrets(type(exc).__name__)}: {redact_secrets(exc)}"[:300])
                    continue
            store.mark_seen(channel, msg.id)
    if store:
        store.close()
    return 0


def cmd_review(args) -> int:
    s = Settings.from_env()
    store = Store(s.data_dir / "state.db")
    rows = store.pending(args.channel)
    if not rows:
        _out("승인 대기 중인 답글이 없습니다.")
    for r in rows:
        _out(f"#{r['id']} [{r['channel']}] {r['sender']}: {(r['original'] or '')[:120]}")
        _out(f"    제안 답글: {r['reply']}")
        if r["link"]:
            _out(f"    열기: {r['link']}")
    if rows:
        _out("\n답글은 직접 복사해 올리세요. 처리 후: python -m reply_copilot mark <번호> done|dismissed")
    store.close()
    return 0


def cmd_mark(args) -> int:
    s = Settings.from_env()
    store = Store(s.data_dir / "state.db")
    ok = store.set_status(args.id, args.status)
    store.close()
    _out("ok" if ok else f"no queue item #{args.id}")
    return 0 if ok else 1


def cmd_eval(args) -> int:
    from .evaluation import run_eval, save, to_markdown

    s = Settings.from_env()
    if not args.real:
        args.mock = True
    judge, drafter = _providers(args, s)
    mode = "mock" if judge.name.startswith("mock") and drafter.name.startswith("mock") else (
        "real" if not judge.name.startswith("mock") and not drafter.name.startswith("mock") else "partial")
    result = run_eval(judge, drafter, s, mode=mode)
    if args.no_save:
        _out(to_markdown(result))
        return 0
    j, m = save(result)
    _out(to_markdown(result).split("## 메시지별")[0])
    _out(f"saved: {j}\n       {m}")
    return 0


def cmd_auth(args) -> int:
    s = Settings.from_env()
    try:
        build_adapter(args.channel, s, interactive=True)
    except AdapterError as exc:
        _out(f"[error] {redact_secrets(exc)}")
        return 1
    _out(f"{args.channel}: token saved under {s.token_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="reply-copilot", description="Judge-first reply drafts. Never sends.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def provider_flags(sp):
        sp.add_argument("--mock", action="store_true", help="use mock judge and drafter (no keys, no network)")
        sp.add_argument("--strict", action="store_true", help="fail instead of falling back to mocks")

    r = sub.add_parser("run", help="read new messages, judge, draft")
    r.add_argument("--channel", choices=sorted(CHANNELS), default="fixtures")
    r.add_argument("--limit", type=int, default=10)
    r.add_argument("--dry-run", action="store_true", help="print only; write nothing anywhere (default)")
    r.add_argument("--stage", action="store_true",
                   help="save best reply: Gmail draft, or the local approval queue for comments")
    provider_flags(r)
    r.set_defaults(func=cmd_run)

    v = sub.add_parser("review", help="list comment replies waiting for your approval")
    v.add_argument("--channel", choices=sorted(CHANNELS))
    v.set_defaults(func=cmd_review)

    m = sub.add_parser("mark", help="mark a queue item done or dismissed")
    m.add_argument("id", type=int)
    m.add_argument("status", choices=["done", "dismissed", "pending"])
    m.set_defaults(func=cmd_mark)

    e = sub.add_parser("eval", help="judge-first vs draft-direct on eval/fixtures")
    e.add_argument("--real", action="store_true", help="use configured providers (needs keys)")
    e.add_argument("--no-save", action="store_true")
    provider_flags(e)
    e.set_defaults(func=cmd_eval)

    a = sub.add_parser("auth", help="one-time OAuth for a Google channel")
    a.add_argument("channel", choices=["gmail", "youtube"])
    a.set_defaults(func=cmd_auth)

    args = p.parse_args(argv)
    if not sys.stdout.isatty():  # pipes and files get UTF-8, whatever the console code page
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

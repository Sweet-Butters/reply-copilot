"""Offline eval: "judge first, then draft" vs "draft directly" on the same fixtures.

Scored automatically (no model grades itself):
- routing: did a pipeline write drafts for messages that need none (spam, abuse, bulk), or skip ones that do?
- action agreement: does the judge's best_action match the fixture's expected actions?
- cost: provider calls, tokens, latency, USD.
Reply quality is left to a human: the report prints both pipelines' best reply side by side.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime
from pathlib import Path

from .adapters.fixtures import FIXTURE_DIR, load_fixtures, to_message
from .config import ROOT, Settings
from .models import Outcome
from .pipeline import draft_direct, judge_first

RESULTS_DIR = ROOT / "eval" / "results"


def _summary(outcomes: list[Outcome], fixtures: list[dict]) -> dict:
    exp = {f["id"]: f for f in fixtures}
    drafted = [o for o in outcomes if o.decision == "draft"]
    no = [o for o in outcomes if exp[o.message_id]["expect_reply"] == "no"]
    yes = [o for o in outcomes if exp[o.message_id]["expect_reply"] == "yes"]
    usages = [u for o in outcomes for u in o.usage]
    per_msg_ms = [o.total_ms for o in outcomes]
    costs = [u.cost_usd for u in usages]
    judged = [o for o in outcomes if o.judgment]
    s = {
        "messages": len(outcomes),
        "drafted": len(drafted),
        "wasted_drafts_on_no_reply": sum(1 for o in no if o.decision == "draft"),
        "correct_skips": sum(1 for o in no if o.decision != "draft"),
        "missed_needed_replies": sum(1 for o in yes if o.decision != "draft"),
        "errors": sum(1 for o in outcomes if o.decision == "error"),
        "calls": {r: sum(1 for u in usages if u.role == r) for r in ("judge", "draft", "rank")},
        "input_tokens": sum(u.input_tokens for u in usages),
        "output_tokens": sum(u.output_tokens for u in usages),
        "cost_usd": None if any(c is None for c in costs) else round(sum(costs), 6),
        "latency_ms_per_message": {
            "p50": round(statistics.median(per_msg_ms)) if per_msg_ms else None,
            "mean": round(statistics.fmean(per_msg_ms)) if per_msg_ms else None,
            "max": max(per_msg_ms) if per_msg_ms else None,
        },
        "high_tension_warned": [o.message_id for o in outcomes
                                if any("직접 쓰세요" in w for w in o.warnings)],
    }
    if judged:
        s["action_agreement"] = round(sum(
            1 for o in judged if o.judgment.best_action in exp[o.message_id]["expected_actions"]) / len(judged), 3)
    return s


def run_eval(judge, drafter, settings: Settings, fixture_dir: Path = FIXTURE_DIR, mode: str = "mock") -> dict:
    fixtures = load_fixtures(fixture_dir)
    owner = {"name": settings.owner_name or "정회광", "style": settings.owner_style}
    jf, dd = [], []
    for f in fixtures:
        msg = to_message(f)
        jf.append(judge_first(msg, judge, drafter, settings.thresholds, owner))
        dd.append(draft_direct(msg, drafter, owner))
    return {
        "mode": mode,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "judge": f"{judge.name}/{judge.model}",
        "drafter": f"{drafter.name}/{drafter.model}",
        "fixtures": len(fixtures),
        "summary": {"judge_first": _summary(jf, fixtures), "draft_direct": _summary(dd, fixtures)},
        "items": [
            {"id": f["id"], "expect_reply": f["expect_reply"], "expected_actions": f["expected_actions"],
             "judge_first": a.to_dict(), "draft_direct": b.to_dict()}
            for f, a, b in zip(fixtures, jf, dd)
        ],
    }


def _fmt_cost(c) -> str:
    return "unknown" if c is None else f"${c:.6f}"


def to_markdown(r: dict) -> str:
    a, b = r["summary"]["judge_first"], r["summary"]["draft_direct"]
    lines = [
        f"# 평가 결과 ({r['mode']})",
        "",
        f"- 실행: {r['run_at']}",
        f"- 판단: `{r['judge']}` / 작성: `{r['drafter']}`",
        f"- 픽스처: {r['fixtures']}개 (가상 한국어 메시지, `eval/fixtures/`)",
    ]
    if r["mode"] == "mock":
        lines += ["", "> **mock 모드**: 규칙 기반 판단과 템플릿 초안입니다. 하네스가 끝까지 돈다는 것만 보여 주며, "
                  "정확도·지연·비용 숫자는 실제 모델 성능이 아닙니다. 규칙은 픽스처를 보고 썼으므로 일치율이 높게 나오는 게 당연합니다."]
    lines += [
        "",
        "| 지표 | 판단 먼저 | 바로 작성 |",
        "|---|---|---|",
        f"| 초안을 만든 메시지 | {a['drafted']} | {b['drafted']} |",
        f"| 답장 불필요(스팸·악플·광고)에 초안 낭비 | {a['wasted_drafts_on_no_reply']} | {b['wasted_drafts_on_no_reply']} |",
        f"| 답장이 필요한데 건너뜀 | {a['missed_needed_replies']} | {b['missed_needed_replies']} |",
        f"| 작성 모델 호출 | {a['calls']['draft']} | {b['calls']['draft']} |",
        f"| 판단/순위 호출 | {a['calls']['judge']}/{a['calls']['rank']} | 0/0 |",
        f"| 입력/출력 토큰 | {a['input_tokens']}/{a['output_tokens']} | {b['input_tokens']}/{b['output_tokens']} |",
        f"| 비용 | {_fmt_cost(a['cost_usd'])} | {_fmt_cost(b['cost_usd'])} |",
        f"| 메시지당 지연 p50/평균/최대 (ms) | {a['latency_ms_per_message']['p50']}/{a['latency_ms_per_message']['mean']}/{a['latency_ms_per_message']['max']} "
        f"| {b['latency_ms_per_message']['p50']}/{b['latency_ms_per_message']['mean']}/{b['latency_ms_per_message']['max']} |",
        f"| 판단의 best_action 일치율 | {a.get('action_agreement', '-')} | - |",
        f"| \"직접 쓰세요\" 경고 | {', '.join(a['high_tension_warned']) or '-'} | - |",
        "",
        "## 메시지별",
        "",
    ]
    for it in r["items"]:
        x, y = it["judge_first"], it["draft_direct"]
        j = x.get("judgment") or {}
        lines.append(f"### {it['id']} (기대: 답장 {it['expect_reply']}, {', '.join(it['expected_actions'])})")
        if j:
            lines.append(f"- 판단: action={j['best_action']}, intent={j['intent']}, wants={j['sender_wants']}, "
                         f"tension={j['tension']:.1f}, needs_reply={j['needs_reply']:.2f}, spam={j['spam']:.2f}, "
                         f"abusive={j['abusive']:.2f}")
        lines.append(f"- 판단 먼저 → **{x['decision']}**" + (f": {x['best']}" if x.get("best") else ""))
        for w in x.get("warnings", []):
            lines.append(f"  - 경고: {w}")
        lines.append(f"- 바로 작성 → **{y['decision']}**" + (f": {y['best']}" if y.get("best") else ""))
        lines.append("")
    return "\n".join(lines)


def save(r: dict, out_dir: Path = RESULTS_DIR) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{r['run_at'][:10]}-{r['mode']}"
    j, m = out_dir / f"{stem}.json", out_dir / f"{stem}.md"
    j.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    m.write_text(to_markdown(r), encoding="utf-8")
    return j, m

"""The two pipelines the eval compares.

judge_first:  judge -> stop early (spam / abuse / no reply needed) -> draft with guidance -> rank
draft_direct: draft 3 with no judgment and take the first (the "just ask an LLM" baseline)
"""
from __future__ import annotations

from .config import Thresholds
from .models import Candidate, Judgment, Message, Outcome
from .privacy import redact_secrets
from .providers.base import Drafter, Judge, ProviderError, filter_candidates

ACTION_KO = {
    "answer": "질문에 직접 답하기", "accept": "수락하고 다음 단계 확인", "decline_politely": "정중히 거절",
    "ask_clarification": "구체적으로 되묻기", "acknowledge": "짧게 감사/확인", "ignore": "답하지 않기",
    "escalate": "민감한 건: 확인 후 답하겠다는 수준으로만, 약속·인정은 하지 않기",
}
WANTS_KO = {
    "information": "정보/설명", "decision": "예·아니오 또는 선택", "commitment": "구체적 약속·행동",
    "apology": "사과", "acknowledgement": "들어줬다는 확인", "nothing": "없음",
}


def guidance_text(j: Judgment) -> str:
    """Judgment -> a short note the drafter must follow. Machine tag first so mocks can read it."""
    return (
        f"[judge] best_action={j.best_action} intent={j.intent} wants={j.sender_wants} "
        f"tension={j.tension:.0f}/9\n"
        f"Judge's notes (follow them): the sender wants {WANTS_KO.get(j.sender_wants, j.sender_wants)}; "
        f"best move: {ACTION_KO.get(j.best_action, j.best_action)}; tension {j.tension:.0f}/9."
    )


def judge_first(msg: Message, judge: Judge, drafter: Drafter, th: Thresholds, owner: dict) -> Outcome:
    out = Outcome(message_id=msg.id, pipeline="judge_first", decision="draft")
    judgment = None
    try:
        judgment, usage = judge.judge(msg)
        out.usage.append(usage)
        out.judgment = judgment
    except ProviderError as exc:
        out.warnings.append(f"judge failed, drafting without it: {redact_secrets(exc)}")

    if judgment:
        if judgment.spam >= th.spam_above:
            out.decision = "skip_spam"
            return out
        if judgment.abusive >= th.abusive_above:
            out.decision = "skip_abusive"
            out.warnings.append("악성 댓글로 보임: 답하지 말고 숨김/신고를 검토하세요.")
            return out
        if judgment.needs_reply < th.skip_no_reply_below or judgment.best_action == "ignore":
            out.decision = "skip_no_reply"
            return out
        if judgment.tension >= th.hand_write_tension or judgment.best_action == "escalate":
            out.warnings.append("긴장도가 높거나 민감한 건입니다. 후보는 참고만 하고 직접 쓰세요.")

    try:
        texts, usage = drafter.draft(msg, guidance_text(judgment) if judgment else None, owner)
        out.usage.append(usage)
    except ProviderError as exc:
        out.decision = "error"
        out.warnings.append(f"draft failed: {redact_secrets(exc)}")
        return out
    texts = filter_candidates(texts, msg.text)
    if not texts:
        out.decision = "error"
        out.warnings.append("no usable candidate after filtering")
        return out
    out.candidates = [Candidate(t) for t in texts]

    if len(texts) >= 2 and judgment is not None:
        try:
            probs, usage = judge.rank(msg, texts)
            out.usage.append(usage)
            for c, p in zip(out.candidates, probs):
                c.score = p
            out.candidates.sort(key=lambda c: -(c.score or 0.0))
        except ProviderError as exc:
            out.warnings.append(f"rank failed, keeping draft order: {redact_secrets(exc)}")
    out.best = out.candidates[0].text
    return out


def draft_direct(msg: Message, drafter: Drafter, owner: dict) -> Outcome:
    out = Outcome(message_id=msg.id, pipeline="draft_direct", decision="draft")
    try:
        texts, usage = drafter.draft(msg, None, owner)
        out.usage.append(usage)
    except ProviderError as exc:
        out.decision = "error"
        out.warnings.append(f"draft failed: {redact_secrets(exc)}")
        return out
    texts = filter_candidates(texts, msg.text)
    if not texts:
        out.decision = "error"
        return out
    out.candidates = [Candidate(t) for t in texts]
    out.best = texts[0]
    return out

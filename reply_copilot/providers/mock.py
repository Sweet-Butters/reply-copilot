"""Offline stand-ins: keyword rules for the judge, templates for the drafter.

They let the whole pipeline, the CLI and the eval harness run with no keys and no network.
Their "accuracy" says nothing about real models.
"""
from __future__ import annotations

import re
import time

from ..models import Judgment, Message, Usage
from ..privacy import prepare

_SPAM = re.compile(r"맞구독|구독\s*해\s*주시면|수익\s*\d+|코인|대출|카지노|bit\.ly|무료\s*증정|홍보|클릭", re.I)
_ABUSE = re.compile(r"이딴|수준\s*참|꺼져|병신|ㅄ|한심|쓰레기|닥쳐")
_QUESTION = re.compile(r"\?|궁금|문의|여쭙|어떻게|왜|가능할까요|가능한지|알려")
_SCHEDULE = re.compile(r"일정|시간\s*(괜찮|되|가능)|미팅|면담|날짜|언제")
_INVITE = re.compile(r"특강|강의\s*요청|초청|섭외|협업|제안|모시고")
_DECLINE = re.compile(r"봉사|주말.*(부탁|요청)|도와주실\s*수")
_COMPLAINT = re.compile(r"납득|이의\s*제기|항의|실망|불만|환불")
_THANKS = re.compile(r"감사합니다|고맙|좋았어요|최고|👏|잘\s*봤")
_BULK = re.compile(r"뉴스레터|수신\s*거부|unsubscribe|광고\)|\(광고", re.I)


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 2)


class MockJudge:
    name = "mock-judge"
    model = "rules-v1"

    def judge(self, msg: Message) -> tuple[Judgment, Usage]:
        t0 = time.perf_counter()
        text = f"{msg.subject}\n{msg.text}"
        spam = 0.95 if (_SPAM.search(text) or _BULK.search(text)) else 0.05
        abusive = 0.9 if _ABUSE.search(text) else 0.03
        if spam > 0.5:
            intent, wants, action, needs = "promotion", "nothing", "ignore", 0.05
        elif abusive > 0.5:
            intent, wants, action, needs = "complaint", "nothing", "ignore", 0.2
        elif _COMPLAINT.search(text):
            intent, wants, action, needs = "complaint", "information", "escalate", 0.95
        elif _INVITE.search(text):
            intent, wants, action, needs = "invitation", "decision", "ask_clarification", 0.9
        elif _DECLINE.search(text):
            intent, wants, action, needs = "request", "decision", "decline_politely", 0.85
        elif _SCHEDULE.search(text):
            intent, wants, action, needs = "scheduling", "decision", "accept", 0.9
        elif _QUESTION.search(text):
            intent, wants, action, needs = "question", "information", "answer", 0.85
        elif _THANKS.search(text):
            intent, wants, action, needs = "thanks_or_fyi", "acknowledgement", "acknowledge", 0.4
        else:
            intent, wants, action, needs = "feedback", "acknowledgement", "acknowledge", 0.3
        tension = 8.0 if abusive > 0.5 else 6.0 if intent == "complaint" else 1.0 if spam < 0.5 else 0.0
        reply_now = 0.8 if re.search(r"오늘|내일|급|ASAP|이번 주", text) else 0.2
        j = Judgment(needs_reply=needs, reply_now=reply_now, spam=spam, abusive=abusive,
                     intent=intent, sender_wants=wants, best_action=action, tension=tension,
                     confidence={"intent": 0.5, "sender_wants": 0.5, "best_action": 0.5, "tension": 0.5})
        ms = round((time.perf_counter() - t0) * 1000)
        return j, Usage("judge", self.name, self.model, ms, _est_tokens(prepare(text)), 0, 0.0)

    def rank(self, msg: Message, candidates: list[str]) -> tuple[list[float], Usage]:
        # Prefer the candidate closest to a medium length; ties keep order. Deterministic.
        target = 80 if msg.kind == "email" else 35
        dist = [abs(len(c) - target) for c in candidates]
        order = sorted(range(len(candidates)), key=lambda i: (dist[i], i))
        weights = [0.6, 0.3, 0.1][: len(candidates)]
        probs = [0.0] * len(candidates)
        for w, i in zip(weights, order):
            probs[i] = w
        return probs, Usage("rank", self.name, self.model, 0, sum(map(_est_tokens, candidates)), 0, 0.0)


_TEMPLATES = {
    "answer": ["질문 감사합니다. {topic}에 대해 답변드리면, [답변 내용]입니다.",
               "좋은 질문이에요! 간단히 말씀드리면 [답변 내용]입니다. 더 궁금한 점 있으면 편하게 물어봐 주세요.",
               "문의 주셔서 감사합니다. 확인해 보고 정확한 내용으로 다시 답변드리겠습니다."],
    "accept": ["네, 가능합니다. [날짜/시간]에 뵙겠습니다.",
               "말씀 주셔서 감사합니다. 제안해 주신 일정 괜찮습니다. [날짜/시간]으로 확정해 주시면 준비하겠습니다.",
               "좋습니다. 혹시 [날짜/시간]도 가능하시면 그때로 부탁드리고, 어려우시면 말씀하신 일정으로 맞추겠습니다."],
    "decline_politely": ["제안 감사합니다. 아쉽지만 이번에는 일정상 참여가 어렵습니다. 다음 기회에 꼭 함께하고 싶습니다.",
                         "연락 주셔서 감사합니다. 해당 기간에 이미 잡힌 일정이 있어 이번에는 정중히 사양하겠습니다.",
                         "좋은 기회 주셔서 감사하지만 이번에는 어렵겠습니다. 혹시 [대안]이 도움이 된다면 말씀드리겠습니다."],
    "ask_clarification": ["연락 주셔서 감사합니다. 검토를 위해 [일정], [대상], [조건]을 조금 더 알려주실 수 있을까요?",
                          "제안 감사합니다. 진행 여부를 판단하려면 [구체적 내용]이 필요합니다. 자료를 보내주시면 검토 후 회신드리겠습니다.",
                          "관심 가져주셔서 감사합니다. 원하시는 [범위]와 [일정]을 알려주시면 가능 여부 말씀드리겠습니다."],
    "acknowledge": ["감사합니다! 좋게 봐주셔서 힘이 납니다.",
                    "따뜻한 말씀 감사해요 🙂",
                    "봐주셔서 감사합니다. 다음에도 좋은 내용으로 찾아뵐게요."],
    "escalate": ["말씀 주신 내용 확인했습니다. 정확히 살펴본 뒤 [날짜]까지 답변드리겠습니다.",
                 "불편을 드려 죄송합니다. 관련 내용을 확인 중이며, 확인되는 대로 자세히 안내드리겠습니다.",
                 "의견 감사합니다. 사실관계를 확인한 뒤 공식적으로 회신드리겠습니다."],
}
_GENERIC = ["메시지 감사합니다. 확인 후 답변드리겠습니다.",
            "연락 주셔서 감사합니다. 내용 잘 읽었습니다.",
            "감사합니다! 확인했습니다."]


class MockDrafter:
    name = "mock-drafter"
    model = "templates-v1"

    def draft(self, msg: Message, guidance: str | None, owner: dict) -> tuple[list[str], Usage]:
        action = None
        if guidance:
            m = re.search(r"best_action=(\w+)", guidance)
            action = m.group(1) if m else None
        topic = (msg.subject or msg.context or "문의하신 내용")[:30]
        texts = [t.format(topic=topic) for t in _TEMPLATES.get(action or "", _GENERIC)]
        return texts, Usage("draft", self.name, self.model, 0, _est_tokens(prepare(msg.text)) + 300,
                            sum(map(_est_tokens, texts)), 0.0)

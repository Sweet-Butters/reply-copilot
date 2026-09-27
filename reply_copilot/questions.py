"""Jev question set for email and comment triage.

Instructions and criteria are English (Jev reads English best); the message stays Korean.
Rewritten from jev-chat-windows core/questions.py, whose set targets personal chats
(loyalty tests, ultimatums) rather than inboxes and comment sections.
"""
from __future__ import annotations

from .models import Message
from .privacy import display_name, prepare

# Bump when a question or its criteria change.
QUESTION_VERSION = 1

INTENTS = {
    "question": "They ask something they want answered (how, what, when, whether).",
    "request": "They ask you to do something: send a file, review, give feedback, change a grade, help.",
    "scheduling": "They propose or ask about a meeting time, deadline, or date.",
    "invitation": "They invite you to speak, teach, join, collaborate, or take on work.",
    "complaint": "They are unhappy with you or your content and say so.",
    "feedback": "They share an opinion, praise, or suggestion about your work without asking anything.",
    "thanks_or_fyi": "Thanks, confirmation, announcement, or information with nothing asked of you.",
    "promotion": "Advertising, self-promotion, link drops, bulk marketing, or scams.",
}

SENDER_WANTS = {
    "information": "A factual answer or explanation.",
    "decision": "A yes/no or a choice from you (accept, decline, pick a date).",
    "commitment": "A concrete action, deliverable, or deadline from you.",
    "apology": "Acknowledgement that something went wrong and an apology.",
    "acknowledgement": "To be heard or thanked; a short friendly reply is enough.",
    "nothing": "Nothing from you; no reply is expected.",
}

ACTIONS = {
    "answer": "Answer the question or give the requested information directly.",
    "accept": "Accept the request or invitation and confirm next steps.",
    "decline_politely": "Say no politely, thank them, and if possible point to an alternative.",
    "ask_clarification": "Ask one or two specific questions before committing to anything.",
    "acknowledge": "Short thanks or acknowledgement; nothing more is needed.",
    "ignore": "Do not reply: spam, bait, bulk mail, or abuse where any reply feeds it.",
    "escalate": "Too sensitive for a template: legal, grades dispute, harassment, money. The owner writes it.",
}

TENSION_LEVELS = [
    "Friendly or neutral; no pressure at all.",
    "Polite routine request; nothing at stake.",
    "Mild pressure: a reminder or a soft deadline.",
    "Some urgency: a near deadline or a follow-up after no answer.",
    "Clear dissatisfaction, stated calmly.",
    "Frustrated; a careless reply would make it worse.",
    "Angry or accusing; the relationship or reputation is at some risk.",
    "Hostile, insulting, or threatening to escalate (complain to a boss, school, platform).",
    "Abusive or harassing language aimed at the owner.",
    "Threats, doxxing, or a crisis that needs a human now.",
]


def judge_questions() -> dict:
    return {
        "needs_reply": {
            "type": "noul",
            "instructions": "Does this incoming Korean message expect a reply from the account owner?",
            "criteria": {
                "true": "A real person asks, requests, invites, or complains, and silence would be rude or costly.",
                "false": "Spam, bulk mail, notifications, pure thanks, or a comment that expects no answer.",
            },
        },
        "reply_now": {
            "type": "noul",
            "instructions": "Should the owner reply within the next few hours rather than later this week?",
            "criteria": {
                "true": "A deadline is today or tomorrow, someone is blocked waiting, or tension is rising.",
                "false": "No near deadline; a reply in a few days is fine, or no reply is needed.",
            },
        },
        "spam": {
            "type": "noul",
            "instructions": "Is this message spam, a scam, bulk promotion, or a link drop unrelated to the owner?",
            "criteria": {
                "true": "Advertising, 'check my channel', crypto/loan/adult links, phishing, mass-mailed offers.",
                "false": "A real person writing to or about the owner, even if brief or critical.",
            },
        },
        "abusive": {
            "type": "noul",
            "instructions": "Does this message insult, harass, or demean the owner or others?",
            "criteria": {
                "true": "Insults, slurs, mockery of a person, threats, or sexual harassment.",
                "false": "Polite, neutral, or critical but respectful, even if negative about the content.",
            },
        },
        "intent": {
            "type": "choice",
            "instructions": "What is the sender's main intent in this message?",
            "criteria": dict(INTENTS),
        },
        "sender_wants": {
            "type": "choice",
            "instructions": "What does the sender want from the owner right now?",
            "criteria": dict(SENDER_WANTS),
        },
        "best_action": {
            "type": "choice",
            "instructions": ("What should the owner's next move be? If the message is spam or abuse, choose ignore. "
                             "If it involves money, grades, legal matters or harassment, choose escalate."),
            "criteria": dict(ACTIONS),
        },
        "tension": {
            "type": "score",
            "instructions": "How tense or risky is this exchange for the owner, from 0 (calm) to 9 (crisis)?",
            "criteria": list(TENSION_LEVELS),
        },
    }


def rank_question(candidates: list[str]) -> dict:
    if not 2 <= len(candidates) <= 3:
        raise ValueError("rank_question expects 2 or 3 candidates")
    keys = ("reply_a", "reply_b", "reply_c")[: len(candidates)]
    return {
        "best_reply": {
            "type": "choice",
            "instructions": ("Which candidate is the most appropriate reply from the owner to this message? "
                             "Prefer replies that answer what the sender actually wants, are polite and concise, "
                             "and do not promise things the owner did not agree to or invent facts."),
            "criteria": dict(zip(keys, candidates)),
        }
    }


RANK_KEYS = ("reply_a", "reply_b", "reply_c")


def build_state(msg: Message) -> dict:
    """What Jev sees. Only cleaned text and a display name; ids and addresses stay local."""
    state: dict = {
        "channel": msg.channel,
        "kind": msg.kind,
        "owner_role": "the account owner, who will review and send any reply personally",
        "sender": display_name(msg.sender),
        "message": prepare(msg.text),
    }
    if msg.subject:
        state["subject"] = prepare(msg.subject, 200)
    if msg.context:
        state["posted_under"] = prepare(msg.context, 300)
    if msg.thread:
        state["earlier"] = [{"from": who, "text": prepare(t, 500)} for who, t in msg.thread[-4:]]
    return state

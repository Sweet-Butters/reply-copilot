import unittest

from helpers import env  # noqa: F401  (path setup)

from reply_copilot.adapters.fixtures import load_fixtures, to_message
from reply_copilot.config import Thresholds
from reply_copilot.models import Outcome, Usage
from reply_copilot.pipeline import draft_direct, judge_first
from reply_copilot.providers.base import ProviderError
from reply_copilot.providers.mock import MockDrafter, MockJudge

FX = {f["id"]: to_message(f) for f in load_fixtures()}
OWNER = {"name": "정회광", "style": "정중하게"}


class CountingDrafter(MockDrafter):
    def __init__(self):
        self.calls = 0
        self.guidance = []

    def draft(self, msg, guidance, owner):
        self.calls += 1
        self.guidance.append(guidance)
        return super().draft(msg, guidance, owner)


class FailingJudge(MockJudge):
    def judge(self, msg):
        raise ProviderError("HTTP 529: overloaded")


class PipelineTest(unittest.TestCase):
    def test_spam_is_skipped_without_a_draft_call(self):
        d = CountingDrafter()
        out = judge_first(FX["fx04-yt-spam"], MockJudge(), d, Thresholds(), OWNER)
        self.assertEqual(out.decision, "skip_spam")
        self.assertEqual(d.calls, 0)
        self.assertIsNone(out.best)

    def test_abuse_is_skipped_with_a_warning(self):
        out = judge_first(FX["fx05-yt-rude"], MockJudge(), CountingDrafter(), Thresholds(), OWNER)
        self.assertEqual(out.decision, "skip_abusive")
        self.assertTrue(out.warnings)

    def test_guidance_reaches_drafter_and_candidates_are_ranked(self):
        d = CountingDrafter()
        out = judge_first(FX["fx03-decline-volunteer"], MockJudge(), d, Thresholds(), OWNER)
        self.assertEqual(out.decision, "draft")
        self.assertIn("best_action=decline_politely", d.guidance[0])
        scores = [c.score for c in out.candidates]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(out.best, out.candidates[0].text)
        self.assertEqual([u.role for u in out.usage], ["judge", "draft", "rank"])

    def test_high_tension_warns_owner(self):
        out = judge_first(FX["fx09-grade-complaint"], MockJudge(), MockDrafter(), Thresholds(), OWNER)
        self.assertTrue(any("직접 쓰세요" in w for w in out.warnings))

    def test_judge_failure_still_drafts_unranked(self):
        d = CountingDrafter()
        out = judge_first(FX["fx06-yt-genuine-question"], FailingJudge(), d, Thresholds(), OWNER)
        self.assertEqual(out.decision, "draft")
        self.assertIsNone(d.guidance[0])
        self.assertTrue(all(c.score is None for c in out.candidates))
        self.assertIn("judge failed", out.warnings[0])

    def test_draft_direct_always_drafts(self):
        d = CountingDrafter()
        out = draft_direct(FX["fx04-yt-spam"], d, OWNER)
        self.assertEqual((out.decision, d.calls), ("draft", 1))

    def test_unknown_cost_propagates(self):
        o = Outcome("x", "judge_first", "draft", usage=[Usage("judge", "j", "m", 1, cost_usd=0.1),
                                                        Usage("draft", "d", "m", 1, cost_usd=None)])
        self.assertIsNone(o.total_cost)


if __name__ == "__main__":
    unittest.main()

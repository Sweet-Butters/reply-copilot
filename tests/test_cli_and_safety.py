import contextlib
import io
import os
import re
import tempfile
import unittest
from pathlib import Path

from helpers import env

from reply_copilot import cli, evaluation
from reply_copilot.store import Store

PKG = Path(__file__).resolve().parent.parent / "reply_copilot"


def run_cli(*argv) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, buf.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["REPLY_DATA_DIR"] = self.tmp.name

    def tearDown(self):
        os.environ.pop("REPLY_DATA_DIR", None)
        self.tmp.cleanup()

    def test_dry_run_needs_no_credentials_and_writes_nothing(self):
        with env():
            code, _ = run_cli("run", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_dry_run_output(self):
        with env():
            code, out = run_cli("run", "--dry-run", "--limit", "5")
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN", out)
        self.assertIn("skip_spam", out)
        self.assertIn("mock-judge", out)

    def test_stage_on_fixtures_fills_queue_and_marks_seen(self):
        with env():
            run_cli("run", "--stage", "--mock")
            store = Store(Path(self.tmp.name) / "state.db")
            pending = store.pending()
            self.assertEqual(len(pending), 7)  # 10 fixtures minus spam, abuse, newsletter
            self.assertTrue(store.is_seen("fixtures", "fx04-yt-spam"))
            store.close()
            code, out = run_cli("review")
            self.assertIn("제안 답글", out)
            code, _ = run_cli("mark", str(pending[0]["id"]), "done")
            self.assertEqual(code, 0)

    def test_dry_run_and_stage_are_exclusive(self):
        with env():
            code, _ = run_cli("run", "--dry-run", "--stage")
        self.assertEqual(code, 2)

    def test_strict_without_keys_fails(self):
        with env():
            with self.assertRaises(Exception):
                run_cli("run", "--strict")


class EvalTest(unittest.TestCase):
    def test_mock_eval_compares_both_pipelines(self):
        with env():
            from reply_copilot.config import Settings
            from reply_copilot.providers.mock import MockDrafter, MockJudge
            r = evaluation.run_eval(MockJudge(), MockDrafter(), Settings.from_env())
        a, b = r["summary"]["judge_first"], r["summary"]["draft_direct"]
        self.assertEqual(r["fixtures"], 10)
        self.assertEqual(b["drafted"], 10)
        self.assertEqual(b["wasted_drafts_on_no_reply"], 3)
        self.assertEqual(a["wasted_drafts_on_no_reply"], 0)
        self.assertEqual(a["calls"]["draft"], a["drafted"])
        md = evaluation.to_markdown(r)
        self.assertIn("mock 모드", md)


class SafetyTest(unittest.TestCase):
    """The product must never send or post. Fail if any send/post call appears in the source."""

    FORBIDDEN = [
        r"messages\(\)\s*\.\s*send\(",       # Gmail send
        r"drafts\(\)\s*\.\s*send\(",         # Gmail send a draft
        r"comments\(\)\s*\.\s*insert\(",     # YouTube reply
        r"commentThreads\(\)\s*\.\s*insert\(",
        r"setModerationStatus|markAsSpam",   # YouTube moderation writes
        r"/replies[\"'].*POST|POST.*?/replies",  # Instagram reply
        r"gmail\.send[\"']",                 # send-only scope
    ]

    def test_no_send_or_post_code(self):
        offenders = []
        for path in PKG.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
            for pat in self.FORBIDDEN:
                if re.search(pat, code):
                    offenders.append(f"{path.name}: {pat}")
        self.assertEqual(offenders, [])

    def test_instagram_and_youtube_only_read(self):
        ig = (PKG / "adapters" / "instagram.py").read_text(encoding="utf-8")
        self.assertNotIn('"POST"', ig)
        yt = (PKG / "adapters" / "youtube.py").read_text(encoding="utf-8")
        self.assertIn("youtube.readonly", yt)
        self.assertNotIn("force-ssl\"", yt)


if __name__ == "__main__":
    unittest.main()

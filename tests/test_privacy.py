import os
import unittest

from helpers import env

from reply_copilot.privacy import display_name, prepare, redact_secrets, strip_quoted


class PrivacyTest(unittest.TestCase):
    def test_strips_quoted_history_and_signature(self):
        text = ("면담 가능한 시간 알려주세요.\n\n김지도 드림\n--\n연구실 02-1234-5678\n\n"
                "2026년 9월 25일 (목) 오후 2:10, 정회광 님이 작성:\n> 교수님, 초안 첨부드립니다.")
        out = strip_quoted(text)
        self.assertIn("면담 가능한 시간", out)
        self.assertNotIn("02-1234-5678", out)
        self.assertNotIn("초안 첨부", out)

    def test_english_quote_header(self):
        self.assertEqual(strip_quoted("Sure.\nOn Mon, Sep 1, 2026 at 9:00 AM Bob <b@x.com> wrote:\n> hi"), "Sure.")

    def test_masks_email_phone_and_url_tokens(self):
        out = prepare("연락처 010-0000-0000, 메일 hr.park@example-corp.co.kr, https://x.io/a?token=abc123&b=1")
        self.assertNotIn("9876", out)
        self.assertNotIn("hr.park", out)
        self.assertNotIn("abc123", out)
        self.assertIn("[PHONE]", out)
        self.assertIn("[EMAIL]", out)

    def test_display_name(self):
        self.assertEqual(display_name("김지도 교수 <prof.kim@example.ac.kr>"), "김지도 교수")
        self.assertEqual(display_name("prof.kim@example.ac.kr"), "[EMAIL]")

    def test_truncates(self):
        self.assertEqual(len(prepare("가" * 5000)), 2000)

    def test_redact_secrets(self):
        with env(TYPESAFE_API_KEY="ts-secret-value-123"):
            self.assertEqual(redact_secrets("bad key ts-secret-value-123"), "bad key [REDACTED]")


if __name__ == "__main__":
    unittest.main()

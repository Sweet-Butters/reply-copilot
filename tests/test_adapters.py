import base64
import email
import unittest
from email import policy

from helpers import env, fake_http

from reply_copilot.adapters.base import AdapterError
from reply_copilot.adapters.gmail import GmailAdapter, build_draft, parse_message
from reply_copilot.adapters.instagram import InstagramAdapter, parse_comments
from reply_copilot.adapters.youtube import YouTubeAdapter, parse_threads
from reply_copilot.store import Store


def b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


GMAIL_RAW = {
    "id": "m1", "threadId": "t1",
    "payload": {
        "mimeType": "multipart/alternative",
        "headers": [{"name": "From", "value": "김지도 교수 <prof.kim@example.ac.kr>"},
                    {"name": "Subject", "value": "면담 일정"},
                    {"name": "Message-ID", "value": "<abc@mail.example>"},
                    {"name": "Date", "value": "Fri, 26 Sep 2026 10:00:00 +0900"}],
        "parts": [{"mimeType": "text/plain", "body": {"data": b64("목요일 3시 괜찮나요?")}},
                  {"mimeType": "text/html", "body": {"data": b64("<p>목요일 3시 괜찮나요?</p>")}}],
    },
}


class _Call:
    def __init__(self, result, log, name, kwargs):
        self.result, self.log = result, log
        log.append((name, kwargs))

    def execute(self):
        return self.result


class FakeGmail:
    """Just enough of googleapiclient's Gmail resource; records every call."""

    def __init__(self, messages):
        self.messages_by_id = {m["id"]: m for m in messages}
        self.log = []

    def users(self):
        return self

    def messages(self):
        outer = self

        class M:
            def list(self, **kw):
                return _Call({"messages": [{"id": i} for i in outer.messages_by_id]}, outer.log, "list", kw)

            def get(self, **kw):
                return _Call(outer.messages_by_id[kw["id"]], outer.log, "get", kw)
        return M()

    def drafts(self):
        outer = self

        class D:
            def create(self, **kw):
                return _Call({"id": "r-1"}, outer.log, "drafts.create", kw)
        return D()


class GmailTest(unittest.TestCase):
    def test_parse_prefers_plain_text(self):
        m = parse_message(GMAIL_RAW)
        self.assertEqual((m.id, m.kind, m.subject), ("m1", "email", "면담 일정"))
        self.assertEqual(m.text, "목요일 3시 괜찮나요?")
        self.assertEqual(m.meta["thread_id"], "t1")

    def test_build_draft_threads_the_reply(self):
        body = build_draft(parse_message(GMAIL_RAW), "네, 목요일 3시에 뵙겠습니다.", "me@example.com")
        self.assertEqual(body["message"]["threadId"], "t1")
        raw = base64.urlsafe_b64decode(body["message"]["raw"])
        em = email.message_from_bytes(raw, policy=policy.default)
        self.assertEqual(em["In-Reply-To"], "<abc@mail.example>")
        self.assertEqual(em["Subject"], "Re: 면담 일정")
        self.assertIn("prof.kim@example.ac.kr", em["To"])
        self.assertIn("목요일 3시에 뵙겠습니다", em.get_content())

    def test_fetch_skips_own_mail_and_stage_only_creates_a_draft(self):
        mine = dict(GMAIL_RAW, id="m2", payload=dict(GMAIL_RAW["payload"], headers=[
            {"name": "From", "value": "정회광 <me@example.com>"}, {"name": "Subject", "value": "x"}]))
        svc = FakeGmail([GMAIL_RAW, mine])
        g = GmailAdapter(None, "me@example.com", service=svc)
        msgs = g.fetch(10)
        self.assertEqual([m.id for m in msgs], ["m1"])
        self.assertTrue(all(kw.get("userId") == "me" for _, kw in svc.log))
        note = g.stage(msgs[0], "네 좋습니다.", Store(":memory:"))
        self.assertEqual(note, "Gmail draft r-1")
        self.assertEqual([n for n, _ in svc.log if "create" in n or "send" in n], ["drafts.create"])


def yt_thread(tid, author, text, replies=()):
    return {"id": tid, "snippet": {"videoId": "v1", "topLevelComment": {"id": f"c-{tid}", "snippet": {
        "authorDisplayName": author, "authorChannelId": {"value": author}, "textOriginal": text,
        "videoId": "v1", "publishedAt": "2026-09-27T00:00:00Z"}}},
        "replies": {"comments": [{"snippet": {"authorChannelId": {"value": r}}} for r in replies]}}


class FakeYouTube:
    def __init__(self, items):
        self.items, self.log = items, []

    def channels(self):
        outer = self

        class C:
            def list(self, **kw):
                return _Call({"items": [{"id": "UC_me"}]}, outer.log, "channels.list", kw)
        return C()

    def commentThreads(self):
        outer = self

        class T:
            def list(self, **kw):
                return _Call({"items": outer.items}, outer.log, "commentThreads.list", kw)
        return T()

    def videos(self):
        outer = self

        class V:
            def list(self, **kw):
                return _Call({"items": [{"id": "v1", "snippet": {"title": "LLM 에이전트 30분"}}]},
                             outer.log, "videos.list", kw)
        return V()


class YouTubeTest(unittest.TestCase):
    def test_parse_skips_mine_and_answered(self):
        items = [yt_thread("1", "viewer", "질문 있어요"), yt_thread("2", "UC_me", "고정 댓글"),
                 yt_thread("3", "viewer2", "감사합니다", replies=["UC_me"])]
        self.assertEqual([m.id for m in parse_threads(items, "UC_me")], ["c-1"])

    def test_fetch_uses_own_channel_and_queues(self):
        yt = FakeYouTube([yt_thread("1", "viewer", "질문 있어요")])
        a = YouTubeAdapter(None, service=yt)
        msgs = a.fetch(5)
        self.assertEqual(msgs[0].context, "LLM 에이전트 30분")
        names = [n for n, _ in yt.log]
        self.assertEqual(names, ["channels.list", "commentThreads.list", "videos.list"])
        self.assertTrue(yt.log[0][1]["mine"])
        self.assertEqual(yt.log[1][1]["allThreadsRelatedToChannelId"], "UC_me")
        store = Store(":memory:")
        self.assertTrue(a.stage(msgs[0], "좋은 질문이에요!", store).startswith("queue #"))
        self.assertIn("lc=c-1", store.pending()[0]["link"])


class InstagramTest(unittest.TestCase):
    MEDIA = {"id": "17", "caption": "세미나 발표", "permalink": "https://instagram.com/p/x"}

    def test_parse_skips_mine_and_answered(self):
        comments = [{"id": "a", "username": "fan", "text": "좋아요"},
                    {"id": "b", "username": "Me_Account", "text": "감사해요"},
                    {"id": "c", "username": "fan2", "text": "질문", "replies": {"data": [{"username": "me_account"}]}}]
        self.assertEqual([m.id for m in parse_comments(comments, "me_account", self.MEDIA)], ["a"])

    def test_fetch_reads_only_and_keeps_token_out_of_errors(self):
        with env(IG_ACCESS_TOKEN="IGtoken-secret-000"), fake_http(
                (200, {"user_id": "1", "username": "me_account"}),
                (200, {"data": [self.MEDIA]}),
                (200, {"data": [{"id": "a", "username": "fan", "text": "좋아요"}]})) as fake:
            msgs = InstagramAdapter().fetch(5)
        self.assertEqual([m.id for m in msgs], ["a"])
        self.assertTrue(all(c["method"] == "GET" for c in fake.calls))
        self.assertTrue(fake.calls[0]["url"].startswith("https://graph.instagram.com/"))
        with env(IG_ACCESS_TOKEN="IGtoken-secret-000"), fake_http((400, {"error": {"message": "bad"}})):
            with self.assertRaises(AdapterError) as ctx:
                InstagramAdapter().fetch(1)
        self.assertNotIn("IGtoken-secret-000", str(ctx.exception))

    def test_missing_token(self):
        with env():
            with self.assertRaises(AdapterError):
                InstagramAdapter()


if __name__ == "__main__":
    unittest.main()

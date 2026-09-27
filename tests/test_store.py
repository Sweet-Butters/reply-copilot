import unittest

from helpers import env  # noqa: F401  (path setup)

from reply_copilot.store import Store


class StoreTest(unittest.TestCase):
    def test_seen_queue_and_status(self):
        s = Store(":memory:")
        self.assertFalse(s.is_seen("youtube", "c1"))
        s.mark_seen("youtube", "c1")
        self.assertTrue(s.is_seen("youtube", "c1"))
        qid = s.enqueue("youtube", "c1", "감사합니다!", sender="a", original="좋아요")
        self.assertEqual(s.enqueue("youtube", "c1", "고맙습니다!"), qid)  # re-queue replaces
        rows = s.pending()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reply"], "고맙습니다!")
        self.assertTrue(s.set_status(qid, "done"))
        self.assertEqual(s.pending(), [])
        with self.assertRaises(ValueError):
            s.set_status(qid, "sent")


if __name__ == "__main__":
    unittest.main()

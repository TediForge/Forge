import unittest

from src.context.idempotency import IdempotencyStore


class IdempotencyStoreTests(unittest.TestCase):
    def test_completed_request_can_be_replayed(self):
        store = IdempotencyStore()
        state, replay = store.begin("tenant-a", "user-1", "idem-1", "fingerprint")
        self.assertEqual(state, "started")
        self.assertIsNone(replay)

        store.complete("tenant-a", "user-1", "idem-1", {"runId": "run-1", "status": "completed"})
        state, replay = store.begin("tenant-a", "user-1", "idem-1", "fingerprint")

        self.assertEqual(state, "replay")
        self.assertEqual(replay["response"]["runId"], "run-1")

    def test_different_payload_conflicts(self):
        store = IdempotencyStore()
        store.begin("tenant-a", "user-1", "idem-1", "fingerprint-a")
        state, _ = store.begin("tenant-a", "user-1", "idem-1", "fingerprint-b")
        self.assertEqual(state, "conflict")


if __name__ == "__main__":
    unittest.main()

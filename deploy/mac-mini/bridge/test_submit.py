import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import submit


class SubmitSafetyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        media = root / "clip.mp4"
        media.write_bytes(b"test media")
        self.job = root / "job.json"
        self.job.write_text(json.dumps({
            "id": "source-123",
            "media_path": str(media),
            "caption": "Test",
            "integrations": [{"id": "channel-1", "settings": {}}],
        }))
        self.state = root / "state.sqlite"

    def run_job(self):
        with patch.object(sys, "argv", ["submit.py", str(self.job), str(self.state)]):
            with contextlib.redirect_stdout(io.StringIO()):
                submit.main()

    def test_accepted_job_is_not_submitted_twice(self):
        with patch.object(submit, "upload", return_value={"id": "media-1", "path": "https://example.org/uploads/a.mp4"}) as upload:
            with patch.object(submit, "submit", return_value=[{"postId": "post-1", "integration": "channel-1"}]) as publish:
                self.run_job()
                self.run_job()
        self.assertEqual(upload.call_count, 1)
        self.assertEqual(publish.call_count, 1)

    def test_uncertain_outcome_blocks_retry(self):
        with patch.object(submit, "upload", return_value={"id": "media-1", "path": "https://example.org/uploads/a.mp4"}):
            with patch.object(submit, "submit", side_effect=TimeoutError("connection lost")) as publish:
                with self.assertRaises(TimeoutError):
                    self.run_job()
                with self.assertRaisesRegex(RuntimeError, "uncertain"):
                    self.run_job()
        self.assertEqual(publish.call_count, 1)

    def test_plain_http_only_allowed_on_loopback(self):
        with patch.dict("os.environ", {"POSTIZ_API_URL": "http://public.example.org/api", "POSTIZ_API_KEY": "test"}):
            with self.assertRaisesRegex(ValueError, "HTTPS or loopback"):
                submit.connection()
        with patch.dict("os.environ", {"POSTIZ_API_URL": "http://127.0.0.1:4007/api", "POSTIZ_API_KEY": "test"}):
            conn, key = submit.connection()
            self.assertEqual(key, "test")
            self.assertEqual(conn.host, "127.0.0.1")
            conn.close()


if __name__ == "__main__":
    unittest.main()

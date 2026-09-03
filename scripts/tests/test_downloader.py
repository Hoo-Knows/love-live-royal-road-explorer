import ssl
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from royal_road.downloader import DownloadError, download_audio  # noqa: E402


class DownloaderTests(unittest.TestCase):
    def test_certificate_verification_failure_is_not_retried(self):
        error = URLError(ssl.SSLCertVerificationError(10, "certificate has expired"))
        request = Mock(side_effect=error)
        logs = []
        with tempfile.TemporaryDirectory() as temp:
            with patch("royal_road.downloader.urlopen", request):
                with self.assertRaises(DownloadError) as raised:
                    download_audio(
                        "https://wiki/audio.ogg",
                        Path(temp) / "audio.ogg",
                        throttle_seconds=0,
                        max_retries=3,
                        log=logs.append,
                    )
        self.assertEqual(request.call_count, 1)
        self.assertIn("TLS certificate verification failed; not retrying", "\n".join(logs))
        self.assertIn("certificate has expired", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

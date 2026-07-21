from __future__ import annotations

import unittest

from app.audio import TTS_SAMPLE_RATE, adjust_pcm_speed


class AudioTests(unittest.TestCase):
    def test_adjust_pcm_speed_changes_duration_without_resampling(self) -> None:
        pcm = b"\x00\x00" * TTS_SAMPLE_RATE

        faster = b"".join(adjust_pcm_speed([pcm], 2))
        slower = b"".join(adjust_pcm_speed([pcm], 0.5))

        self.assertGreater(len(faster), 0)
        self.assertLess(len(faster), len(pcm))
        self.assertGreater(len(slower), len(pcm))


if __name__ == "__main__":
    unittest.main()

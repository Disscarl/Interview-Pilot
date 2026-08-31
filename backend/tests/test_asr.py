import struct
import unittest

from services.asr import (
    _pcm_from_wav, _frame_status, SEGMENT_BYTES, SEGMENT_SECONDS, BYTES_PER_SECOND,
)


def _make_wav(pcm: bytes) -> bytes:
    return (
        b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 16000, BYTES_PER_SECOND, 2, 16)
        + b"data" + struct.pack("<I", len(pcm)) + pcm
    )


class WavParseTest(unittest.TestCase):
    def test_extracts_pcm(self):
        pcm = b"\x00\x00\x01\x00"
        self.assertEqual(_pcm_from_wav(_make_wav(pcm)), pcm)

    def test_rejects_non_wav(self):
        with self.assertRaises(ValueError):
            _pcm_from_wav(b"not a wav file")

    def test_rejects_missing_data(self):
        with self.assertRaises(ValueError):
            _pcm_from_wav(b"RIFF" + struct.pack("<I", 36) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16))

    def test_rejects_unsupported_format(self):
        # 48 kHz mono 16-bit WAV must be rejected, not blindly parsed.
        bad = (
            b"RIFF" + struct.pack("<I", 36 + 4) + b"WAVE"
            + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 48000, 48000 * 2, 2, 16)
            + b"data" + struct.pack("<I", 4) + b"\x00\x00\x01\x00"
        )
        with self.assertRaises(ValueError):
            _pcm_from_wav(bad)


class SegmentConfigTest(unittest.TestCase):
    def test_segment_is_under_60s(self):
        # 55 seconds of 16k/16bit mono PCM, kept under iFlytek's 60s cap.
        self.assertEqual(SEGMENT_SECONDS, 55)
        self.assertEqual(SEGMENT_BYTES, SEGMENT_SECONDS * BYTES_PER_SECOND)
        self.assertLess(SEGMENT_SECONDS, 60)


class FrameStatusTest(unittest.TestCase):
    """L1: a single-frame upload must still send the end marker (status=2)."""

    def test_single_frame_is_last(self):
        self.assertEqual(_frame_status(0, 1), 2)

    def test_multi_frame_sequence(self):
        self.assertEqual(_frame_status(0, 3), 0)
        self.assertEqual(_frame_status(1, 3), 1)
        self.assertEqual(_frame_status(2, 3), 2)


if __name__ == "__main__":
    unittest.main()

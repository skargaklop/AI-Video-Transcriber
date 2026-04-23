import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from transcript_formatting import format_transcript_without_timecodes, strip_transcript_timecodes  # noqa: E402


class TranscriptFormattingTests(unittest.TestCase):
    def test_strips_markdown_timecode_blocks(self):
        transcript = (
            "# Video Transcription\n\n"
            "**Detected Language:** ru\n\n"
            "## Transcription Content\n\n"
            "**[00:02 - 00:04]**\n\n"
            "First sentence.\n\n"
            "**[01:02:03 - 01:02:05]**\n\n"
            "Second sentence.\n"
        )

        result = strip_transcript_timecodes(transcript)

        self.assertNotIn("[00:02 - 00:04]", result)
        self.assertNotIn("[01:02:03 - 01:02:05]", result)
        self.assertIn("First sentence.", result)
        self.assertIn("Second sentence.", result)
        self.assertIn("## Transcription Content", result)

    def test_strips_plain_timecode_lines(self):
        transcript = "[19:20 - 19:22]\nText one.\n\n[19:22 - 19:24]\nText two."

        result = strip_transcript_timecodes(transcript)

        self.assertEqual(result, "Text one.\n\nText two.")

    def test_formats_transcript_without_timecodes_as_readable_paragraphs(self):
        transcript = (
            "# Video Transcription\n\n"
            "**Detected Language:** ru\n\n"
            "## Transcription Content\n\n"
            "**[00:02 - 00:04]**\n\n"
            "Всем здорово. Сегодня я расскажу вам про GitHub Spec Kit.\n\n"
            "**[00:04 - 00:07]**\n\n"
            "Это фреймворк, который позволяет улучшить качество разработки.\n\n"
            "## Эпизод 2: Установка\n\n"
            "**[01:13 - 01:17]**\n\n"
            "Для начала нужно установить инструмент одной командой.\n"
        )

        result = format_transcript_without_timecodes(transcript)

        self.assertNotIn("[00:02 - 00:04]", result)
        self.assertIn(
            "Всем здорово. Сегодня я расскажу вам про GitHub Spec Kit. "
            "Это фреймворк, который позволяет улучшить качество разработки.",
            result,
        )
        self.assertIn("## Эпизод 2: Установка", result)
        self.assertIn("Для начала нужно установить инструмент одной командой.", result)


if __name__ == "__main__":
    unittest.main()

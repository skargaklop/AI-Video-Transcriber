import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from video_processor import VideoProcessor, remove_leading_text_overlap, resolve_media_redirect_url, select_subtitle_language  # noqa: E402


class FakeResponse:
    def __init__(self, url):
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def geturl(self):
        return self._url


class FakeOpener:
    def __init__(self, final_url):
        self.final_url = final_url
        self.requests = []

    def open(self, request, timeout=0):
        self.requests.append((request, timeout))
        return FakeResponse(self.final_url)


class RedirectResolutionTests(unittest.TestCase):
    def test_resolves_media_redirect_without_downloading_body(self):
        opener = FakeOpener("https://rr2---sn.googlevideo.com/videoplayback?id=final")

        resolved = resolve_media_redirect_url(
            "https://redirector.googlevideo.com/videoplayback?id=initial",
            headers={"User-Agent": "test-agent"},
            opener=opener,
            timeout=7,
        )

        self.assertEqual(resolved, "https://rr2---sn.googlevideo.com/videoplayback?id=final")
        request, timeout = opener.requests[0]
        self.assertEqual(request.get_method(), "HEAD")
        self.assertEqual(request.get_header("User-agent"), "test-agent")
        self.assertEqual(timeout, 7)


class SubtitleSelectionTests(unittest.TestCase):
    def test_prefers_original_auto_caption_over_translated_english_caption(self):
        captions = {
            "en": [{"ext": "vtt", "url": "https://www.youtube.com/api/timedtext?v=abc&tlang=en"}],
            "ru": [{"ext": "vtt", "url": "https://www.youtube.com/api/timedtext?v=abc&lang=ru"}],
        }

        selected = select_subtitle_language(captions, prefer_original=True)

        self.assertEqual(selected, "ru")

    def test_uses_priority_when_no_original_caption_can_be_identified(self):
        captions = {
            "de": [{"ext": "vtt", "url": "https://example.com/caption?tlang=de"}],
            "en": [{"ext": "vtt", "url": "https://example.com/caption?tlang=en"}],
        }

        selected = select_subtitle_language(captions, prefer_original=True)

        self.assertEqual(selected, "en")


class SubtitleOverlapTests(unittest.TestCase):
    def test_removes_repeated_leading_phrase_from_next_caption(self):
        previous = "Всем здорово. Сегодня я расскажу вам про GitHub Spe Kit - это фреймворк, который"
        current = "GitHub Spe Kit - это фреймворк, который позволяет сильно улучшить качество,"

        result = remove_leading_text_overlap(previous, current)

        self.assertEqual(result, "позволяет сильно улучшить качество,")

    def test_format_subtitle_entries_deduplicates_rolling_youtube_captions(self):
        processor = VideoProcessor()
        entries = [
            {
                "start": "00:00",
                "end": "00:07",
                "text": "Всем здорово. Сегодня я расскажу вам про GitHub Spe Kit - это фреймворк, который позволяет сильно улучшить качество,",
            },
            {
                "start": "00:07",
                "end": "00:15",
                "text": "скорость и эффективность разработки в ИД и сила инструментах по типу, курсора и в целом разработки с помощью нейросетей,",
            },
            {
                "start": "00:15",
                "end": "00:26",
                "text": "которые позволяет структурировать всю информацию и превращать технические задания в артефакты, которые помогут уже нам направлять весь процесс создания кода. Значит, сначала вообще разберёмся,",
            },
            {
                "start": "00:26",
                "end": "00:34",
                "text": "что такое GitHub SpeedKit. Это, опять же таки официальный инструмент от Гитхаubба. Реализовали они его буквально недавно. Он ещё обновляется постоянно.",
            },
        ]

        result = processor._format_subtitle_entries(entries, "ru")

        self.assertEqual(result.count("GitHub Spe Kit"), 1)
        self.assertEqual(result.count("позволяет сильно улучшить качество"), 1)
        self.assertIn("скорость и эффективность разработки", result)

    def test_format_subtitle_entries_adds_chapter_headings(self):
        processor = VideoProcessor()
        entries = [
            {"start": "00:00", "end": "00:07", "text": "Intro text."},
            {"start": "00:26", "end": "00:34", "text": "Chapter text."},
        ]
        chapters = [
            {"start_time": 0, "title": "Вступление"},
            {"start_time": 26, "title": "Что такое GitHub Spec Kit"},
        ]

        result = processor._format_subtitle_entries(entries, "ru", chapters=chapters)

        self.assertIn("## Вступление", result)
        self.assertIn("## Что такое GitHub Spec Kit", result)
        self.assertLess(result.index("## Вступление"), result.index("Intro text."))
        self.assertLess(result.index("## Что такое GitHub Spec Kit"), result.index("Chapter text."))


if __name__ == "__main__":
    unittest.main()

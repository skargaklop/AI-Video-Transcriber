import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from groq_transcriber import (  # noqa: E402
    MultipartFile,
    build_multipart_form_data,
    format_seconds,
    format_transcription_markdown,
    prepare_groq_payload,
)


class GroqTranscriberTests(unittest.TestCase):
    def test_formats_segmented_verbose_json(self):
        data = {
            "language": "en",
            "duration": 4.5,
            "segments": [
                {"start": 0.0, "end": 1.25, "text": " First sentence."},
                {"start": 1.25, "end": 4.5, "text": "Second sentence."},
            ],
        }

        result = format_transcription_markdown(data, fallback_language="en")

        self.assertIn("**Detected Language:** en", result)
        self.assertIn("**[00:00 - 00:01]**", result)
        self.assertIn("First sentence.", result)
        self.assertIn("Second sentence.", result)

    def test_falls_back_to_plain_text_response(self):
        result = format_transcription_markdown("Plain transcription text", fallback_language="")

        self.assertIn("## Transcription Content", result)
        self.assertIn("Plain transcription text", result)

    def test_formats_preformatted_timestamp_strings(self):
        self.assertEqual(format_seconds("00:00"), "00:00")
        self.assertEqual(format_seconds("00:03"), "00:03")
        self.assertEqual(format_seconds("01:02:03"), "01:02:03")

    def test_prepare_groq_payload_uses_url_not_file(self):
        payload = prepare_groq_payload(
            audio_url="https://example.com/audio.m4a",
            model="whisper-large-v3-turbo",
            language="en",
            prompt="Speaker talks about APIs.",
        )

        self.assertEqual(payload["url"], "https://example.com/audio.m4a")
        self.assertNotIn("file", payload)
        self.assertEqual(payload["response_format"], "verbose_json")
        self.assertEqual(payload["timestamp_granularities[]"], ["segment"])

    def test_prepare_groq_payload_omits_auto_language_for_detection(self):
        payload = prepare_groq_payload(
            audio_url="https://example.com/audio.m4a",
            model="whisper-large-v3-turbo",
            language="auto",
        )

        self.assertNotIn("language", payload)

    def test_groq_request_body_is_multipart_form_data(self):
        body, content_type = build_multipart_form_data(
            {
                "url": "https://example.com/audio.m4a",
                "model": "whisper-large-v3-turbo",
                "response_format": "verbose_json",
                "timestamp_granularities[]": ["segment"],
            },
            boundary="test-boundary",
        )

        self.assertEqual(content_type, "multipart/form-data; boundary=test-boundary")
        self.assertIn(b'name="url"', body)
        self.assertIn(b"https://example.com/audio.m4a", body)
        self.assertIn(b'name="timestamp_granularities[]"', body)
        self.assertIn(b"--test-boundary--", body)

    def test_groq_request_body_can_include_uploaded_audio_file(self):
        body, content_type = build_multipart_form_data(
            {
                "file": MultipartFile(
                    filename="audio.m4a",
                    content=b"fake-audio",
                    content_type="audio/mp4",
                ),
                "model": "whisper-large-v3-turbo",
                "response_format": "verbose_json",
            },
            boundary="file-boundary",
        )

        self.assertEqual(content_type, "multipart/form-data; boundary=file-boundary")
        self.assertIn(b'name="file"; filename="audio.m4a"', body)
        self.assertIn(b"Content-Type: audio/mp4", body)
        self.assertIn(b"fake-audio", body)
        self.assertIn(b'name="model"', body)


if __name__ == "__main__":
    unittest.main()

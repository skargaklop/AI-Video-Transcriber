import asyncio
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from summarizer import Summarizer  # noqa: E402


class _FakeMessage:
    content = "Summary body"


class _FakeChoice:
    message = _FakeMessage()


class _FakeResponse:
    choices = [_FakeChoice()]


class _FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse()


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self):
        self.chat = _FakeChat()


class _FailingCompletions:
    def create(self, **kwargs):
        raise RuntimeError("provider rejected request")


class _FailingChat:
    def __init__(self):
        self.completions = _FailingCompletions()


class _FailingClient:
    def __init__(self):
        self.chat = _FailingChat()


class SummarizerPromptTests(unittest.TestCase):
    def test_single_summary_prompt_ends_with_summary_language(self):
        summarizer = Summarizer()
        fake_client = _FakeClient()
        summarizer.client = fake_client

        asyncio.run(
            summarizer._summarize_single_text(
                "Transcript body",
                "en",
                "Video",
                custom_prompt="Focus on action items.",
            )
        )

        messages = fake_client.chat.completions.calls[0]["messages"]
        user_prompt = messages[-1]["content"]
        self.assertIn("Focus on action items.", user_prompt)
        self.assertTrue(user_prompt.rstrip().endswith("Summary Language: English"))

    def test_russian_summary_prompt_ends_with_russian_language(self):
        summarizer = Summarizer()
        fake_client = _FakeClient()
        summarizer.client = fake_client

        asyncio.run(
            summarizer._summarize_single_text(
                "Transcript body",
                "ru",
                "Video",
                custom_prompt="Сделай краткое саммари.",
            )
        )

        messages = fake_client.chat.completions.calls[0]["messages"]
        user_prompt = messages[-1]["content"]
        self.assertTrue(user_prompt.rstrip().endswith("Summary Language: Русский"))

    def test_gpt5_chat_completion_uses_supported_token_parameter(self):
        summarizer = Summarizer(model="gpt-5.4")
        fake_client = _FakeClient()
        summarizer.client = fake_client

        asyncio.run(summarizer._summarize_single_text("Transcript body", "en", "Video"))

        call = fake_client.chat.completions.calls[0]
        self.assertEqual(call["model"], "gpt-5.4")
        self.assertEqual(call["max_completion_tokens"], 3500)
        self.assertNotIn("max_tokens", call)
        self.assertNotIn("temperature", call)

    def test_reasoning_effort_is_sent_for_supported_models(self):
        summarizer = Summarizer(model="gpt-5.4", reasoning_effort="high")
        fake_client = _FakeClient()
        summarizer.client = fake_client

        asyncio.run(summarizer._summarize_single_text("Transcript body", "en", "Video"))

        call = fake_client.chat.completions.calls[0]
        self.assertEqual(call["reasoning_effort"], "high")

    def test_reasoning_effort_is_not_sent_for_non_reasoning_models(self):
        summarizer = Summarizer(model="gpt-4o", reasoning_effort="high")
        fake_client = _FakeClient()
        summarizer.client = fake_client

        asyncio.run(summarizer._summarize_single_text("Transcript body", "en", "Video"))

        call = fake_client.chat.completions.calls[0]
        self.assertEqual(call["max_tokens"], 3500)
        self.assertEqual(call["temperature"], 0.3)
        self.assertNotIn("reasoning_effort", call)

    def test_provider_errors_are_not_hidden_as_chunk_summaries(self):
        summarizer = Summarizer(model="gpt-5.4")
        summarizer.client = _FailingClient()

        with self.assertRaises(RuntimeError):
            asyncio.run(
                summarizer._summarize_with_chunks(
                    "Paragraph one.\n\nParagraph two.",
                    "ru",
                    "Video",
                    max_tokens=1000,
                )
            )


if __name__ == "__main__":
    unittest.main()

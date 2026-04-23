import asyncio
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import main  # noqa: E402


class PlanContractTests(unittest.TestCase):
    def setUp(self):
        self._old_tasks = main.tasks
        self._old_processing_urls = main.processing_urls
        self._old_active_tasks = main.active_tasks
        self._old_active_summary_tasks = main.active_summary_tasks
        self._old_video_processor = main.video_processor
        self._old_summarizer = main.summarizer
        self._old_temp_dir = main.TEMP_DIR

        main.tasks = {}
        main.processing_urls = set()
        main.active_tasks = {}
        main.active_summary_tasks = {}
        self.temp_dir = PROJECT_ROOT / "temp" / "test_plan_contract"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        main.TEMP_DIR = self.temp_dir

    def tearDown(self):
        main.tasks = self._old_tasks
        main.processing_urls = self._old_processing_urls
        main.active_tasks = self._old_active_tasks
        main.active_summary_tasks = self._old_active_summary_tasks
        main.video_processor = self._old_video_processor
        main.summarizer = self._old_summarizer
        main.TEMP_DIR = self._old_temp_dir
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_transcription_task_exposes_planned_contract_and_manual_source(self):
        class FakeVideoProcessor:
            async def fetch_subtitles(self, url, output_dir):
                return (
                    "# Video Transcription\n\nManual subtitle text",
                    "Manual Source Video",
                    "en",
                    "youtube_manual_subtitles",
                )

        main.video_processor = FakeVideoProcessor()
        task_id = "manual-source-task"
        main.tasks[task_id] = {"status": "processing", "url": "https://youtu.be/manual"}
        main.processing_urls.add("https://youtu.be/manual")

        asyncio.run(main.process_video_task(task_id, "https://youtu.be/manual", skip_subtitles=False))

        task = main.tasks[task_id]
        self.assertEqual(task["status"], "completed")
        self.assertIn("Manual subtitle text", task["transcript"])
        self.assertEqual(task["transcript_source"], "youtube_manual_subtitles")
        self.assertEqual(task["transcription_source"], "youtube_manual_subtitles")
        self.assertEqual(task["script"], task["transcript"])

    def test_transcription_task_strips_timecodes_by_default(self):
        class FakeVideoProcessor:
            async def fetch_subtitles(self, url, output_dir):
                return (
                    "# Video Transcription\n\n"
                    "## Transcription Content\n\n"
                    "**[00:02 - 00:04]**\n\n"
                    "Subtitle text",
                    "No Timecodes Video",
                    "en",
                    "youtube_auto_subtitles",
                )

        main.video_processor = FakeVideoProcessor()
        task_id = "no-timecodes-task"
        main.tasks[task_id] = {"status": "processing", "url": "https://youtu.be/no-timecodes"}
        main.processing_urls.add("https://youtu.be/no-timecodes")

        asyncio.run(main.process_video_task(task_id, "https://youtu.be/no-timecodes", skip_subtitles=False))

        task = main.tasks[task_id]
        self.assertEqual(task["status"], "completed")
        self.assertNotIn("[00:02 - 00:04]", task["transcript"])
        self.assertIn("Subtitle text", task["transcript"])

    def test_transcription_task_can_keep_timecodes(self):
        class FakeVideoProcessor:
            async def fetch_subtitles(self, url, output_dir):
                return (
                    "# Video Transcription\n\n"
                    "## Transcription Content\n\n"
                    "**[00:02 - 00:04]**\n\n"
                    "Subtitle text",
                    "With Timecodes Video",
                    "en",
                    "youtube_auto_subtitles",
                )

        main.video_processor = FakeVideoProcessor()
        task_id = "with-timecodes-task"
        main.tasks[task_id] = {"status": "processing", "url": "https://youtu.be/with-timecodes"}
        main.processing_urls.add("https://youtu.be/with-timecodes")

        asyncio.run(
            main.process_video_task(
                task_id,
                "https://youtu.be/with-timecodes",
                include_timecodes=True,
                skip_subtitles=False,
            )
        )

        task = main.tasks[task_id]
        self.assertEqual(task["status"], "completed")
        self.assertIn("[00:02 - 00:04]", task["transcript"])
        self.assertIn("Subtitle text", task["transcript"])

    def test_transcription_task_can_force_groq_without_fetching_subtitles(self):
        class FakeVideoProcessor:
            async def fetch_subtitles(self, url, output_dir):
                raise AssertionError("subtitle stage should be skipped")

            async def extract_audio_url(self, url):
                return {
                    "title": "Forced Groq Video",
                    "audio_url": "https://media.example/forced.m4a",
                }

        class FakeGroq:
            async def transcribe_url(self, audio_url, language="", prompt=""):
                return {
                    "markdown": "# Video Transcription\n\nForced Groq transcription",
                    "language": "en",
                }

        main.video_processor = FakeVideoProcessor()
        task_id = "forced-groq-task"
        url = "https://youtu.be/forced-groq"
        main.tasks[task_id] = {"status": "processing", "url": url}
        main.processing_urls.add(url)

        with patch.object(main, "GroqURLTranscriber", return_value=FakeGroq()):
            asyncio.run(main.process_video_task(task_id, url, groq_api_key="gsk-test", skip_subtitles=True))

        task = main.tasks[task_id]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["transcript_source"], "groq_audio_url")
        self.assertIn("Forced Groq transcription", task["transcript"])

    def test_summarize_without_key_rejects_instead_of_generating_fallback(self):
        task_id = "missing-summary-key-task"
        main.tasks[task_id] = {
            "status": "completed",
            "script": "Transcript body",
            "transcript": "Transcript body",
            "video_title": "Video",
            "url": "https://youtu.be/no-key",
            "short_id": "nokey1",
            "safe_title": "Video",
        }

        with self.assertRaises(main.HTTPException) as ctx:
            asyncio.run(main.summarize_transcript(task_id=task_id, api_key="", output_format="markdown"))

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("summary provider", str(ctx.exception.detail).lower())
        self.assertIsNone(main.tasks[task_id].get("summary"))

    def test_summarize_endpoint_starts_background_summary_job(self):
        class FakeSummarizer:
            async def summarize(self, transcript, target_language, video_title, custom_prompt=""):
                return "# Summary\n\nDone"

        task_id = "async-summary-task"
        main.tasks[task_id] = {
            "status": "completed",
            "script": "Transcript body",
            "transcript": "Transcript body",
            "video_title": "Video",
            "url": "https://youtu.be/async",
            "short_id": "async1",
            "safe_title": "Video",
        }

        async def run_endpoint():
            response = await main.summarize_transcript(
                task_id=task_id,
                summary_language="en",
                api_key="sk-test",
                model_base_url="",
                model_id="test-model",
                output_format="markdown",
            )
            self.assertEqual(response["summary_status"], "processing")
            self.assertEqual(main.tasks[task_id]["summary_status"], "processing")
            await main.active_summary_tasks[task_id]

        with patch.object(main, "Summarizer", return_value=FakeSummarizer()):
            asyncio.run(
                run_endpoint()
            )

    def test_summarize_endpoint_passes_custom_summary_prompt(self):
        class FakeSummarizer:
            def __init__(self):
                self.calls = []

            async def summarize(self, transcript, target_language, video_title, custom_prompt=""):
                self.calls.append({
                    "transcript": transcript,
                    "target_language": target_language,
                    "video_title": video_title,
                    "custom_prompt": custom_prompt,
                })
                return "# Summary\n\nDone"

        fake_summarizer = FakeSummarizer()
        task_id = "custom-summary-prompt-task"
        main.tasks[task_id] = {
            "status": "completed",
            "script": "Transcript body",
            "transcript": "Transcript body",
            "video_title": "Video",
            "url": "https://youtu.be/custom-prompt",
            "short_id": "prompt1",
            "safe_title": "Video",
        }

        async def run_endpoint():
            response = await main.summarize_transcript(
                task_id=task_id,
                summary_language="en",
                api_key="sk-test",
                model_base_url="",
                model_id="test-model",
                output_format="markdown",
                summary_prompt="Focus on action items and open questions.",
                reasoning_effort="high",
            )
            self.assertEqual(response["summary_status"], "processing")
            await main.active_summary_tasks[task_id]

        with patch.object(main, "Summarizer", return_value=fake_summarizer) as summarizer_cls:
            asyncio.run(run_endpoint())

        self.assertEqual(summarizer_cls.call_args.kwargs["reasoning_effort"], "high")
        self.assertEqual(fake_summarizer.calls[0]["custom_prompt"], "Focus on action items and open questions.")
        self.assertEqual(main.tasks[task_id]["summary_prompt"], "Focus on action items and open questions.")
        self.assertEqual(main.tasks[task_id]["summary_reasoning_effort"], "high")

    def test_groq_media_fetch_error_refreshes_audio_url_and_retries_once(self):
        class FakeVideoProcessor:
            def __init__(self):
                self.extract_calls = 0

            async def fetch_subtitles(self, url, output_dir):
                return None, "Retry Video", None, None

            async def extract_audio_url(self, url):
                self.extract_calls += 1
                return {
                    "title": "Retry Video",
                    "audio_url": f"https://media.example/audio-{self.extract_calls}.m4a",
                }

        class FakeGroq:
            def __init__(self, api_key, model):
                self.transcribed_urls = []

            async def transcribe_url(self, audio_url, language="", prompt=""):
                self.transcribed_urls.append(audio_url)
                if len(self.transcribed_urls) == 1:
                    raise main.GroqTranscriptionError("failed to retrieve media: received status code: 302")
                return {
                    "markdown": "# Video Transcription\n\nRecovered transcription",
                    "language": "en",
                }

        fake_processor = FakeVideoProcessor()
        fake_groq = FakeGroq(api_key="gsk-test", model="whisper-large-v3-turbo")
        main.video_processor = fake_processor
        task_id = "groq-retry-task"
        url = "https://youtu.be/retry"
        main.tasks[task_id] = {"status": "processing", "url": url}
        main.processing_urls.add(url)

        with patch.object(main, "GroqURLTranscriber", return_value=fake_groq):
            asyncio.run(main.process_video_task(task_id, url, groq_api_key="gsk-test"))

        task = main.tasks[task_id]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(fake_processor.extract_calls, 2)
        self.assertEqual(
            fake_groq.transcribed_urls,
            [
                "https://media.example/audio-1.m4a",
                "https://media.example/audio-2.m4a",
            ],
        )
        self.assertIn("Recovered transcription", task["transcript"])

    def test_groq_media_fetch_error_falls_back_to_local_file_upload(self):
        class FakeVideoProcessor:
            def __init__(self):
                self.upload_download_calls = 0

            async def fetch_subtitles(self, url, output_dir):
                return None, "Fallback Video", None, None

            async def extract_audio_url(self, url):
                return {
                    "title": "Fallback Video",
                    "audio_url": "https://media.example/fallback.m4a",
                }

            async def download_audio_for_upload(self, url, output_dir):
                self.upload_download_calls += 1
                audio_path = output_dir / "fallback.m4a"
                audio_path.write_bytes(b"fake audio")
                return str(audio_path), "Fallback Video"

        class FakeGroq:
            def __init__(self):
                self.file_paths = []

            async def transcribe_url(self, audio_url, language="", prompt=""):
                raise main.GroqTranscriptionError("failed to retrieve media: received status code: 302")

            async def transcribe_file(self, audio_file, language="", prompt=""):
                self.file_paths.append(audio_file)
                return {
                    "markdown": "# Video Transcription\n\nUploaded file transcription",
                    "language": "en",
                }

        fake_processor = FakeVideoProcessor()
        fake_groq = FakeGroq()
        main.video_processor = fake_processor
        task_id = "groq-file-fallback-task"
        url = "https://youtu.be/file-fallback"
        main.tasks[task_id] = {"status": "processing", "url": url}
        main.processing_urls.add(url)

        with patch.object(main, "GroqURLTranscriber", return_value=fake_groq):
            asyncio.run(main.process_video_task(task_id, url, groq_api_key="gsk-test"))

        task = main.tasks[task_id]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["transcript_source"], "groq_audio_file")
        self.assertEqual(fake_processor.upload_download_calls, 1)
        self.assertEqual(len(fake_groq.file_paths), 1)
        self.assertIn("Uploaded file transcription", task["transcript"])

    def test_groq_media_fetch_error_reports_actionable_message_after_file_fallback_fails(self):
        class FakeVideoProcessor:
            async def fetch_subtitles(self, url, output_dir):
                return None, "Blocked Video", None, None

            async def extract_audio_url(self, url):
                return {
                    "title": "Blocked Video",
                    "audio_url": "https://media.example/blocked.m4a",
                }

            async def download_and_convert(self, url, output_dir):
                audio_path = output_dir / "blocked.m4a"
                audio_path.write_bytes(b"fake audio")
                return str(audio_path), "Blocked Video"

        class FakeGroq:
            async def transcribe_url(self, audio_url, language="", prompt=""):
                raise main.GroqTranscriptionError("context deadline exceeded")

            async def transcribe_file(self, audio_file, language="", prompt=""):
                raise main.GroqTranscriptionError("file upload rejected")

        main.video_processor = FakeVideoProcessor()
        task_id = "groq-actionable-error-task"
        url = "https://youtu.be/blocked"
        main.tasks[task_id] = {"status": "processing", "url": url}
        main.processing_urls.add(url)

        with patch.object(main, "GroqURLTranscriber", return_value=FakeGroq()):
            asyncio.run(main.process_video_task(task_id, url, groq_api_key="gsk-test"))

        task = main.tasks[task_id]
        self.assertEqual(task["status"], "error")
        self.assertIn("Groq could not retrieve the temporary media URL", task["error"])
        self.assertIn("local file upload fallback also failed", task["error"])


class WindowsLauncherTests(unittest.TestCase):
    def test_windows_launcher_uses_production_mode(self):
        launcher = (PROJECT_ROOT / "start_windows.bat").read_text(encoding="utf-8")

        self.assertIn("python start.py --prod", launcher)


if __name__ == "__main__":
    unittest.main()

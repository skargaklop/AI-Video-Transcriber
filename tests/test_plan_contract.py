import asyncio
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import main  # noqa: E402
import local_transcription  # noqa: E402


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

    def test_summarize_endpoint_can_generate_txt_summary_file(self):
        class FakeSummarizer:
            async def summarize(self, transcript, target_language, video_title, custom_prompt=""):
                return "# Summary\n\nPlain text body"

        task_id = "txt-summary-task"
        main.tasks[task_id] = {
            "status": "completed",
            "script": "Transcript body",
            "transcript": "Transcript body",
            "video_title": "Video",
            "url": "https://youtu.be/txt-summary",
            "short_id": "txt001",
            "safe_title": "Video",
        }

        async def run_endpoint():
            response = await main.summarize_transcript(
                task_id=task_id,
                summary_language="en",
                api_key="sk-test",
                model_base_url="",
                model_id="test-model",
                output_format="txt",
            )
            self.assertEqual(response["summary_status"], "processing")
            await main.active_summary_tasks[task_id]

        with patch.object(main, "Summarizer", return_value=FakeSummarizer()):
            asyncio.run(run_endpoint())

        task = main.tasks[task_id]
        self.assertEqual(task["summary_output_format"], "txt")
        self.assertIsNotNone(task["summary_text_path"])
        self.assertTrue(task["summary_text_path"].endswith(".txt"))
        self.assertTrue(Path(task["summary_text_path"]).exists())
        self.assertIn("Plain text body", Path(task["summary_text_path"]).read_text(encoding="utf-8"))

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

    def test_local_provider_can_bypass_subtitles_and_use_whisper_backend(self):
        class FakeVideoProcessor:
            async def fetch_subtitles(self, url, output_dir):
                raise AssertionError("subtitle stage should be skipped")

            async def download_and_convert(self, url, output_dir):
                audio_path = output_dir / "local_whisper.m4a"
                audio_path.write_bytes(b"fake audio")
                return str(audio_path), "Local Whisper Video"

        class FakeLocalTranscriber:
            def __init__(self):
                self.calls = []

            async def transcribe(self, audio_path, language=""):
                self.calls.append({"audio_path": audio_path, "language": language})
                return {
                    "markdown": "# Video Transcription\n\nLocal whisper transcription",
                    "language": "en",
                    "warnings": [],
                    "runtime": "cpu",
                    "timestamps_supported": True,
                }

        fake_local = FakeLocalTranscriber()
        main.video_processor = FakeVideoProcessor()
        task_id = "local-whisper-task"
        url = "https://youtu.be/local-whisper"
        main.tasks[task_id] = {"status": "processing", "url": url}
        main.processing_urls.add(url)

        with patch.object(main, "prepare_local_transcriber", return_value=(fake_local, "base")):
            asyncio.run(
                main.process_video_task(
                    task_id,
                    url,
                    transcription_provider="local",
                    try_subtitles_first=False,
                    local_backend="whisper",
                    local_model_preset="base",
                    local_language="en",
                )
            )

        task = main.tasks[task_id]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["transcription_provider_requested"], "local")
        self.assertEqual(task["transcription_provider_used"], "local")
        self.assertEqual(task["transcript_source"], "local_audio_file")
        self.assertEqual(task["local_backend_used"], "whisper")
        self.assertEqual(task["local_model_used"], "base")
        self.assertFalse(task["used_local_fallback"])
        self.assertIn("Local whisper transcription", task["transcript"])
        self.assertEqual(fake_local.calls[0]["language"], "en")

    def test_local_provider_reports_detailed_stage_metadata_while_preparing_model(self):
        class FakeVideoProcessor:
            async def fetch_subtitles(self, url, output_dir):
                raise AssertionError("subtitle stage should be skipped")

            async def download_and_convert(self, url, output_dir):
                audio_path = output_dir / "local_stage_test.m4a"
                audio_path.write_bytes(b"fake audio")
                return str(audio_path), "Local Stage Video"

        class FakeLocalTranscriber:
            async def transcribe(self, audio_path, language=""):
                return {
                    "markdown": "# Video Transcription\n\nLocal parakeet transcription",
                    "language": "en",
                    "warnings": [],
                    "runtime": "cpu",
                    "timestamps_supported": True,
                }

        stage_events = []

        async def fake_broadcast(task_id, task_data):
            stage_events.append(
                {
                    "flow": task_data.get("stage_flow"),
                    "code": task_data.get("stage_code"),
                    "message": task_data.get("message"),
                    "index": task_data.get("stage_index"),
                    "total": task_data.get("stage_total"),
                }
            )

        main.video_processor = FakeVideoProcessor()
        task_id = "local-stage-task"
        url = "https://youtu.be/local-stage"
        main.tasks[task_id] = {"status": "processing", "url": url}
        main.processing_urls.add(url)

        with patch.object(main, "broadcast_task_update", side_effect=fake_broadcast):
            with patch.object(main, "backend_dependencies_available", return_value=False):
                with patch.object(main, "ensure_backend_dependencies") as ensure_deps:
                    with patch.object(main, "ensure_backend_audio_file", side_effect=lambda audio_path, backend, output_dir: audio_path):
                        with patch.object(main, "prepare_local_transcriber", return_value=(FakeLocalTranscriber(), "nvidia/parakeet-tdt-0.6b-v3")) as prepare_local:
                            asyncio.run(
                                main.process_video_task(
                                    task_id,
                                    url,
                                    transcription_provider="local",
                                    try_subtitles_first=False,
                                    local_backend="parakeet",
                                    local_model_preset="nvidia/parakeet-tdt-0.6b-v3",
                                )
                            )

        task = main.tasks[task_id]
        codes = [event["code"] for event in stage_events if event.get("code")]

        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["stage_flow"], "local")
        self.assertEqual(task["stage_code"], "completed")
        self.assertTrue(task.get("stage_started_at"))
        self.assertGreaterEqual(task.get("stage_total") or 0, 8)
        self.assertEqual(task.get("stage_index"), task.get("stage_total"))
        self.assertEqual(task["local_backend_used"], "parakeet")
        self.assertEqual(task["local_model_used"], "nvidia/parakeet-tdt-0.6b-v3")
        self.assertIn("subtitle_skipped", codes)
        self.assertIn("downloading_audio", codes)
        self.assertIn("preparing_audio", codes)
        self.assertIn("installing_local_backend", codes)
        self.assertIn("loading_local_model", codes)
        self.assertIn("transcribing_local_audio", codes)
        self.assertIn("saving_transcript", codes)
        self.assertIn("completed", codes)
        ensure_deps.assert_called_once_with("parakeet")
        prepare_local.assert_called_once()

    def test_local_provider_uses_subtitles_first_when_enabled(self):
        class FakeVideoProcessor:
            def __init__(self):
                self.subtitle_calls = 0
                self.download_calls = 0

            async def fetch_subtitles(self, url, output_dir):
                self.subtitle_calls += 1
                return (
                    "# Video Transcription\n\nSubtitle transcript",
                    "Subtitle First Video",
                    "en",
                    "youtube_auto_subtitles",
                )

            async def download_and_convert(self, url, output_dir):
                self.download_calls += 1
                raise AssertionError("local audio path should not run when subtitles are available")

        main.video_processor = FakeVideoProcessor()
        task_id = "local-subtitle-first-task"
        url = "https://youtu.be/local-subtitle-first"
        main.tasks[task_id] = {"status": "processing", "url": url}
        main.processing_urls.add(url)

        with patch.object(main, "prepare_local_transcriber") as prepare_local:
            asyncio.run(
                main.process_video_task(
                    task_id,
                    url,
                    transcription_provider="local",
                    try_subtitles_first=True,
                    local_backend="whisper",
                    local_model_preset="base",
                )
            )

        task = main.tasks[task_id]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["transcript_source"], "youtube_auto_subtitles")
        self.assertEqual(task["transcription_provider_used"], "subtitles")
        self.assertIsNone(task["local_backend_used"])
        self.assertFalse(task["used_local_fallback"])
        self.assertEqual(main.video_processor.subtitle_calls, 1)
        self.assertEqual(main.video_processor.download_calls, 0)
        prepare_local.assert_not_called()

    def test_local_api_provider_uses_selected_api_model(self):
        class FakeVideoProcessor:
            async def fetch_subtitles(self, url, output_dir):
                return None, "Local API Video", None, None

            async def download_and_convert(self, url, output_dir):
                audio_path = output_dir / "local_api_audio.m4a"
                audio_path.write_bytes(b"fake local api audio")
                return str(audio_path), "Local API Video"

        class FakeLocalAPI:
            def __init__(self, base_url, model, api_key="", endpoint_path="/audio/transcriptions", timeout=300):
                self.base_url = base_url
                self.model = model
                self.api_key = api_key

            async def transcribe_file(self, audio_file, language="", prompt=""):
                return {
                    "markdown": "# Video Transcription\n\nRecovered by local api",
                    "language": "en",
                    "model": self.model,
                }

        main.video_processor = FakeVideoProcessor()
        task_id = "local-api-task"
        url = "https://youtu.be/local-api"
        main.tasks[task_id] = {"status": "processing", "url": url}
        main.processing_urls.add(url)

        with patch.object(main, "LocalAPITranscriber", FakeLocalAPI):
            asyncio.run(
                main.process_video_task(
                    task_id,
                    url,
                    transcription_provider="local_api",
                    try_subtitles_first=False,
                    local_api_base_url="http://127.0.0.1:11434/v1",
                    local_api_model="whisper-large-v3",
                    local_api_language="en",
                    local_api_prompt="names",
                )
            )

        task = main.tasks[task_id]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["transcription_provider_used"], "local_api")
        self.assertEqual(task["transcript_source"], "local_api_audio_file")
        self.assertEqual(task["local_model_used"], "whisper-large-v3")
        self.assertIn("Recovered by local api", task["transcript"])

    def test_groq_provider_can_fall_back_to_local_backend_for_eligible_errors(self):
        class FakeVideoProcessor:
            async def fetch_subtitles(self, url, output_dir):
                return None, "Groq To Local Video", None, None

            async def extract_audio_url(self, url):
                return {
                    "title": "Groq To Local Video",
                    "audio_url": "https://media.example/groq-local.m4a",
                }

            async def download_audio_for_upload(self, url, output_dir):
                audio_path = output_dir / "groq_upload_fail.m4a"
                audio_path.write_bytes(b"fake upload audio")
                return str(audio_path), "Groq To Local Video"

            async def download_and_convert(self, url, output_dir):
                audio_path = output_dir / "groq_local_fallback.m4a"
                audio_path.write_bytes(b"fake local audio")
                return str(audio_path), "Groq To Local Video"

        class FakeGroq:
            async def transcribe_url(self, audio_url, language="", prompt=""):
                raise main.GroqTranscriptionError("context deadline exceeded")

            async def transcribe_file(self, audio_file, language="", prompt=""):
                raise main.GroqTranscriptionError("temporary upstream timeout")

        class FakeLocalTranscriber:
            async def transcribe(self, audio_path, language=""):
                return {
                    "markdown": "# Video Transcription\n\nRecovered by local fallback",
                    "language": "en",
                    "warnings": ["CPU mode may be slow."],
                    "runtime": "cpu",
                    "timestamps_supported": True,
                }

        main.video_processor = FakeVideoProcessor()
        task_id = "groq-local-fallback-task"
        url = "https://youtu.be/groq-local-fallback"
        main.tasks[task_id] = {"status": "processing", "url": url}
        main.processing_urls.add(url)

        with patch.object(main, "GroqURLTranscriber", return_value=FakeGroq()):
            with patch.object(main, "prepare_local_transcriber", return_value=(FakeLocalTranscriber(), "small")):
                asyncio.run(
                    main.process_video_task(
                        task_id,
                        url,
                        transcription_provider="groq",
                        groq_api_key="gsk-test",
                        try_subtitles_first=True,
                        use_local_fallback=True,
                        local_backend="whisper",
                        local_model_preset="small",
                    )
                )

        task = main.tasks[task_id]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["transcription_provider_requested"], "groq")
        self.assertEqual(task["transcription_provider_used"], "local")
        self.assertEqual(task["transcript_source"], "local_audio_file")
        self.assertTrue(task["used_local_fallback"])
        self.assertEqual(task["local_backend_used"], "whisper")
        self.assertEqual(task["local_model_used"], "small")
        self.assertIn("Recovered by local fallback", task["transcript"])
        self.assertIn("CPU mode may be slow.", task["warnings"])

    def test_groq_invalid_credentials_do_not_fall_back_to_local(self):
        class FakeVideoProcessor:
            async def fetch_subtitles(self, url, output_dir):
                return None, "Invalid Groq Video", None, None

            async def extract_audio_url(self, url):
                return {
                    "title": "Invalid Groq Video",
                    "audio_url": "https://media.example/invalid-key.m4a",
                }

        class FakeGroq:
            async def transcribe_url(self, audio_url, language="", prompt=""):
                raise main.GroqTranscriptionError("invalid api key")

        main.video_processor = FakeVideoProcessor()
        task_id = "groq-invalid-key-task"
        url = "https://youtu.be/invalid-key"
        main.tasks[task_id] = {"status": "processing", "url": url}
        main.processing_urls.add(url)

        with patch.object(main, "GroqURLTranscriber", return_value=FakeGroq()):
            with patch.object(main, "prepare_local_transcriber") as prepare_local:
                asyncio.run(
                    main.process_video_task(
                        task_id,
                        url,
                        transcription_provider="groq",
                        use_local_fallback=True,
                        local_backend="whisper",
                        local_model_preset="base",
                        groq_api_key="gsk-test",
                    )
                )

        task = main.tasks[task_id]
        self.assertEqual(task["status"], "error")
        self.assertFalse(task.get("used_local_fallback"))
        prepare_local.assert_not_called()

    def test_local_model_capabilities_report_missing_optional_dependencies(self):
        import importlib.util

        original_find_spec = importlib.util.find_spec

        def fake_find_spec(name, package=None):
            if name in {"faster_whisper", "nemo", "nemo.collections", "nemo.collections.asr"}:
                return None
            return original_find_spec(name, package)

        with patch.object(main.importlib.util, "find_spec", side_effect=fake_find_spec):
            caps = asyncio.run(main.get_local_model_capabilities())

        self.assertIn("backends", caps)
        self.assertFalse(caps["backends"]["whisper"]["available"])
        self.assertFalse(caps["backends"]["parakeet"]["available"])
        self.assertTrue(caps["backends"]["whisper"]["custom_supported"])
        self.assertTrue(caps["backends"]["parakeet"]["custom_supported"])
        self.assertTrue(caps["backends"]["whisper"]["auto_install"])
        self.assertTrue(caps["backends"]["parakeet"]["auto_install"])

    def test_local_model_capabilities_report_parakeet_auto_install_unsupported_on_windows_py313(self):
        import importlib.util

        original_find_spec = importlib.util.find_spec

        def fake_find_spec(name, package=None):
            if name in {"nemo", "nemo.collections", "nemo.collections.asr"}:
                return None
            return original_find_spec(name, package)

        with patch.object(main.importlib.util, "find_spec", side_effect=fake_find_spec):
            with patch.object(local_transcription.sys, "platform", "win32"):
                with patch.object(local_transcription.sys, "version_info", (3, 13, 0)):
                    caps = asyncio.run(main.get_local_model_capabilities())

        parakeet_caps = caps["backends"]["parakeet"]
        self.assertFalse(parakeet_caps["available"])
        self.assertFalse(parakeet_caps["auto_install"])
        self.assertEqual(
            parakeet_caps["warning_code"],
            "parakeet_windows_py313_requires_build_tools",
        )


class WindowsLauncherTests(unittest.TestCase):
    def test_windows_launcher_uses_production_mode(self):
        launcher = (PROJECT_ROOT / "start_windows.bat").read_text(encoding="utf-8")

        self.assertIn("python start.py --prod", launcher)


class LocalTranscriptionHelpersTests(unittest.TestCase):
    def test_prepare_local_transcriber_uses_selected_model_and_preloads_it(self):
        loaded_models = []

        class FakeWhisperTranscriber:
            @staticmethod
            def dependency_available(importlib_module=None):
                return True

            def __init__(self, model_id):
                self.model_id = model_id

            def _load_model(self):
                loaded_models.append(self.model_id)

        with patch.object(local_transcription, "WhisperLocalTranscriber", FakeWhisperTranscriber):
            transcriber, resolved_model_id = local_transcription.prepare_local_transcriber(
                local_backend="whisper",
                local_model_preset="small",
                local_model_id="",
            )

        self.assertEqual(resolved_model_id, "small")
        self.assertEqual(transcriber.model_id, "small")
        self.assertEqual(loaded_models, ["small"])

    def test_prepare_local_transcriber_passes_custom_model_id_through(self):
        loaded_models = []

        class FakeParakeetTranscriber:
            @staticmethod
            def dependency_available(importlib_module=None):
                return True

            def __init__(self, model_id):
                self.model_id = model_id

            def _load_model(self):
                loaded_models.append(self.model_id)

        custom_model = "D:/models/parakeet-custom"
        with patch.object(local_transcription, "ParakeetLocalTranscriber", FakeParakeetTranscriber):
            transcriber, resolved_model_id = local_transcription.prepare_local_transcriber(
                local_backend="parakeet",
                local_model_preset="custom",
                local_model_id=custom_model,
            )

        self.assertEqual(resolved_model_id, custom_model)
        self.assertEqual(transcriber.model_id, custom_model)
        self.assertEqual(loaded_models, [custom_model])

    def test_install_backend_dependencies_rejects_parakeet_auto_install_on_windows_py313(self):
        with patch.object(local_transcription.sys, "platform", "win32"):
            with patch.object(local_transcription.sys, "version_info", (3, 13, 0)):
                with self.assertRaises(local_transcription.LocalTranscriptionError) as ctx:
                    local_transcription.install_backend_dependencies("parakeet")

        self.assertIn("Python 3.13", str(ctx.exception))
        self.assertIn("Microsoft C++ Build Tools", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

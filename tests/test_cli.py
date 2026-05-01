"""Tests for the AI Video Transcriber CLI."""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import cli
from cli import AGENT_MANIFEST, build_parser, main


class TestAgentHelp(unittest.TestCase):
    def test_manifest_is_valid_json(self):
        text = json.dumps(AGENT_MANIFEST, indent=2)
        parsed = json.loads(text)
        self.assertIsInstance(parsed, dict)

    def test_manifest_required_keys(self):
        for key in ("name", "version", "description", "guide", "commands", "exit_codes", "env_vars"):
            self.assertIn(key, AGENT_MANIFEST)

    def test_manifest_commands(self):
        commands = AGENT_MANIFEST["commands"]
        for name in ("transcribe", "summarize", "pipeline", "tasks"):
            self.assertIn(name, commands)
            self.assertIn("description", commands[name])

    def test_agent_help_flag(self):
        with patch("sys.argv", ["cli.py", "--agent-help"]):
            with patch("builtins.print") as mock_print:
                code = main()
                self.assertEqual(code, 0)
                output = mock_print.call_args[0][0]
                parsed = json.loads(output)
                self.assertEqual(parsed["name"], "ai-video-transcriber-cli")


class TestBuildParser(unittest.TestCase):
    def test_parser_created(self):
        parser = build_parser()
        self.assertIsNotNone(parser)

    def test_no_command_returns_2(self):
        with patch("sys.argv", ["cli.py"]):
            code = main()
            self.assertEqual(code, 2)

    def test_transcribe_args_url(self):
        parser = build_parser()
        args = parser.parse_args(["transcribe", "--url", "https://youtu.be/test"])
        self.assertEqual(args.url, "https://youtu.be/test")
        self.assertEqual(args.command, "transcribe")

    def test_transcribe_args_file(self):
        parser = build_parser()
        args = parser.parse_args(["transcribe", "--file", "/path/to/audio.mp3"])
        self.assertEqual(args.file, "/path/to/audio.mp3")

    def test_transcribe_args_provider(self):
        parser = build_parser()
        args = parser.parse_args(["transcribe", "--url", "http://x", "--provider", "local"])
        self.assertEqual(args.provider, "local")

    def test_transcribe_args_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["transcribe", "--url", "http://x"])
        self.assertEqual(args.provider, "groq")
        self.assertEqual(args.groq_model, "")
        self.assertEqual(args.language, "")
        self.assertFalse(args.include_timecodes)
        self.assertFalse(args.skip_subtitles)
        self.assertEqual(args.local_backend, "whisper")
        self.assertEqual(args.local_model, "base")
        self.assertEqual(args.format, "json")

    def test_summarize_args(self):
        parser = build_parser()
        args = parser.parse_args(["summarize", "--task-id", "abc-123"])
        self.assertEqual(args.task_id, "abc-123")
        self.assertEqual(args.command, "summarize")

    def test_summarize_args_transcript_file(self):
        parser = build_parser()
        args = parser.parse_args(["summarize", "--transcript-file", "transcript.md"])
        self.assertEqual(args.transcript_file, "transcript.md")

    def test_summarize_args_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["summarize", "--task-id", "abc"])
        self.assertEqual(args.model, "")
        self.assertEqual(args.summary_lang, "en")
        self.assertEqual(args.output_format, "markdown")
        self.assertEqual(args.reasoning_effort, "")

    def test_pipeline_args(self):
        parser = build_parser()
        args = parser.parse_args(["pipeline", "--url", "http://x", "--task-id", "abc"])
        self.assertEqual(args.command, "pipeline")
        self.assertEqual(args.url, "http://x")
        self.assertEqual(args.task_id, "abc")

    def test_tasks_args(self):
        parser = build_parser()
        args = parser.parse_args(["tasks", "--list"])
        self.assertTrue(args.list)

    def test_tasks_get(self):
        parser = build_parser()
        args = parser.parse_args(["tasks", "--get", "abc-123"])
        self.assertEqual(args.get, "abc-123")

    def test_tasks_delete(self):
        parser = build_parser()
        args = parser.parse_args(["tasks", "--delete", "abc-123"])
        self.assertEqual(args.delete, "abc-123")


class TestTranscribeCommand(unittest.TestCase):
    def test_missing_url_and_file(self):
        with patch("sys.argv", ["cli.py", "transcribe"]):
            code = main()
            self.assertEqual(code, 2)

    @patch("cli.asyncio.run")
    @patch("cli._patch_broadcast")
    @patch("cli._output_result")
    def test_successful_transcribe(self, mock_output, mock_patch, mock_run):
        mock_run.return_value = {
            "task_id": "test-id",
            "status": "completed",
            "video_title": "Test Video",
            "transcript": "Hello world",
            "detected_language": "en",
            "transcript_source": "groq_audio_url",
        }
        with patch("sys.argv", ["cli.py", "transcribe", "--url", "https://youtu.be/test"]):
            code = main()
            self.assertEqual(code, 0)
            mock_output.assert_called_once()


class TestSummarizeCommand(unittest.TestCase):
    def test_missing_task_id_and_file(self):
        with patch("sys.argv", ["cli.py", "summarize"]):
            code = main()
            self.assertEqual(code, 2)


class TestTasksCommand(unittest.TestCase):
    def test_no_flag_returns_error(self):
        with patch("sys.argv", ["cli.py", "tasks"]):
            code = main()
            self.assertEqual(code, 2)

    @patch("cli._patch_broadcast")
    def test_list_tasks(self, mock_patch):
        import main as backend_main

        original_tasks = backend_main.tasks.copy()
        backend_main.tasks["test-id"] = {"status": "completed", "video_title": "Test"}
        try:
            with patch("sys.argv", ["cli.py", "tasks", "--list"]):
                with patch("cli._output_result") as mock_output:
                    code = main()
                    self.assertEqual(code, 0)
                    call_args = mock_output.call_args[0][0]
                    self.assertIn("tasks", call_args)
        finally:
            backend_main.tasks = original_tasks

    @patch("cli._patch_broadcast")
    def test_get_nonexistent_task(self, mock_patch):
        import main as backend_main

        original_tasks = backend_main.tasks.copy()
        backend_main.tasks = {}
        try:
            with patch("sys.argv", ["cli.py", "tasks", "--get", "nonexistent"]):
                code = main()
                self.assertEqual(code, 1)
        finally:
            backend_main.tasks = original_tasks

    @patch("cli._patch_broadcast")
    def test_delete_task(self, mock_patch):
        import main as backend_main

        original_tasks = backend_main.tasks.copy()
        backend_main.tasks["del-me"] = {"status": "completed"}
        try:
            with patch("sys.argv", ["cli.py", "tasks", "--delete", "del-me"]):
                with patch("cli._output_result") as mock_output:
                    code = main()
                    self.assertEqual(code, 0)
                    call_args = mock_output.call_args[0][0]
                    self.assertEqual(call_args["status"], "deleted")
        finally:
            backend_main.tasks = original_tasks


class TestOutputResult(unittest.TestCase):
    def test_json_to_stdout(self):
        data = {"status": "completed", "transcript": "hello"}
        with patch("builtins.print") as mock_print:
            code = cli._output_result(data)
            self.assertEqual(code, 0)
            output = mock_print.call_args[0][0]
            parsed = json.loads(output)
            self.assertEqual(parsed["status"], "completed")

    def test_pretty_output(self):
        data = {"video_title": "Test", "transcript": "Hello world"}
        with patch("builtins.print") as mock_print:
            code = cli._output_result(data, pretty=True)
            self.assertEqual(code, 0)

    def test_write_to_file(self):
        import tempfile

        data = {"transcript": "Hello world"}
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = os.path.join(tmpdir, "out.md")
            code = cli._output_result(data, output_path=outpath, fmt="markdown")
            self.assertEqual(code, 0)
            content = Path(outpath).read_text(encoding="utf-8")
            self.assertIn("Hello world", content)


class TestLoadEnv(unittest.TestCase):
    def test_load_env_skips_missing(self):
        original = os.environ.copy()
        cli._load_env()
        self.assertEqual(os.environ, original)

    def test_load_env_reads_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("TEST_CLI_VAR=hello\n# comment\n\nOTHER_VAR=world\n")
            with patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
                os.environ.pop("TEST_CLI_VAR", None)
                os.environ.pop("OTHER_VAR", None)
                cli._load_env()
                self.assertEqual(os.environ.get("TEST_CLI_VAR"), "hello")
                self.assertEqual(os.environ.get("OTHER_VAR"), "world")
            os.environ.pop("TEST_CLI_VAR", None)
            os.environ.pop("OTHER_VAR", None)

    def test_load_env_does_not_override_existing(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("EXISTING_VAR=new_value\n")
            os.environ["EXISTING_VAR"] = "original"
            with patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
                cli._load_env()
                self.assertEqual(os.environ["EXISTING_VAR"], "original")
            del os.environ["EXISTING_VAR"]


class TestResolveApiKey(unittest.TestCase):
    def test_flag_takes_precedence(self):
        os.environ["TEST_KEY"] = "env_value"
        result = cli._resolve_api_key("flag_value", "TEST_KEY")
        self.assertEqual(result, "flag_value")
        del os.environ["TEST_KEY"]

    def test_env_fallback(self):
        os.environ["TEST_KEY"] = "env_value"
        result = cli._resolve_api_key("", "TEST_KEY")
        self.assertEqual(result, "env_value")
        del os.environ["TEST_KEY"]

    def test_empty_when_both_missing(self):
        result = cli._resolve_api_key("", "NONEXISTENT_KEY_12345")
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()

"""Tests for the AI Video Transcriber CLI."""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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
        for key in ("name", "version", "description", "guide", "commands", "exit_codes", "env_vars", "settings_file"):
            self.assertIn(key, AGENT_MANIFEST)

    def test_manifest_commands(self):
        commands = AGENT_MANIFEST["commands"]
        for name in ("transcribe", "summarize", "pipeline", "tasks", "settings"):
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

    def test_transcribe_local_api_args(self):
        parser = build_parser()
        args = parser.parse_args([
            "transcribe", "--url", "http://x", "--provider", "local_api",
            "--local-api-base-url", "http://localhost:8000",
            "--local-api-key", "test-key",
            "--local-api-model", "whisper-large",
            "--local-api-language", "en",
            "--local-api-prompt", "test prompt",
        ])
        self.assertEqual(args.local_api_base_url, "http://localhost:8000")
        self.assertEqual(args.local_api_key, "test-key")
        self.assertEqual(args.local_api_model, "whisper-large")
        self.assertEqual(args.local_api_language, "en")
        self.assertEqual(args.local_api_prompt, "test prompt")

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
        args = parser.parse_args(["pipeline", "--url", "http://x"])
        self.assertEqual(args.command, "pipeline")
        self.assertEqual(args.url, "http://x")
        # pipeline does not have --task-id / --transcript-file flags
        self.assertFalse(hasattr(args, "task_id"))
        self.assertFalse(hasattr(args, "transcript_file"))

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
    def test_missing_url_and_file_exits_2(self):
        """Without --url or --file, argparse still parses (defaults are ""),
        but _run_transcribe returns exit_code 2 with a clear message."""
        with patch("sys.argv", ["cli.py", "transcribe"]):
            with patch("builtins.print") as mock_print:
                code = main()
                self.assertEqual(code, 2)
                # Verify the error JSON was printed to stdout
                output = mock_print.call_args[0][0]
                result = json.loads(output)
                self.assertIn("Either --url or --file is required", result["error"])

    @patch("cli._run_transcribe")
    @patch("cli._output_result")
    def test_successful_transcribe(self, mock_output, mock_run_transcribe):
        mock_run_transcribe.return_value = {
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
    def test_missing_task_id_and_file_exits_2(self):
        """Without --task-id or --transcript-file, _run_summarize returns
        exit_code 2 with a clear error message."""
        with patch("sys.argv", ["cli.py", "summarize"]):
            with patch("builtins.print") as mock_print:
                code = main()
                self.assertEqual(code, 2)
                output = mock_print.call_args[0][0]
                result = json.loads(output)
                self.assertIn("Either --task-id or --transcript-file is required", result["error"])


class TestTasksCommand(unittest.TestCase):
    def test_no_flag_returns_error(self):
        with patch("sys.argv", ["cli.py", "tasks"]):
            with patch("builtins.print") as mock_print:
                code = main()
                self.assertEqual(code, 2)

    def test_list_tasks_includes_ids(self):
        import main as backend_main

        original_tasks = backend_main.tasks.copy()
        backend_main.tasks = {
            "test-id-1": {"status": "completed", "video_title": "Test 1"},
            "test-id-2": {"status": "completed", "video_title": "Test 2"},
        }
        try:
            with patch("sys.argv", ["cli.py", "tasks", "--list"]):
                with patch("cli._output_result") as mock_output:
                    code = main()
                    self.assertEqual(code, 0)
                    call_args = mock_output.call_args[0][0]
                    self.assertIn("tasks", call_args)
                    tasks_list = call_args["tasks"]
                    self.assertEqual(len(tasks_list), 2)
                    for task in tasks_list:
                        self.assertIn("task_id", task)
        finally:
            backend_main.tasks = original_tasks

    def test_get_nonexistent_task(self):
        import main as backend_main

        original_tasks = backend_main.tasks.copy()
        backend_main.tasks = {}
        try:
            with patch("sys.argv", ["cli.py", "tasks", "--get", "nonexistent"]):
                code = main()
                self.assertEqual(code, 1)
        finally:
            backend_main.tasks = original_tasks

    def test_delete_task(self):
        import main as backend_main

        original_tasks = backend_main.tasks.copy()
        backend_main.tasks = {"del-me": {"status": "completed"}}
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


class TestQuietMode(unittest.TestCase):
    def test_quiet_mode_suppresses_progress(self):
        """Verify _print_progress is a no-op when _quiet_mode is True."""
        original = cli._quiet_mode
        try:
            cli._quiet_mode = True
            with patch("builtins.print") as mock_print:
                cli._print_progress("test-id", {"progress": 50, "message": "Working..."})
                mock_print.assert_not_called()
        finally:
            cli._quiet_mode = original

    def test_progress_prints_when_not_quiet(self):
        original = cli._quiet_mode
        try:
            cli._quiet_mode = False
            with patch("builtins.print") as mock_print:
                cli._print_progress("test-id", {"progress": 50, "message": "Working..."})
                mock_print.assert_called_once()
                self.assertIn("50%", mock_print.call_args[0][0])
                self.assertIn("Working...", mock_print.call_args[0][0])
        finally:
            cli._quiet_mode = original


class TestSettingsSubcommand(unittest.TestCase):
    def test_settings_show_parses(self):
        parser = build_parser()
        args = parser.parse_args(["settings", "--show"])
        self.assertTrue(args.show)
        self.assertEqual(args.command, "settings")

    def test_settings_set_parses(self):
        parser = build_parser()
        args = parser.parse_args(["settings", "--set", "groq_model=test-model"])
        self.assertEqual(args.set_value, "groq_model=test-model")

    def test_settings_set_groq_key_parses(self):
        parser = build_parser()
        args = parser.parse_args(["settings", "--set-groq-key"])
        self.assertTrue(args.set_groq_key)

    def test_settings_set_openai_key_parses(self):
        parser = build_parser()
        args = parser.parse_args(["settings", "--set-openai-key"])
        self.assertTrue(args.set_openai_key)

    def test_settings_show_returns_masked(self):
        import tempfile
        import settings as settings_module
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = Path(tmpdir) / "settings.json"
            sf.write_text('{"groq_api_key": "gsk_test_long_key_12345"}')
            with patch.object(settings_module, "SETTINGS_FILE", sf):
                with patch("sys.argv", ["cli.py", "settings", "--show"]):
                    with patch("cli._output_result") as mock_output:
                        code = main()
                        self.assertEqual(code, 0)
                        call_args = mock_output.call_args[0][0]
                        self.assertIn("...", call_args["groq_api_key"])
                        self.assertNotEqual(call_args["groq_api_key"], "gsk_test_long_key_12345")

    def test_settings_set_writes_value(self):
        import tempfile
        import settings as settings_module
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = Path(tmpdir) / "settings.json"
            sf.write_text('{}')
            with patch.object(settings_module, "SETTINGS_FILE", sf):
                with patch("sys.argv", ["cli.py", "settings", "--set", "groq_model=whisper-large-v3"]):
                    with patch("cli._output_result") as mock_output:
                        code = main()
                        self.assertEqual(code, 0)
                        saved = json.loads(sf.read_text())
                        self.assertEqual(saved["groq_model"], "whisper-large-v3")

    def test_settings_set_invalid_format(self):
        with patch("sys.argv", ["cli.py", "settings", "--set", "no_equals_sign"]):
            with patch("builtins.print") as mock_print:
                code = main()
                self.assertEqual(code, 2)
                output = mock_print.call_args[0][0]
                result = json.loads(output)
                self.assertIn("key=value", result["error"])

    def test_settings_set_unknown_key(self):
        with patch("sys.argv", ["cli.py", "settings", "--set", "nonexistent_key=value"]):
            with patch("builtins.print") as mock_print:
                code = main()
                self.assertEqual(code, 2)
                output = mock_print.call_args[0][0]
                result = json.loads(output)
                self.assertIn("Unknown setting", result["error"])


class TestMissingCredentials(unittest.TestCase):
    def test_transcribe_missing_groq_key_error(self):
        """When provider is groq and no key is set, exit with helpful error."""
        with patch("settings.get_credential", return_value=""):
            with patch("cli._load_env"):
                with patch("sys.argv", ["cli.py", "transcribe", "--url", "http://x", "--provider", "groq"]):
                    with patch("builtins.print") as mock_print:
                        code = main()
                        self.assertEqual(code, 1)
                        output = mock_print.call_args[0][0]
                        result = json.loads(output)
                        self.assertIn("GROQ_API_KEY", result["error"])
                        self.assertIn("settings --set-groq-key", result["error"])

    def test_summarize_missing_openai_key_error(self):
        """When no OpenAI key is set, exit with helpful error."""
        import tempfile
        with patch("settings.get_credential", return_value=""):
            with patch("cli._load_env"):
                tf = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
                tf.write("# Test transcript")
                tf.close()
                try:
                    with patch("sys.argv", ["cli.py", "summarize", "--transcript-file", tf.name]):
                        with patch("builtins.print") as mock_print:
                            code = main()
                            self.assertEqual(code, 1)
                            output = mock_print.call_args[0][0]
                            result = json.loads(output)
                            self.assertIn("OPENAI_API_KEY", result["error"])
                            self.assertIn("settings --set-openai-key", result["error"])
                finally:
                    os.unlink(tf.name)


if __name__ == "__main__":
    unittest.main()

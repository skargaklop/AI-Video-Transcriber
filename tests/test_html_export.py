import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from html_export import markdown_to_html, render_summary_html  # noqa: E402


class HtmlExportTests(unittest.TestCase):
    def test_markdown_to_html_handles_headings_and_lists(self):
        html = markdown_to_html("# Summary\n\n- Tip one\n- Tip two")

        self.assertIn("<h1>Summary</h1>", html)
        self.assertIn("<li>Tip one</li>", html)
        self.assertIn("<li>Tip two</li>", html)

    def test_render_summary_html_is_standalone(self):
        html = render_summary_html(
            title="Video title",
            summary_markdown="# Summary\n\nUseful text",
            source_url="https://youtube.com/watch?v=abc",
        )

        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<title>Video title</title>", html)
        self.assertIn("https://youtube.com/watch?v=abc", html)
        self.assertIn("<main", html)


if __name__ == "__main__":
    unittest.main()

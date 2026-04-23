import importlib
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))


class BackendImportTests(unittest.TestCase):
    def test_main_imports_without_local_whisper_dependency(self):
        main = importlib.import_module("main")

        self.assertTrue(hasattr(main, "app"))
        self.assertEqual(main.app.title, "AI视频转录器")


if __name__ == "__main__":
    unittest.main()

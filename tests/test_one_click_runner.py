from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER = PROJECT_ROOT / "一键转换.command"


class OneClickRunnerTests(unittest.TestCase):
    def test_successful_converter_exits_without_zsh_reserved_variable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fake_python = Path(temporary_directory) / "python3"
            fake_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_python.chmod(0o755)

            environment = os.environ.copy()
            environment["PATH"] = (
                f"{temporary_directory}{os.pathsep}{environment['PATH']}"
            )
            result = subprocess.run(
                ["zsh", str(RUNNER)],
                cwd="/tmp",
                env=environment,
                input="\n",
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )

        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn("read-only variable", output)
        self.assertIn("转换完成，结果已写入 output 文件夹。", result.stdout)


if __name__ == "__main__":
    unittest.main()

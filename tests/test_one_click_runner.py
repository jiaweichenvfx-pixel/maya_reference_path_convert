from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCAN_RUNNER = PROJECT_ROOT / "一键更新查找表.command"
REWRITE_RUNNER = PROJECT_ROOT / "一键更新ma文件路径.command"


class OneClickRunnerTests(unittest.TestCase):
    def run_runner_with_fake_python(
        self,
        runner: Path,
    ) -> tuple[subprocess.CompletedProcess[str], str]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            argv_log = Path(temporary_directory) / "argv.log"
            fake_python = Path(temporary_directory) / "python3"
            fake_python.write_text(
                f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {argv_log}\nexit 0\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)

            environment = os.environ.copy()
            environment["PATH"] = (
                f"{temporary_directory}{os.pathsep}{environment['PATH']}"
            )
            result = subprocess.run(
                ["zsh", str(runner)],
                cwd="/tmp",
                env=environment,
                input="\n",
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            argv = argv_log.read_text(encoding="utf-8")

        return result, argv

    def test_scan_runner_invokes_scan_server(self) -> None:
        result, argv = self.run_runner_with_fake_python(SCAN_RUNNER)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn("read-only variable", output)
        self.assertIn("查找表更新完成，结果已写入 data 文件夹。", result.stdout)
        self.assertIn("maya_path_rewriter.py\nscan-server\n", argv)

    def test_rewrite_runner_invokes_batch(self) -> None:
        result, argv = self.run_runner_with_fake_python(REWRITE_RUNNER)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn("read-only variable", output)
        self.assertIn("ma 文件路径更新完成，结果已写入 output 文件夹。", result.stdout)
        self.assertIn("maya_path_rewriter.py\nbatch\n", argv)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "python_script" / "maya_path_rewriter.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "maya_path_rewriter_loading_tests",
    MODULE_PATH,
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"无法加载测试模块: {MODULE_PATH}")

maya_path_rewriter = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = maya_path_rewriter
MODULE_SPEC.loader.exec_module(maya_path_rewriter)


def lookup_table(filename: str, windows_path: str) -> dict[str, object]:
    return {
        "files": [
            {
                "name": filename,
                "name_key": filename.casefold(),
                "windows_path": windows_path,
            }
        ]
    }


class MayaLoadingMetadataTests(unittest.TestCase):
    def test_defer_value_is_synchronized_for_r_and_rdi(self) -> None:
        source = (
            'file -rdi 2 -ns "asset" -dr 1 -rfn "assetRN" '
            '-typ "mayaAscii" "J:/old/Asset.ma";\n'
            'file -r -ns "asset" -dr 1 -rfn "assetRN" '
            '-typ "mayaAscii" "J:/old/Asset.ma";\n'
        )

        rewritten, report = maya_path_rewriter.rewrite_maya_text(
            source,
            lookup_table("Asset.ma", "P:/assets/Asset.ma"),
            defer_reference_value=0,
        )

        self.assertNotIn("-dr 1", rewritten)
        self.assertEqual(rewritten.count("-dr 0"), 2)
        self.assertIn("file -rdi 2", rewritten)
        self.assertEqual(report["defer_changed"], 2)

    def test_mb_fallback_updates_explicit_maya_file_type(self) -> None:
        source = (
            'file -rdi 1 -ns "asset" -dr 0 -rfn "assetRN" '
            '-typ "mayaAscii" "J:/old/Asset.ma";\n'
            'file -r -ns "asset" -dr 0 -rfn "assetRN" '
            '-typ "mayaAscii" "J:/old/Asset.ma";\n'
        )

        rewritten, report = maya_path_rewriter.rewrite_maya_text(
            source,
            lookup_table("Asset.mb", "P:/assets/Asset.mb"),
            defer_reference_value=0,
        )

        self.assertNotIn('mayaAscii" "P:/assets/Asset.mb', rewritten)
        self.assertEqual(rewritten.count('-typ "mayaBinary"'), 2)
        self.assertEqual(report["extension_fallback"], 2)
        self.assertEqual(report["file_type_changed"], 2)


if __name__ == "__main__":
    unittest.main()

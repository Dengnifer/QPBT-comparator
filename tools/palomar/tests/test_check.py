import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("palomar_check", ROOT / "tools/palomar/check.py")
CHECK = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = CHECK
SPEC.loader.exec_module(CHECK)


class PalomarCheckTests(unittest.TestCase):
    def test_module_header_matches_palomar_boundaries(self):
        cases = {
            "module\n": True,
            "-- ordinary comment\n/- nested /- comment -/ ok -/\nmodule\n": True,
            "/-! module documentation -/\nmodule\n": False,
            "/-- declaration documentation -/\nmodule\n": False,
            "moduleName\n": False,
            "import Mathlib\nmodule\n": False,
            "/- unterminated\nmodule\n": False,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(CHECK.has_module_header(text), expected)

    def test_physical_lines_matches_policy(self):
        self.assertEqual(CHECK.physical_lines(""), 0)
        self.assertEqual(CHECK.physical_lines("module"), 1)
        self.assertEqual(CHECK.physical_lines("module\n"), 1)
        self.assertEqual(CHECK.physical_lines("module\r\n-- x\r\n"), 2)
        self.assertEqual(CHECK.physical_lines("module\n-- x"), 2)

    def test_split_challenge_is_local_and_untrusted(self):
        challenge = "module\nimport Mathlib\nimport Challenge.Helper\n"
        helper = "module\nimport Mathlib\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Challenge").mkdir()
            (root / "Challenge.lean").write_text(challenge)
            (root / "Challenge/Helper.lean").write_text(helper)
            local_modules = {
                path.relative_to(root).with_suffix("").as_posix().replace("/", "."): path
                for path in root.rglob("*.lean")
            }
            self.assertIn("Challenge.Helper", CHECK.parse_imports(challenge))
            self.assertIn("Challenge.Helper", local_modules)
            self.assertNotIn("Challenge.Helper".split(".", 1)[0], {"Mathlib", "Lean", "Init"})

    def test_schema_accepts_draft_and_rejects_missing_author(self):
        schema = CHECK.load_json(ROOT / "tools/palomar/upstream/formalization-v0.4.schema.json")
        metadata = CHECK.load_yaml(ROOT / "formalization.yaml")
        validator = CHECK.jsonschema.Draft7Validator(schema)
        self.assertEqual(list(validator.iter_errors(metadata)), [])
        metadata["project"]["authors"] = []
        self.assertTrue(list(validator.iter_errors(metadata)))

    def test_input_manifest_excludes_report_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "A.lean").write_text("module\n")
            (root / "reports").mkdir()
            report = root / "reports/palomar-mechanical.json"
            report.write_text("first")
            first = CHECK.input_manifest(root, {"reports/palomar-mechanical.json"})
            report.write_text("second")
            second = CHECK.input_manifest(root, {"reports/palomar-mechanical.json"})
            self.assertEqual(first, second)
            self.assertEqual([item["path"] for item in first["files"]], ["A.lean"])

    def test_current_checker_config_is_json(self):
        config = json.loads((ROOT / "palomar-check.json").read_text())
        self.assertEqual(config["schema_version"], 1)
        self.assertEqual(config["canonical_substantive_repository"], "Dengnifer/MIPStarRE-QPBT")

    def test_authoritative_report_requires_exact_head_and_kernels(self):
        config = json.loads((ROOT / "palomar-check.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "fixture"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "fixture@example.test"], check=True)
            (root / "README").write_text("fixture\n")
            subprocess.run(["git", "-C", str(root), "add", "README"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "fixture"], check=True)
            head = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            official = {
                "status": "pass",
                "stage": "complete",
                "phase": "verification",
                "source": {"repository": config["wrapper_repository"], "commit": head},
                "comparator": {
                    "theorem_names": config["expected_theorems"],
                    "permitted_axioms": ["Classical.choice", "Quot.sound", "propext"],
                    "external_kernels": {"nanoda": ["/nanoda"], "con-ron": ["/con-ron"]},
                },
            }
            path = Path(directory) / "official.json"
            path.write_text(json.dumps(official))
            accepted = CHECK.authoritative_report_check(
                root, path, config, {"Classical.choice", "Quot.sound", "propext"}
            )
            self.assertEqual(accepted.status, "pass")
            official["source"]["commit"] = "0" * 40
            path.write_text(json.dumps(official))
            rejected = CHECK.authoritative_report_check(
                root, path, config, {"Classical.choice", "Quot.sound", "propext"}
            )
            self.assertEqual(rejected.status, "fail")


if __name__ == "__main__":
    unittest.main()

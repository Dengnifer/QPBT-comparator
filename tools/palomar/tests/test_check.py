import copy
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
    def git(self, root: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def init_repo(self, root: Path) -> None:
        subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
        self.git(root, "config", "user.name", "fixture")
        self.git(root, "config", "user.email", "fixture@example.test")

    def commit_all(self, root: Path, message: str = "fixture") -> str:
        self.git(root, "add", ".")
        self.git(root, "commit", "-q", "-m", message)
        return self.git(root, "rev-parse", "HEAD")

    def report_fixture(self, directory: str) -> tuple[Path, Path, dict, dict]:
        config = CHECK.load_json(ROOT / "palomar-check.json")
        root = Path(directory) / "repo"
        root.mkdir()
        self.init_repo(root)
        comparator = {
            "challenge_module": "Challenge",
            "solution_module": "Solution",
            "theorem_names": list(config["expected_theorems"]),
            "definition_names": list(config["expected_definitions"]),
            "permitted_axioms": ["Classical.choice", "Quot.sound", "propext"],
            "enable_nanoda": True,
        }
        files = {
            "formalization.yaml": "version: v0.4\n",
            "comparator.json": json.dumps(comparator, indent=2) + "\n",
            "lakefile.toml": 'name = "Fixture"\n',
            "lake-manifest.json": '{"version":"1.2.0","packages":[]}\n',
            "lean-toolchain": "leanprover/lean4:v4.35.0-rc2\n",
            "Challenge.lean": "module\nimport Mathlib\n",
            "Solution.lean": "module\nimport Mathlib\n",
        }
        for name, text in files.items():
            (root / name).write_text(text, encoding="utf-8")
        head = self.commit_all(root)

        kernel_map = {
            "nanoda": ["/opt/lean/bin/nanoda"],
            "con-ron": ["/opt/lean/bin/con-ron"],
        }
        protected = {
            "challenge_module": "PalomarCanonical0123456789abcdef01234567.Challenge",
            "solution_module": "Solution",
            "theorem_names": list(config["expected_theorems"]),
            "definition_names": list(config["expected_definitions"]),
            "permitted_axioms": ["Classical.choice", "Quot.sound", "propext"],
            "external_kernels": kernel_map,
        }
        protected_text = json.dumps(protected, indent=2) + "\n"
        report = {
            "schema_version": 2,
            "status": "pass",
            "stage": "complete",
            "phase": "verification",
            "errors": [],
            "workflow_url": "https://github.com/PalomarRegistry/PalomarSubmission/actions/runs/1",
            "submission": {
                "requested_paths": {
                    "project_path": "",
                    "comparator_config_path": "comparator.json",
                    "formalization_metadata_path": "",
                }
            },
            "source": {
                "repository": config["wrapper_repository"],
                "repository_url": f"https://github.com/{config['wrapper_repository']}",
                "commit": head,
            },
            "formalization": {
                "path": "formalization.yaml",
                "sha256": CHECK.sha256_file(root / "formalization.yaml"),
            },
            "lakefile": {
                "path": "lakefile.toml",
                "sha256": CHECK.sha256_file(root / "lakefile.toml"),
            },
            "lake_manifest": {
                "path": "lake-manifest.json",
                "sha256": CHECK.sha256_file(root / "lake-manifest.json"),
            },
            "lean_toolchain_path": "lean-toolchain",
            "comparator": {
                "path": "comparator.json",
                "sha256": CHECK.sha256_file(root / "comparator.json"),
                "challenge_module": "Challenge",
                "solution_module": "Solution",
                "theorem_names": list(config["expected_theorems"]),
                "definition_names": list(config["expected_definitions"]),
                "permitted_axioms": ["Classical.choice", "Quot.sound", "propext"],
            },
            "challenge": {
                "module": "Challenge",
                "path": "Challenge.lean",
                "sha256": CHECK.sha256_file(root / "Challenge.lean"),
                "direct_imports": ["Mathlib"],
                "transitive_source_count": 1,
                "dependencies": [
                    {
                        "repository": "leanprover-community/mathlib4",
                        "provenance": "allowlisted",
                    }
                ],
                "trust_level": "high",
                "untrusted_sources": [],
            },
            "solution": {
                "module": "Solution",
                "path": "Solution.lean",
                "sha256": CHECK.sha256_file(root / "Solution.lean"),
            },
            "kernels": [
                {"name": name, "argv": argv} for name, argv in kernel_map.items()
            ],
            "protected_config": protected_text,
            "protected_config_sha256": CHECK.sha256_bytes(protected_text.encode("utf-8")),
        }
        report_path = Path(directory) / "official.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return root, report_path, config, report

    def report_statuses(
        self, root: Path, path: Path, config: dict
    ) -> dict[str, CHECK.Check]:
        checks = CHECK.official_report_checks(
            root, path, config, {"Classical.choice", "Quot.sound", "propext"}
        )
        return {check.id: check for check in checks}

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

    def test_run_checks_separates_lexical_diagnostics_from_requirements(self):
        config = CHECK.load_json(ROOT / "palomar-check.json")
        report = CHECK.run_checks(ROOT, config, None)
        check_ids = {item["id"] for item in report["checks"]}
        diagnostics = {item["id"]: item for item in report["diagnostics"]}
        self.assertNotIn("proof.lexical_source_scan", check_ids)
        self.assertEqual(diagnostics["proof.lexical_source_scan"]["status"], "unknown")
        self.assertEqual(diagnostics["proof.lexical_source_scan"]["evidence"], "diagnostic")

    def test_current_profile_and_metadata_use_compact_declarations(self):
        config = CHECK.load_json(ROOT / "palomar-check.json")
        metadata = CHECK.load_yaml(ROOT / "formalization.yaml")
        self.assertEqual(config["schema_version"], 1)
        self.assertEqual(config["canonical_substantive_repository"], "Dengnifer/MIPStarRE-QPBT")
        self.assertEqual(config["expected_definitions"], ["MIPStarRE.QPBT.fixedFieldModel"])
        main_results = metadata["status"]["main_results"]
        self.assertTrue(
            CHECK.exact_declaration_list(
                [item["declaration"] for item in main_results], config["expected_theorems"]
            )
        )
        self.assertTrue(
            CHECK.exact_declaration_list(
                metadata["status"]["declarations"], config["expected_theorems"]
            )
        )

    def test_declaration_lists_reject_wrong_missing_extra_and_duplicate_names(self):
        config = CHECK.load_json(ROOT / "palomar-check.json")
        for expected in (config["expected_theorems"], config["expected_definitions"]):
            cases = {
                "valid": (list(expected), True),
                "wrong": ([*expected[:-1], "Wrong.Namespace.target"], False),
                "missing": (list(expected[:-1]), False),
                "extra": ([*expected, "Extra.Namespace.target"], False),
                "duplicate": ([*expected, expected[0]], False),
                "malformed": ([*expected[:-1], "bad-name"], False),
            }
            for name, (actual, accepted) in cases.items():
                with self.subTest(contract=expected, case=name):
                    self.assertEqual(CHECK.exact_declaration_list(actual, expected), accepted)

    def test_json_loader_rejects_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"a": 1, "a": 2}\n')
            with self.assertRaisesRegex(ValueError, "duplicate JSON keys"):
                CHECK.load_json(path)

    def test_configuration_byte_limit_and_compiled_artifact_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comparator.json"
            path.write_bytes(b"x" * 16)
            self.assertEqual(CHECK.regular_file_within_limit(path, 16), (True, 16))
            path.write_bytes(b"x" * 17)
            self.assertEqual(CHECK.regular_file_within_limit(path, 16), (False, 17))
        self.assertFalse(CHECK.is_compiled_artifact(Path("harmless.c")))
        self.assertTrue(CHECK.is_compiled_artifact(Path("build.a")))
        self.assertTrue(CHECK.is_compiled_artifact(Path("Module.olean.private")))

    def test_git_lfs_check_uses_cached_attributes_not_file_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            self.init_repo(root)
            (root / ".gitattributes").write_text("*.bin filter=lfs\n")
            (root / "payload.bin").write_text("ordinary contents\n")
            (root / "pointer.txt").write_text(
                "version https://git-lfs.github.com/spec/v1\n"
            )
            self.git(root, "add", ".")
            self.assertEqual(CHECK.tracked_lfs_paths(root), ["payload.bin"])

    def test_substantive_pin_requires_canonical_observed_main(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            self.init_repo(root)
            (root / "base").write_text("base\n")
            base = self.commit_all(root, "base")
            self.git(
                root,
                "remote",
                "add",
                "canonical",
                "https://github.com/Dengnifer/MIPStarRE-QPBT.git",
            )
            self.git(root, "update-ref", "refs/remotes/canonical/main", base)
            accepted = CHECK.substantive_main_pin_check(
                root, base, "Dengnifer/MIPStarRE-QPBT"
            )
            self.assertEqual(accepted.status, "pass")

            self.git(root, "checkout", "-q", "-b", "side")
            (root / "side").write_text("side\n")
            side = self.commit_all(root, "side")
            self.git(root, "checkout", "-q", "main")
            (root / "main").write_text("main\n")
            main = self.commit_all(root, "main")
            self.git(root, "update-ref", "refs/remotes/canonical/main", main)
            rejected = CHECK.substantive_main_pin_check(
                root, side, "Dengnifer/MIPStarRE-QPBT"
            )
            self.assertEqual(rejected.status, "fail")

            self.git(root, "remote", "remove", "canonical")
            unknown = CHECK.substantive_main_pin_check(
                root, base, "Dengnifer/MIPStarRE-QPBT"
            )
            self.assertEqual(unknown.status, "unknown")

    def test_substantive_size_uses_pinned_regular_tree_not_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            self.init_repo(root)
            (root / "first.bin").write_bytes(b"1234")
            (root / "second.bin").write_bytes(b"1234")
            (root / "link").symlink_to("first.bin")
            revision = self.commit_all(root)

            (root / "first.bin").write_bytes(b"x" * 100)
            (root / ".lake").mkdir()
            (root / ".lake/untracked.bin").write_bytes(b"x" * 1000)
            evidence = CHECK.inspect_substantive(root, revision, 10_000, {"lakefile.lean"})

            self.assertEqual(evidence["source_bytes"], 8)
            self.assertEqual(evidence["regular_files"], 2)
            self.assertEqual(evidence["symlinks"], ["link"])
            self.assertEqual(CHECK.substantive_source_cap_check(evidence, 8).status, "pass")
            rejected = CHECK.substantive_source_cap_check(evidence, 7)
            self.assertEqual(rejected.status, "fail")
            self.assertEqual(rejected.details["revision"], revision)
            self.assertEqual(rejected.details["bytes"], 8)

    def test_substantive_preservation_uses_pinned_lfs_and_gitlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            self.init_repo(root)
            (root / ".gitattributes").write_text("*.bin filter=lfs\n")
            (root / "payload.bin").write_text("ordinary contents\n")
            (root / "Alias.lean").symlink_to("payload.bin")
            base = self.commit_all(root, "base")
            self.git(root, "update-index", "--add", "--cacheinfo", f"160000,{base},vendor/source")
            self.git(root, "commit", "-q", "-m", "gitlink")
            revision = self.git(root, "rev-parse", "HEAD")

            (root / ".gitattributes").write_text("*.bin -filter\n")
            evidence = CHECK.inspect_substantive(root, revision, 10_000, {"lakefile.lean"})
            self.assertEqual(evidence["tracked_lfs_paths"], ["payload.bin"])
            self.assertEqual(evidence["submodules"], ["vendor/source"])
            self.assertEqual(evidence["lean_symlinks"], ["Alias.lean"])

    def test_real_shaped_report_content_is_not_labeled_authenticated(self):
        with tempfile.TemporaryDirectory() as directory:
            root, path, config, _ = self.report_fixture(directory)
            checks = self.report_statuses(root, path, config)
            self.assertEqual({item.status for item in checks.values()}, {"pass"})
            self.assertEqual(
                {item.evidence for item in checks.values()}, {"report-content"}
            )
            self.assertIn("content only", checks["proof.report_content"].details["note"])

    def test_requirement_aggregation_preserves_runtime_and_static_gates(self):
        expected_axioms = {"Classical.choice", "Quot.sound", "propext"}
        diagnostic = CHECK.Check(
            "proof.lexical_source_scan",
            "unknown",
            "diagnostic",
            "non-certifying fixture observation",
        )
        with tempfile.TemporaryDirectory() as directory:
            root, path, config, report = self.report_fixture(directory)
            complete = CHECK.official_report_checks(
                root, path, config, expected_axioms
            )
            self.assertEqual(CHECK.aggregate_requirement_status(complete), "pass")
            self.assertEqual(diagnostic.status, "unknown")

            missing = CHECK.official_report_checks(
                root, None, config, expected_axioms
            )
            self.assertEqual(CHECK.aggregate_requirement_status(missing), "unknown")

            report["status"] = "fail"
            path.write_text(json.dumps(report), encoding="utf-8")
            failed = CHECK.official_report_checks(
                root, path, config, expected_axioms
            )
            self.assertEqual(CHECK.aggregate_requirement_status(failed), "fail")

            source_failure = CHECK.Check(
                "source.fixture", "fail", "static", "source requirement failed"
            )
            self.assertEqual(
                CHECK.aggregate_requirement_status([*complete, source_failure]),
                "fail",
            )

    def test_report_metadata_request_default_explicit_and_selected_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root, path, config, report = self.report_fixture(directory)
            self.assertEqual(
                self.report_statuses(root, path, config)["proof.report_content"].status,
                "pass",
            )

            explicit = copy.deepcopy(report)
            explicit["submission"]["requested_paths"][
                "formalization_metadata_path"
            ] = "formalization.yaml"
            path.write_text(json.dumps(explicit), encoding="utf-8")
            self.assertEqual(
                self.report_statuses(root, path, config)["proof.report_content"].status,
                "pass",
            )

            variants = {
                "wrong_explicit": lambda value: value["submission"]["requested_paths"].update(
                    formalization_metadata_path="metadata/formalization.yaml"
                ),
                "wrong_selected_path": lambda value: value["formalization"].update(
                    path="metadata/formalization.yaml"
                ),
                "wrong_selected_hash": lambda value: value["formalization"].update(
                    sha256="0" * 64
                ),
                "wrong_project": lambda value: value["submission"]["requested_paths"].update(
                    project_path="nested"
                ),
                "wrong_comparator": lambda value: value["submission"]["requested_paths"].update(
                    comparator_config_path="other.json"
                ),
            }
            for name, mutate in variants.items():
                candidate = copy.deepcopy(report)
                mutate(candidate)
                path.write_text(json.dumps(candidate), encoding="utf-8")
                with self.subTest(case=name):
                    self.assertEqual(
                        self.report_statuses(root, path, config)["proof.report_content"].status,
                        "fail",
                    )

    def test_report_content_rejects_wrong_head_and_declaration_variants(self):
        with tempfile.TemporaryDirectory() as directory:
            root, path, config, report = self.report_fixture(directory)
            variants = {
                "wrong_head": lambda value: value["source"].update(commit="0" * 40),
                "missing": lambda value: value["comparator"]["theorem_names"].pop(),
                "extra": lambda value: value["comparator"]["theorem_names"].append(
                    "Extra.Namespace.target"
                ),
                "duplicate": lambda value: value["comparator"]["theorem_names"].append(
                    config["expected_theorems"][0]
                ),
                "wrong_definition": lambda value: value["comparator"].update(
                    definition_names=["Wrong.Namespace.definition"]
                ),
            }
            for name, mutate in variants.items():
                candidate = copy.deepcopy(report)
                mutate(candidate)
                path.write_text(json.dumps(candidate), encoding="utf-8")
                with self.subTest(case=name):
                    self.assertEqual(
                        self.report_statuses(root, path, config)["proof.report_content"].status,
                        "fail",
                    )

    def test_report_content_rejects_malformed_protected_config_and_kernel_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root, path, config, report = self.report_fixture(directory)
            malformed = copy.deepcopy(report)
            malformed["protected_config"] = '{"bad":'
            malformed["protected_config_sha256"] = CHECK.sha256_bytes(
                malformed["protected_config"].encode("utf-8")
            )
            path.write_text(json.dumps(malformed), encoding="utf-8")
            result = self.report_statuses(root, path, config)["proof.report_content"]
            self.assertEqual(result.status, "fail")
            self.assertTrue(any("malformed" in error for error in result.details["errors"]))

            mismatch = copy.deepcopy(report)
            mismatch["kernels"][0]["argv"] = ["/different/nanoda"]
            path.write_text(json.dumps(mismatch), encoding="utf-8")
            result = self.report_statuses(root, path, config)["proof.report_content"]
            self.assertEqual(result.status, "fail")
            self.assertTrue(any("kernel commands differ" in error for error in result.details["errors"]))


if __name__ == "__main__":
    unittest.main()

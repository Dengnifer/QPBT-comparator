#!/usr/bin/env python3
"""Deterministic, non-executing Palomar preparation checks."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

try:
    import jsonschema
    import yaml
except ImportError as error:  # pragma: no cover - exercised by the entry point
    raise SystemExit(
        "tools/palomar/check.py requires the Python jsonschema and PyYAML packages"
    ) from error


FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
LICENSE_RE = re.compile(r"^(?:LICENSE|LICENCE|COPYING)(?:\..+)?$", re.IGNORECASE)
LFS_HEADER = b"version https://git-lfs.github.com/spec/v1"
COMMENT_MARKER = re.compile(r"/-|-/")
RUNTIME_PARTS = {".git", ".lake", "__pycache__"}
COMPILED_SUFFIXES = {".olean", ".ilean", ".c", ".o", ".so", ".dll", ".dylib"}

# Lean identifier boundaries used by PalomarSubmission's cheap module-header
# preflight. Lean itself remains the authoritative parser in the official run.
ID_LETTER_LIKE = (
    r"\u03b1-\u03ba\u03bc-\u03c9\u0391-\u039f\u03a1-\u03a2\u03a4-\u03a9"
    r"\u03ca-\u03fb\u1f00-\u1ffe\u2100-\u214f\U0001d49c-\U0001d59f"
    r"\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u017f"
)
ID_FIRST = rf"A-Za-z_{ID_LETTER_LIKE}"
ID_REST = rf"{ID_FIRST}0-9'!?\u2080-\u2089\u2090-\u209c\u1d62-\u1d6a\u2c7c"
IDENTIFIER_CONTINUATION = re.compile(rf"[{ID_REST}]|\.[{ID_FIRST}«]")


@dataclass
class Check:
    id: str
    status: str
    evidence: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False):
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    for token in yaml.scan(text):
        if isinstance(token, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken)):
            raise ValueError("YAML anchors and aliases are not accepted")
    value = yaml.load(text, Loader=UniqueKeyLoader)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return value


def physical_lines(text: str) -> int:
    return text.count("\n") + int(bool(text) and not text.endswith("\n"))


def has_module_header(text: str) -> bool:
    """Match Palomar's non-executing module-header preflight."""
    index = 0
    while index < len(text):
        if text[index] in " \r\n":
            index += 1
        elif text.startswith("--", index):
            end = text.find("\n", index + 2)
            index = len(text) if end < 0 else end + 1
        elif text.startswith("/-", index) and not text.startswith(("/--", "/-!"), index):
            index += 3
            depth = 1
            while depth:
                marker = COMMENT_MARKER.search(text, index)
                if marker is None:
                    break
                depth += 1 if marker.group() == "/-" else -1
                index = marker.end()
            if depth:
                return False
        else:
            return text.startswith("module", index) and (
                IDENTIFIER_CONTINUATION.match(text, index + 6) is None
            )
    return False


def run_git(root: Path, *args: str, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        input=input_bytes,
        capture_output=True,
        check=False,
    )


def repository_files(root: Path, excluded: set[str]) -> list[Path]:
    proc = run_git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if proc.returncode == 0:
        names = [name.decode("utf-8") for name in proc.stdout.split(b"\0") if name]
        return sorted(
            root / name for name in names
            if name not in excluded and not any(part in RUNTIME_PARTS for part in Path(name).parts)
        )

    files: list[Path] = []
    for directory, subdirectories, names in os.walk(root, followlinks=False):
        subdirectories[:] = sorted(name for name in subdirectories if name not in RUNTIME_PARTS)
        for name in sorted(names):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if relative not in excluded:
                files.append(path)
    return files


def input_manifest(root: Path, excluded: set[str]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    for path in repository_files(root, excluded):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            data = os.readlink(path).encode("utf-8")
            kind = "symlink"
        elif path.is_file():
            data = path.read_bytes()
            kind = "file"
        else:
            continue
        item_hash = sha256_bytes(data)
        entries.append({"path": relative, "kind": kind, "bytes": len(data), "sha256": item_hash})
        digest.update(relative.encode("utf-8") + b"\0" + item_hash.encode("ascii") + b"\0")
    return {"sha256": digest.hexdigest(), "files": entries}


def add(
    checks: list[Check], check_id: str, status: str, evidence: str,
    summary: str, **details: Any,
) -> None:
    checks.append(Check(check_id, status, evidence, summary, details))


def module_path(module_name: str) -> Path:
    return Path(*module_name.split(".")).with_suffix(".lean")


def parse_imports(text: str) -> list[str]:
    imports: list[str] = []
    block_depth = 0
    for raw_line in text.splitlines():
        line = raw_line
        cleaned: list[str] = []
        index = 0
        while index < len(line):
            if block_depth:
                if line.startswith("/-", index):
                    block_depth += 1
                    index += 2
                elif line.startswith("-/", index):
                    block_depth -= 1
                    index += 2
                else:
                    index += 1
            elif line.startswith("--", index):
                break
            elif line.startswith("/-", index):
                block_depth = 1
                index += 2
            else:
                cleaned.append(line[index])
                index += 1
        statement = "".join(cleaned).strip()
        match = re.match(r"^(?:(?:public|private)\s+)?import\s+(.+)$", statement)
        if match:
            imports.extend(part for part in match.group(1).split() if part)
    return imports


def normalize_repository_id(value: str) -> str:
    value = value.strip()
    if "://" in value:
        parsed = urlparse(value)
        value = parsed.path
    elif value.startswith("git@github.com:"):
        value = value.split(":", 1)[1]
    value = value.strip("/")
    return value[:-4] if value.endswith(".git") else value


def parse_version(value: str) -> tuple[int, int, int, int]:
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)(?:-rc(\d+))?", value)
    if not match:
        raise ValueError(f"unsupported Lean release tag: {value}")
    major, minor, patch, rc = match.groups()
    # Stable sorts after all release candidates at the same numeric version.
    release_rank = 1_000_000 if rc is None else int(rc)
    return int(major), int(minor), int(patch), release_rank


def inspect_source_map(
    files: dict[str, bytes], *, line_cap: int, module_exempt: set[str],
) -> dict[str, Any]:
    missing_module: list[str] = []
    too_long: list[dict[str, Any]] = []
    invalid_utf8: list[str] = []
    max_lines = 0
    lexical_escape_matches: list[dict[str, Any]] = []
    escape_re = re.compile(r"\b(?:sorry|admit|native_decide|unsafe|axiom)\b|@\[extern")

    digest = hashlib.sha256()
    for path, data in sorted(files.items()):
        item_hash = sha256_bytes(data)
        digest.update(path.encode("utf-8") + b"\0" + item_hash.encode("ascii") + b"\0")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            invalid_utf8.append(path)
            continue
        lines = physical_lines(text)
        max_lines = max(max_lines, lines)
        if lines > line_cap:
            too_long.append({"path": path, "lines": lines})
        if Path(path).name not in module_exempt and not has_module_header(text):
            missing_module.append(path)
        if len(lexical_escape_matches) < 50:
            for line_number, line in enumerate(text.splitlines(), 1):
                if escape_re.search(line):
                    lexical_escape_matches.append({"path": path, "line": line_number})
                    if len(lexical_escape_matches) >= 50:
                        break

    return {
        "files_checked": len(files),
        "content_sha256": digest.hexdigest(),
        "maximum_lines": max_lines,
        "missing_module_count": len(missing_module),
        "missing_module_examples": missing_module[:50],
        "too_long_count": len(too_long),
        "too_long_examples": too_long[:50],
        "invalid_utf8_count": len(invalid_utf8),
        "invalid_utf8_examples": invalid_utf8[:50],
        "lexical_escape_match_count_at_least": len(lexical_escape_matches),
        "lexical_escape_examples": lexical_escape_matches,
    }


def git_tree_entries(repo: Path, revision: str) -> list[tuple[str, str, str]]:
    proc = run_git(repo, "ls-tree", "-r", "-z", "--full-tree", revision)
    if proc.returncode != 0:
        raise ValueError(proc.stderr.decode("utf-8", "replace").strip())
    entries: list[tuple[str, str, str]] = []
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        metadata, path = raw.split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split()
        entries.append((mode, object_id, path.decode("utf-8")))
    return entries


def git_blob_map(repo: Path, entries: Iterable[tuple[str, str]]) -> dict[str, bytes]:
    requested = list(entries)
    unique_ids = list(dict.fromkeys(object_id for _, object_id in requested))
    proc = run_git(repo, "cat-file", "--batch", input_bytes=b"".join(
        object_id.encode("ascii") + b"\n" for object_id in unique_ids
    ))
    if proc.returncode != 0:
        raise ValueError(proc.stderr.decode("utf-8", "replace").strip())

    stream = io.BytesIO(proc.stdout)
    contents: dict[str, bytes] = {}
    for expected_id in unique_ids:
        header = stream.readline().decode("ascii").strip().split()
        if len(header) != 3 or header[1] != "blob":
            raise ValueError(f"unexpected git cat-file header for {expected_id}: {header}")
        size = int(header[2])
        contents[expected_id] = stream.read(size)
        if stream.read(1) != b"\n":
            raise ValueError("malformed git cat-file batch output")
    return {path: contents[object_id] for path, object_id in requested}


def inspect_substantive(repo: Path, revision: str, line_cap: int, module_exempt: set[str]) -> dict[str, Any]:
    commit = run_git(repo, "cat-file", "-e", f"{revision}^{{commit}}")
    if commit.returncode != 0:
        raise ValueError(f"revision {revision} is not present in {repo}")
    entries = git_tree_entries(repo, revision)
    symlinks = [path for mode, _, path in entries if mode == "120000"]
    submodules = [path for mode, _, path in entries if mode == "160000"]
    lean_entries = [(path, object_id) for mode, object_id, path in entries if path.endswith(".lean") and mode != "160000"]
    requested = list(lean_entries)
    for special in ("lean-toolchain", "lake-manifest.json", "lakefile.toml", "lakefile.lean", "LICENSE"):
        for mode, object_id, path in entries:
            if path == special and mode != "160000":
                requested.append((path, object_id))
                break
    blobs = git_blob_map(repo, requested)
    lean_files = {path: blobs[path] for path, _ in lean_entries if path in blobs}
    scan = inspect_source_map(lean_files, line_cap=line_cap, module_exempt=module_exempt)
    tree = run_git(repo, "rev-parse", f"{revision}^{{tree}}")
    scan.update(
        {
            "revision": revision,
            "tree": tree.stdout.decode("ascii").strip(),
            "symlinks": symlinks[:50],
            "submodules": submodules[:50],
            "special_files": {
                name: {"sha256": sha256_bytes(data), "bytes": len(data)}
                for name, data in blobs.items() if not name.endswith(".lean")
            },
            "_blobs": blobs,
        }
    )
    return scan


def authoritative_report_check(
    root: Path, report_path: Path | None, config: dict[str, Any],
    expected_axioms: set[str],
) -> Check:
    required_kernels = {"nanoda", "con-ron"}
    if report_path is None:
        return Check(
            "proof.authoritative_comparator", "unknown", "authoritative",
            "no official final-snapshot Palomar/comparator report is attached; proof, axiom, and independent-kernel claims are not certified here",
            {
                "required_targets": config["expected_theorems"],
                "required_axioms": sorted(expected_axioms),
                "required_kernels": ["Lean kernel", "leanchecker", "NanoDa", "con-ron"],
            },
        )
    try:
        official = load_json(report_path)
        head_proc = run_git(root, "rev-parse", "HEAD")
        if head_proc.returncode != 0:
            raise ValueError("current Git head is unavailable")
        head = head_proc.stdout.decode("ascii").strip()
        status_proc = run_git(root, "status", "--porcelain=v1", "--untracked-files=all")
        if status_proc.returncode != 0:
            raise ValueError("current Git status is unavailable")
        source = official.get("source", {})
        comparator = official.get("comparator", {})
        kernels = comparator.get("external_kernels", {})
        errors: list[str] = []
        if official.get("status") != "pass" or official.get("stage") != "complete":
            errors.append("official report is not a completed pass")
        if official.get("phase") != "verification":
            errors.append("official report is not a verification-phase report")
        if normalize_repository_id(str(source.get("repository", ""))) != config["wrapper_repository"]:
            errors.append("official report names a different wrapper repository")
        if source.get("commit") != head:
            errors.append("official report is not bound to the current Git head")
        if status_proc.stdout:
            errors.append("worktree is not clean at the reported Git head")
        theorem_names = comparator.get("theorem_names", [])
        if not isinstance(theorem_names, list) or set(theorem_names) != set(config["expected_theorems"]):
            errors.append("official report does not cover exactly the four expected declarations")
        axioms = comparator.get("permitted_axioms", [])
        if not isinstance(axioms, list) or set(axioms) != expected_axioms:
            errors.append("official report does not use exactly the standard axiom set")
        if not isinstance(kernels, dict) or not required_kernels <= set(kernels):
            errors.append("official report does not record protected nanoda and con-ron kernels")
        return Check(
            "proof.authoritative_comparator", "pass" if not errors else "fail", "authoritative",
            "official final-snapshot verification passed with the expected declarations, axioms, and kernels" if not errors else "official report is present but does not match the required final-snapshot evidence",
            {
                "report_sha256": sha256_file(report_path),
                "source_commit": source.get("commit"),
                "workflow_url": official.get("workflow_url"),
                "errors": errors,
            },
        )
    except Exception as error:
        return Check(
            "proof.authoritative_comparator", "fail", "authoritative",
            f"official report could not be validated: {error}",
            {"report": str(report_path)},
        )


def metadata_checks(
    root: Path, config: dict[str, Any], policy: dict[str, Any], schema: dict[str, Any], checks: list[Check],
) -> dict[str, Any] | None:
    path = root / config["metadata_path"]
    if not path.is_file():
        add(checks, "metadata.present", "fail", "static", f"{path.name} is missing")
        return None
    size = path.stat().st_size
    limit = policy["limits"]["formalization_bytes"]
    add(
        checks, "metadata.size", "pass" if size <= limit else "fail", "static",
        f"metadata is {size} bytes (limit {limit})", bytes=size, limit=limit,
    )
    try:
        metadata = load_yaml(path)
    except Exception as error:
        add(checks, "metadata.yaml", "fail", "schema", str(error))
        return None

    errors = sorted(jsonschema.Draft7Validator(schema).iter_errors(metadata), key=lambda item: list(item.path))
    formatted = [f"/{'/'.join(map(str, error.path))}: {error.message}" for error in errors]
    add(
        checks, "metadata.schema", "pass" if not errors else "fail", "schema",
        "formalization.yaml validates against upstream v0.4" if not errors else "formalization.yaml violates upstream v0.4",
        errors=formatted[:50],
    )

    semantic: list[str] = []
    project = metadata.get("project", {})
    if not str(project.get("description", "")).strip():
        semantic.append("project.description must be nonempty")
    maintainers = project.get("responsible_maintainers")
    if not isinstance(maintainers, list) or not any(str(item).strip() for item in maintainers):
        semantic.append("project.responsible_maintainers must name at least one person")
    classification = metadata.get("classification", {})
    arxiv = classification.get("arxiv", [])
    msc = classification.get("msc2020", [])
    arxiv_min, arxiv_max = policy["formalization"]["classification_cardinality"]["arxiv"]
    msc_min, msc_max = policy["formalization"]["classification_cardinality"]["msc2020"]
    if not isinstance(arxiv, list) or not arxiv_min <= len(arxiv) <= arxiv_max or len(set(arxiv)) != len(arxiv):
        semantic.append(f"classification.arxiv must contain {arxiv_min}-{arxiv_max} distinct values")
    if not isinstance(msc, list) or not msc_min <= len(msc) <= msc_max or len(set(msc)) != len(msc):
        semantic.append(f"classification.msc2020 must contain {msc_min}-{msc_max} distinct values")
    if metadata.get("repository", {}).get("role") != "thin-wrapper":
        semantic.append("repository.role must be thin-wrapper for this project")
    notes = str(metadata.get("automation", {}).get("notes", ""))
    for disclosure in config.get("required_disclosures", []):
        if disclosure.casefold() not in notes.casefold():
            semantic.append(f"automation.notes must include disclosure {disclosure!r}")
    if metadata.get("review", {}).get("status") != "unchecked":
        semantic.append("review.status must remain unchecked until a review is actually recorded")
    add(
        checks, "metadata.palomar_minimum", "pass" if not semantic else "fail", "static",
        "metadata satisfies the selected Palomar semantic minimum" if not semantic else "metadata misses selected Palomar requirements",
        errors=semantic,
    )
    return metadata


def wrapper_source_checks(
    root: Path, files: list[Path], line_cap: int, module_exempt: set[str], checks: list[Check],
) -> dict[str, Any]:
    symlinks = [path.relative_to(root).as_posix() for path in files if path.is_symlink()]
    lean_bytes = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in files if path.suffix == ".lean" and path.is_file() and not path.is_symlink()
    }
    scan = inspect_source_map(lean_bytes, line_cap=line_cap, module_exempt=module_exempt)
    integrity_ok = not symlinks and not scan["invalid_utf8_count"]
    add(
        checks, "source.wrapper_integrity", "pass" if integrity_ok else "fail", "static",
        "wrapper Lean sources are regular UTF-8 files" if integrity_ok else "wrapper Lean source integrity failed",
        symlinks=symlinks[:50], invalid_utf8=scan["invalid_utf8_examples"],
    )
    add(
        checks, "source.wrapper_modules", "pass" if not scan["missing_module_count"] else "fail", "static",
        "all wrapper Lean sources have module headers" if not scan["missing_module_count"] else f"{scan['missing_module_count']} wrapper Lean sources lack module headers",
        files_checked=scan["files_checked"], examples=scan["missing_module_examples"],
    )
    add(
        checks, "source.wrapper_line_cap", "pass" if not scan["too_long_count"] else "fail", "static",
        f"all wrapper Lean sources are at most {line_cap} physical lines" if not scan["too_long_count"] else f"{scan['too_long_count']} wrapper Lean sources exceed {line_cap} lines",
        maximum_lines=scan["maximum_lines"], examples=scan["too_long_examples"],
    )
    return scan


def run_checks(
    root: Path, config: dict[str, Any], substantive_repo: Path | None,
    official_report: Path | None = None,
) -> dict[str, Any]:
    checks: list[Check] = []
    report_relative = config["report_path"]
    excluded = {report_relative}
    files = repository_files(root, excluded)

    snapshot_errors: list[str] = []
    for name, spec in config["upstream"].items():
        path = root / spec["path"]
        if not path.is_file():
            snapshot_errors.append(f"{name}: missing {spec['path']}")
        elif sha256_file(path) != spec["sha256"]:
            snapshot_errors.append(f"{name}: sha256 differs from palomar-check.json")
    add(
        checks, "upstream.snapshots", "pass" if not snapshot_errors else "fail", "static",
        "vendored upstream policy snapshots match their pins" if not snapshot_errors else "vendored upstream policy snapshots are not intact",
        errors=snapshot_errors,
    )
    schema = load_json(root / config["upstream"]["formalization_schema"]["path"])
    policy = load_json(root / config["upstream"]["browser_policy"]["path"])
    toolchain_policy = load_json(root / config["upstream"]["toolchains"]["path"])

    lakefiles = [
        path.relative_to(root).as_posix() for path in files
        if path.name in {"lakefile.toml", "lakefile.lean"}
    ]
    required = [config["metadata_path"], config["comparator_config_path"], "lean-toolchain", "lake-manifest.json"]
    missing = [name for name in required if not (root / name).is_file()]
    add(
        checks, "layout.project_root", "pass" if lakefiles == ["lakefile.toml"] and not missing else "fail", "static",
        "the selected project is the repository root with one lakefile.toml" if lakefiles == ["lakefile.toml"] and not missing else "the selected root layout is incomplete or ambiguous",
        lakefiles=lakefiles, missing=missing,
    )

    total_bytes = sum(path.lstat().st_size for path in files if path.exists())
    lfs = []
    compiled = []
    for path in files:
        if path.is_file() and not path.is_symlink():
            data = path.read_bytes()
            if data.startswith(LFS_HEADER):
                lfs.append(path.relative_to(root).as_posix())
            if path.suffix in COMPILED_SUFFIXES:
                compiled.append(path.relative_to(root).as_posix())
    submodules: list[str] = []
    staged = run_git(root, "ls-files", "--stage", "-z")
    if staged.returncode == 0:
        for entry in staged.stdout.split(b"\0"):
            if entry.startswith(b"160000 "):
                submodules.append(entry.split(b"\t", 1)[1].decode("utf-8"))
    repository_ok = total_bytes <= policy["limits"]["source_bytes"] and not lfs and not compiled and not submodules
    add(
        checks, "repository.integrity", "pass" if repository_ok else "fail", "static",
        "repository source snapshot meets static integrity limits" if repository_ok else "repository source snapshot has prohibited content",
        bytes=total_bytes, byte_limit=policy["limits"]["source_bytes"], lfs_pointers=lfs,
        compiled_artifacts=compiled, submodules=submodules,
    )

    metadata = metadata_checks(root, config, policy, schema, checks)
    module_exempt = set(policy["lean_sources"]["module_exempt_filenames"])
    wrapper_scan = wrapper_source_checks(
        root, files, policy["limits"]["lean_source_lines"], module_exempt, checks
    )

    toolchain_text = (root / "lean-toolchain").read_text(encoding="utf-8").strip()
    match = re.fullmatch(policy["toolchain"]["pattern"], toolchain_text)
    release = f"v{'.'.join(match.groups()[:3])}" if match else None
    if match and match.group(4) is not None:
        release += f"-rc{match.group(4)}"
    add(
        checks, "toolchain.pinned_release", "pass" if match else "fail", "static",
        f"toolchain is pinned to {release}" if match else "lean-toolchain is not a supported release-form pin",
        value=toolchain_text,
    )
    minimum = toolchain_policy["minimum"]
    supported = bool(release and parse_version(release) >= parse_version(minimum))
    add(
        checks, "toolchain.supported", "pass" if supported else "fail", "static",
        f"Lean {release} meets the current minimum {minimum}" if supported else f"Lean {release or toolchain_text} is below the current minimum {minimum}",
        selected=release, minimum=minimum,
    )

    manifest = load_json(root / "lake-manifest.json")
    packages = {item.get("name"): item for item in manifest.get("packages", []) if isinstance(item, dict)}
    mathlib = packages.get("mathlib", {})
    mathlib_ok = bool(
        release and mathlib.get("url") == "https://github.com/leanprover-community/mathlib4"
        and FULL_SHA_RE.fullmatch(str(mathlib.get("rev", "")))
        and mathlib.get("inputRev") == release
    )
    add(
        checks, "mathlib.wrapper_pin", "pass" if mathlib_ok else "fail", "static",
        "wrapper manifest pins canonical Mathlib at the selected Lean release" if mathlib_ok else "wrapper Mathlib pin does not match the selected Lean release",
        url=mathlib.get("url"), revision=mathlib.get("rev"), input_revision=mathlib.get("inputRev"),
    )

    with (root / "lakefile.toml").open("rb") as handle:
        lakefile = tomllib.load(handle)
    dependency_name = config["substantive_dependency_name"]
    requirements = [item for item in lakefile.get("require", []) if item.get("name") == dependency_name]
    dependency = requirements[0] if len(requirements) == 1 else {}
    manifest_dependency = packages.get(dependency_name, {})
    metadata_source = (metadata or {}).get("repository", {}).get("substantive_formalization", {})
    dependency_revision = str(dependency.get("rev", ""))
    revision_ok = bool(
        len(requirements) == 1 and FULL_SHA_RE.fullmatch(dependency_revision)
        and manifest_dependency.get("rev") == dependency_revision
        and manifest_dependency.get("inputRev") == dependency_revision
        and metadata_source.get("revision") == dependency_revision
    )
    add(
        checks, "substantive.immutable_pin", "pass" if revision_ok else "fail", "static",
        "Lake, manifest, and metadata agree on one immutable substantive revision" if revision_ok else "substantive revision pins are missing or inconsistent",
        lakefile_revision=dependency.get("rev"), manifest_revision=manifest_dependency.get("rev"),
        manifest_input_revision=manifest_dependency.get("inputRev"), metadata_revision=metadata_source.get("revision"),
    )
    canonical = config["canonical_substantive_repository"]
    lake_repository = normalize_repository_id(str(dependency.get("git", "")))
    manifest_repository = normalize_repository_id(str(manifest_dependency.get("url", "")))
    metadata_repository = normalize_repository_id(str(metadata_source.get("id", "")))
    canonical_ok = lake_repository == manifest_repository == metadata_repository == canonical
    add(
        checks, "substantive.canonical_repository", "pass" if canonical_ok else "fail", "static",
        "all substantive references use the canonical repository" if canonical_ok else "the substantive dependency still uses a noncanonical repository name",
        expected=canonical, lakefile=lake_repository, manifest=manifest_repository, metadata=metadata_repository,
    )

    license_candidates = sorted(
        path.name for path in root.iterdir() if path.is_file() and LICENSE_RE.fullmatch(path.name)
    )
    license_ok = len(license_candidates) == 1
    recognized = None
    if license_ok:
        license_text = (root / license_candidates[0]).read_text(encoding="utf-8")
        if re.search(r"Apache\s+License\s+Version\s+2\.0", license_text, re.IGNORECASE):
            recognized = "Apache-2.0"
    metadata_license = (metadata or {}).get("project", {}).get("license")
    license_ok = license_ok and recognized == metadata_license == "Apache-2.0"
    add(
        checks, "license.root", "pass" if license_ok else "fail", "static",
        "exactly one root license is recognized as Apache-2.0 and matches metadata" if license_ok else "root license count, recognition, or metadata does not match",
        candidates=license_candidates, recognized=recognized, metadata=metadata_license,
    )

    comparator = load_json(root / config["comparator_config_path"])
    required_keys = set(policy["comparator"]["required_keys"])
    allowed_keys = set(policy["comparator"]["allowed_keys"])
    key_ok = required_keys <= comparator.keys() <= allowed_keys
    theorem_names = comparator.get("theorem_names", [])
    declarations_ok = (
        isinstance(theorem_names, list) and len(theorem_names) == len(set(theorem_names))
        and set(theorem_names) == set(config["expected_theorems"])
    )
    expected_axioms = set(policy["comparator"]["standard_axioms"])
    axioms = comparator.get("permitted_axioms", [])
    axioms_ok = isinstance(axioms, list) and set(axioms) == expected_axioms and len(axioms) == len(expected_axioms)
    nanoda_ok = comparator.get("enable_nanoda") is True
    comparator_ok = key_ok and declarations_ok and axioms_ok and nanoda_ok
    add(
        checks, "comparator.configuration", "pass" if comparator_ok else "fail", "static",
        "comparator config names the four targets, only standard axioms, and NanoDa" if comparator_ok else "comparator config differs from the selected Palomar profile",
        required_keys=sorted(required_keys), actual_keys=sorted(comparator), theorem_names=theorem_names,
        permitted_axioms=axioms, enable_nanoda=comparator.get("enable_nanoda"),
        note="Palomar's official verifier injects protected NanoDa and con-ron commands; this field is compatibility data, not kernel evidence.",
    )

    challenge_name = str(comparator.get("challenge_module", ""))
    solution_name = str(comparator.get("solution_module", ""))
    challenge_path = root / module_path(challenge_name)
    solution_path = root / module_path(solution_name)
    module_selection_ok = challenge_name != solution_name and challenge_path.is_file() and solution_path.is_file()
    add(
        checks, "comparator.modules", "pass" if module_selection_ok else "fail", "static",
        "Challenge and Solution select distinct regular source files" if module_selection_ok else "Challenge or Solution module selection is invalid",
        challenge=challenge_path.relative_to(root).as_posix() if challenge_path.exists() else str(challenge_path),
        solution=solution_path.relative_to(root).as_posix() if solution_path.exists() else str(solution_path),
    )

    challenge_text = challenge_path.read_text(encoding="utf-8") if challenge_path.is_file() else ""
    challenge_lines = physical_lines(challenge_text)
    challenge_bytes = len(challenge_text.encode("utf-8"))
    challenge_limits = config["challenge_limits"]
    challenge_size_ok = challenge_lines <= challenge_limits["lines"] and challenge_bytes <= challenge_limits["bytes"]
    add(
        checks, "challenge.size", "pass" if challenge_size_ok else "fail", "static",
        f"Challenge is {challenge_lines} lines and {challenge_bytes} bytes" if challenge_size_ok else "Challenge exceeds a hard size limit",
        lines=challenge_lines, line_limit=challenge_limits["lines"], bytes=challenge_bytes,
        byte_limit=challenge_limits["bytes"],
    )

    local_modules = {
        path.relative_to(root).with_suffix("").as_posix().replace("/", "."): path
        for path in files if path.suffix == ".lean" and path.is_file() and not path.is_symlink()
    }
    queue = [challenge_name]
    visited: set[str] = set()
    local_dependencies: set[str] = set()
    unknown_imports: set[str] = set()
    trusted_imports: set[str] = set()
    trusted_prefixes = set(config["trusted_challenge_prefixes"])
    while queue:
        module = queue.pop()
        if module in visited:
            continue
        visited.add(module)
        source = local_modules.get(module)
        if source is None:
            continue
        for imported in parse_imports(source.read_text(encoding="utf-8")):
            if imported in local_modules:
                local_dependencies.add(imported)
                queue.append(imported)
            elif imported.split(".", 1)[0] in trusted_prefixes:
                trusted_imports.add(imported)
            else:
                unknown_imports.add(imported)
    closure_paths = [local_modules[name] for name in visited if name in local_modules]
    closure_lines = sum(physical_lines(path.read_text(encoding="utf-8")) for path in closure_paths)
    closure_bytes = sum(path.stat().st_size for path in closure_paths)
    import_ok = not local_dependencies and not unknown_imports
    add(
        checks, "challenge.static_import_boundary", "pass" if import_ok else "fail", "static",
        "Challenge directly imports only trusted dependency roots" if import_ok else "Challenge reaches local or untrusted source modules",
        local_dependencies=sorted(local_dependencies)[:100], unknown_imports=sorted(unknown_imports),
        trusted_imports=sorted(trusted_imports), local_closure_files=len(closure_paths),
        local_closure_lines=closure_lines, local_closure_bytes=closure_bytes,
    )

    substantive_evidence: dict[str, Any] | None = None
    if substantive_repo is None:
        add(
            checks, "source.substantive_requirements", "unknown", "static",
            "no local substantive repository was supplied for the pinned-revision source scan",
            expected_revision=dependency_revision,
        )
        add(
            checks, "mathlib.substantive_match", "unknown", "static",
            "the substantive toolchain and Mathlib revision were not inspected",
        )
    else:
        try:
            substantive_evidence = inspect_substantive(
                substantive_repo.resolve(), dependency_revision,
                policy["limits"]["lean_source_lines"], module_exempt,
            )
            substantive_ok = (
                not substantive_evidence["missing_module_count"]
                and not substantive_evidence["too_long_count"]
                and not substantive_evidence["invalid_utf8_count"]
                and not substantive_evidence["symlinks"]
                and not substantive_evidence["submodules"]
            )
            add(
                checks, "source.substantive_requirements", "pass" if substantive_ok else "fail", "static",
                "pinned substantive Lean sources meet module and line requirements" if substantive_ok else "pinned substantive Lean sources fail module or line requirements",
                files_checked=substantive_evidence["files_checked"],
                missing_module_count=substantive_evidence["missing_module_count"],
                missing_module_examples=substantive_evidence["missing_module_examples"],
                too_long_count=substantive_evidence["too_long_count"],
                too_long_examples=substantive_evidence["too_long_examples"],
                maximum_lines=substantive_evidence["maximum_lines"],
                symlinks=substantive_evidence["symlinks"], submodules=substantive_evidence["submodules"],
            )
            blobs = substantive_evidence["_blobs"]
            substantive_toolchain = blobs.get("lean-toolchain", b"").decode("utf-8", "replace").strip()
            substantive_manifest = json.loads(blobs.get("lake-manifest.json", b"{}").decode("utf-8"))
            substantive_packages = {
                item.get("name"): item for item in substantive_manifest.get("packages", []) if isinstance(item, dict)
            }
            substantive_mathlib = substantive_packages.get("mathlib", {})
            match_ok = (
                substantive_toolchain == toolchain_text
                and substantive_mathlib.get("rev") == mathlib.get("rev")
                and substantive_mathlib.get("inputRev") == mathlib.get("inputRev")
            )
            add(
                checks, "mathlib.substantive_match", "pass" if match_ok else "fail", "static",
                "wrapper and substantive repository use the same Lean and Mathlib revisions" if match_ok else "wrapper and substantive repository toolchain or Mathlib revisions differ",
                wrapper_toolchain=toolchain_text, substantive_toolchain=substantive_toolchain,
                wrapper_mathlib=mathlib.get("rev"), substantive_mathlib=substantive_mathlib.get("rev"),
            )
        except Exception as error:
            add(
                checks, "source.substantive_requirements", "fail", "static",
                f"could not inspect the pinned substantive revision: {error}",
            )
            add(
                checks, "mathlib.substantive_match", "unknown", "static",
                "substantive toolchain comparison was unavailable after the source-scan failure",
            )

    lexical_details = {
        "wrapper_matches_at_least": wrapper_scan["lexical_escape_match_count_at_least"],
        "wrapper_examples": wrapper_scan["lexical_escape_examples"],
    }
    if substantive_evidence is not None:
        lexical_details.update(
            substantive_matches_at_least=substantive_evidence["lexical_escape_match_count_at_least"],
            substantive_examples=substantive_evidence["lexical_escape_examples"],
        )
    add(
        checks, "proof.lexical_source_scan", "unknown", "static",
        "lexical scans are recorded but cannot certify proof completion or axiom closure",
        **lexical_details,
    )
    checks.append(authoritative_report_check(root, official_report, config, expected_axioms))

    statuses = {check.status for check in checks}
    overall = "fail" if "fail" in statuses else "unknown" if "unknown" in statuses else "pass"
    report: dict[str, Any] = {
        "schema_version": 1,
        "checker": "tools/palomar/check.py",
        "overall": overall,
        "evidence_model": {
            "schema": "validation against a byte-pinned public schema",
            "static": "non-executing source/configuration inspection",
            "authoritative": "kernel/comparator evidence from an official final-snapshot run",
        },
        "inputs": {
            "wrapper": input_manifest(root, excluded),
            "substantive": None,
            "upstream": config["upstream"],
        },
        "checks": [asdict(check) for check in checks],
    }
    if substantive_evidence is not None:
        report["inputs"]["substantive"] = {
            "repository": canonical,
            "revision": substantive_evidence["revision"],
            "tree": substantive_evidence["tree"],
            "lean_files": substantive_evidence["files_checked"],
            "lean_sources_sha256": substantive_evidence["content_sha256"],
            "special_files": substantive_evidence["special_files"],
        }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "report"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=Path, default=Path("palomar-check.json"))
    parser.add_argument("--substantive-repo", type=Path)
    parser.add_argument("--official-report", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    config = load_json(config_path)
    report = run_checks(root, config, args.substantive_repo, args.official_report)
    encoded = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if args.command == "report":
        output = args.output or Path(config["report_path"])
        output = output if output.is_absolute() else root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    return 1 if report["overall"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())

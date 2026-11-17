"""Export a curated working-tree snapshot without Git history or runtime data."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT_FILES = {
    "CareerPilot_Codex_Development_Spec_v1.0.md",
    "CareerPilot_Revised_Product_M2_M4_Spec_v2.md",
    "README.md",
    "AGENTS.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    ".env.example",
    ".gitignore",
    ".dockerignore",
    "Makefile",
    "docker-compose.yml",
}
PUBLIC_DOCS = {
    "USER_GUIDE.md",
    "INTERVIEW_NOTES.md",
    "PUBLIC_STATUS.md",
    "PUBLIC_WEBSITE.md",
    "OPEN_SOURCE_RELEASE.md",
}
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    ".next",
    "__pycache__",
    ".cache",
    ".local",
    ".config",
    ".fontconfig",
    "var",
    "uploads",
    "backups",
    "test-results",
    "playwright-report",
    "blob-report",
    "coverage",
    "dist",
}


def include(path: Path) -> bool:
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    if path.name.startswith(".env") and path.name != ".env.example":
        return False
    if path.suffix in {
        ".key",
        ".pem",
        ".log",
        ".sql",
        ".har",
        ".tsbuildinfo",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".p12",
        ".pfx",
    }:
        return False
    if len(path.parts) == 1:
        return path.name in ROOT_FILES
    if path.parts[0] == "docs":
        return len(path.parts) == 2 and (
            path.name in PUBLIC_DOCS
            or path.name.startswith(("M2_", "M3_", "M4_", "M5_", "M6_"))
            and path.suffix == ".md"
        )
    return path.parts[0] in {"apps", "backend", "infra", "scripts", ".github"}


def export(root: Path, destination: Path) -> None:
    if destination.exists():
        raise SystemExit(
            "Destination exists; choose a new directory. Nothing was overwritten."
        )
    candidates = (
        subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
        )
        .decode()
        .split("\0")
    )
    selected = []
    excluded = []
    for name in sorted(set(filter(None, candidates))):
        path = Path(name)
        source = root / path
        if not source.is_file():
            continue
        if source.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
            raise SystemExit(f"Refusing symlink or external path: {name}")
        (selected if include(path) else excluded).append(name)
    required = ROOT_FILES | {f"docs/{name}" for name in PUBLIC_DOCS}
    if missing := required - set(selected):
        raise SystemExit(f"Missing release inputs: {', '.join(sorted(missing))}")
    destination.mkdir(parents=True)
    entries = []
    for name in selected:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
        entries.append(
            {"path": name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        )
    # Keep the documented entry point, replacing private iteration logs with a
    # public summary. The original file and Git history are never changed.
    status = destination / "docs/IMPLEMENTATION_STATUS.md"
    shutil.copy2(root / "docs/PUBLIC_STATUS.md", status)
    entries.append(
        {
            "path": "docs/IMPLEMENTATION_STATUS.md",
            "sha256": hashlib.sha256(status.read_bytes()).hexdigest(),
        }
    )
    manifest = {
        "kind": "curated-working-tree-export",
        "contains_git_history": False,
        "note": "This export is not a security certification. Review before publishing.",
        "files": entries,
        "excluded_file_count": len(excluded),
    }
    (destination / "RELEASE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "destination": str(destination),
                "included": len(entries),
                "excluded": len(excluded),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("dist/open-source/CareerPilot")
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    export(root, args.output.resolve())


if __name__ == "__main__":
    main()

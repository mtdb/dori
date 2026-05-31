import json
import os
import sys
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".worktrees",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
KNOWN_FILES = {
    "AGENTS.md": "Dori/Codex agent instructions",
    "Cargo.toml": "Rust package",
    "Dockerfile": "Docker container build",
    "Gemfile": "Ruby dependencies",
    "Makefile": "Make automation",
    "README.md": "project documentation",
    "compose.yaml": "Docker Compose setup",
    "docker-compose.yml": "Docker Compose setup",
    "go.mod": "Go module",
    "package.json": "Node/JavaScript package",
    "poetry.lock": "Python Poetry lockfile",
    "pyproject.toml": "Python project metadata",
    "requirements.txt": "Python dependencies",
}
ENTRYPOINT_NAMES = {
    "app.py",
    "main.go",
    "main.py",
    "manage.py",
    "server.js",
    "src/main.rs",
}
MAX_WALK_FILES = 2000
MAX_TEXT_CHARS = 8000


def read_text(path: Path, limit: int = MAX_TEXT_CHARS) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}


def read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(read_text(path))
    except tomllib.TOMLDecodeError:
        return {}


def first_readme(root: Path) -> tuple[str | None, str | None]:
    readmes = sorted(root.glob("README*"))
    if not readmes:
        return None, None

    text = read_text(readmes[0])
    title = None
    paragraphs: list[str] = []
    current: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("#") and title is None:
            title = line.lstrip("#").strip()
            continue
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if line.startswith(("#", "```", "!", "[!")):
            continue
        current.append(line)

    if current:
        paragraphs.append(" ".join(current))

    summary = paragraphs[0] if paragraphs else None
    return title, summary


def scan_tree(root: Path) -> tuple[int, int, Counter[str], list[str]]:
    file_count = 0
    dir_count = 0
    extensions: Counter[str] = Counter()
    entrypoints: list[str] = []

    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in IGNORED_DIRS]
        dir_count += len(dirnames)
        current_path = Path(current_root)

        for filename in filenames:
            file_count += 1
            path = current_path / filename
            relative = path.relative_to(root).as_posix()

            suffix = path.suffix.lower() or "no extension"
            extensions[suffix] += 1

            if filename in ENTRYPOINT_NAMES or relative in ENTRYPOINT_NAMES:
                entrypoints.append(relative)

            if file_count >= MAX_WALK_FILES:
                return file_count, dir_count, extensions, sorted(entrypoints)

    return file_count, dir_count, extensions, sorted(entrypoints)


def detect_metadata(root: Path) -> tuple[str, str | None, list[str]]:
    signals: list[str] = []
    project_name = root.name
    description = None

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        data = read_toml(pyproject)
        project = data.get("project", {})
        poetry = data.get("tool", {}).get("poetry", {})
        project_name = project.get("name") or poetry.get("name") or project_name
        description = (
            project.get("description") or poetry.get("description") or description
        )
        signals.append("Python project metadata")

    package_json = root / "package.json"
    if package_json.is_file():
        data = read_json(package_json)
        project_name = data.get("name") or project_name
        description = data.get("description") or description
        signals.append("Node/JavaScript package metadata")

    cargo = root / "Cargo.toml"
    if cargo.is_file():
        data = read_toml(cargo)
        package = data.get("package", {})
        project_name = package.get("name") or project_name
        description = package.get("description") or description
        signals.append("Rust package metadata")

    if (root / "go.mod").is_file():
        signals.append("Go module")
    if (root / "Dockerfile").is_file():
        signals.append("Docker build file")
    if (root / "compose.yaml").is_file() or (root / "docker-compose.yml").is_file():
        signals.append("Docker Compose configuration")

    return str(project_name), description, signals


def top_level_signals(root: Path) -> list[str]:
    signals = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if path.name in IGNORED_DIRS:
            continue
        if path.is_file() and path.name in KNOWN_FILES:
            signals.append(f"{path.name}: {KNOWN_FILES[path.name]}")
    return signals


def format_list(items: list[str], empty: str, limit: int = 6) -> str:
    if not items:
        return f"- {empty}"
    return "\n".join(f"- {item}" for item in items[:limit])


def analyze_folder(root: Path, focus: str | None = None) -> str:
    name, metadata_description, metadata_signals = detect_metadata(root)
    readme_title, readme_summary = first_readme(root)
    file_count, dir_count, extensions, entrypoints = scan_tree(root)

    description = metadata_description or readme_summary
    if not description:
        description = "No README summary or package description was found."

    signal_lines = metadata_signals + top_level_signals(root)
    extension_lines = [f"{ext}: {count}" for ext, count in extensions.most_common(5)]

    lines = [
        "📁 [Folder Analysis]",
        f"Path: {root}",
        f"Project: {readme_title or name}",
    ]
    if focus:
        lines.append(f"Focus: {focus}")
    lines.extend(
        [
            f"What it does: {description}",
            f"Size: {file_count} files across {dir_count} directories scanned",
            "Detected signals:",
            format_list(signal_lines, "No common project metadata files found."),
            "Likely entry points:",
            format_list(entrypoints, "No common entry point filenames found."),
            "Main file types:",
            format_list(extension_lines, "No files found."),
        ]
    )
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload", file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        print(
            "Error: Invalid JSON payload provided to analyze-folder script.",
            file=sys.stderr,
        )
        sys.exit(1)

    path_text = str(payload.get("path") or payload.get("directory") or ".")
    root = Path(path_text).expanduser().resolve()
    if not root.exists():
        print(f"Error: Directory does not exist: {root}", file=sys.stderr)
        sys.exit(1)
    if not root.is_dir():
        print(f"Error: Path is not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    focus = payload.get("focus")
    print(analyze_folder(root, str(focus) if focus else None))


if __name__ == "__main__":
    main()

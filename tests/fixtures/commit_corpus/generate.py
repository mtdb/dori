"""Generate commit-message eval fixtures from angular and dori commits.

Each fixture stores the real diff plus curated expectations:
- expected_types: acceptable conventional commit types (any of)
- expected_keywords: groups; the generated subject+body must match at least
  one alternative from every group (case-insensitive substring)
- expected_scopes: soft signal, reported but not asserted
"""

import json
import os
import subprocess
import urllib.request
from pathlib import Path

DORI = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent

ANGULAR_CASES = [
    {
        "id": "angular-i18n-select-hasown",
        "sha": "311aff05aa2c",
        "expected_types": ["fix"],
        "expected_scopes": ["common", "i18n"],
        "expected_keywords": [
            ["hasOwn", "hasOwnProperty", "null-prototype", "null prototype"],
            ["I18nSelectPipe", "i18n", "pipe", "mapping"],
        ],
    },
    {
        "id": "angular-forms-docs-signal-call",
        "sha": "e653a7bf3028",
        "expected_types": ["docs", "fix"],
        "expected_scopes": ["forms", "docs"],
        "expected_keywords": [
            ["myForm", "form model", "signal", "example"],
        ],
    },
    {
        "id": "angular-compiler-rename-visitor",
        "sha": "74803c75cd88",
        "expected_types": ["refactor"],
        "expected_scopes": ["compiler"],
        "expected_keywords": [
            ["visitAttributeComment", "visitStartTagComment", "StartTagComment"],
        ],
    },
    {
        "id": "angular-sw-referrer-policy",
        "sha": "6f98f98f1f41",
        "expected_types": ["fix"],
        "expected_scopes": ["service-worker"],
        "expected_keywords": [
            ["referrer"],
        ],
    },
    {
        "id": "angular-zonejs-proto-hardening",
        "sha": "2d33fd55ff0f",
        # perf accepted: with no tests or security mention in the diff,
        # Object.create(null) reads as a perf/hardening tweak either way.
        "expected_types": ["fix", "refactor", "perf"],
        "expected_scopes": ["zone.js", "zone"],
        "expected_keywords": [
            [
                "__proto__",
                "proto",
                "pollution",
                "hasOwn",
                "Object.create(null)",
                "null prototype",
                "harden",
            ],
        ],
    },
    {
        "id": "angular-core-injectasync-promise",
        "sha": "91d168e74b7c",
        "expected_types": ["fix"],
        "expected_scopes": ["core"],
        "expected_keywords": [
            ["injectAsync"],
            ["promise", "error", "rejection"],
        ],
    },
]

DORI_CASES = [
    {
        "id": "dori-update-workspace-md5",
        "sha": "ae48663",
        # curated: original said "fix(dori): add md5 check for unchanged
        # files in update_workspace command"
        "curated_subject": "fix(commands): skip unchanged files in update_workspace via md5 check",
        "expected_types": ["fix", "feat", "perf", "refactor"],
        "expected_scopes": ["commands", "update"],
        "expected_keywords": [
            ["md5", "hash", "unchanged", "identical"],
        ],
    },
    {
        "id": "dori-tui-missing-widgets",
        "sha": "950e7d8",
        "curated_subject": "fix(tui): handle missing widgets when updating status and prompt labels",
        "expected_types": ["fix"],
        "expected_scopes": ["tui", "dori"],
        "expected_keywords": [
            ["widget", "label", "status"],
        ],
    },
    {
        "id": "dori-script-partial-writes",
        "sha": "e152f4b",
        "curated_subject": "fix(script): handle partial writes and reject string choices",
        "expected_types": ["fix"],
        "expected_scopes": ["script"],
        "expected_keywords": [
            ["write", "choices", "choose"],
        ],
    },
    {
        "id": "dori-script-protocol-version-test",
        "sha": "9793ea9",
        "curated_subject": "test(script): cover protocol version rejection",
        "expected_types": ["test"],
        "expected_scopes": ["script"],
        "expected_keywords": [
            ["protocol", "version"],
        ],
    },
    {
        "id": "dori-pyproject-license-metadata",
        "sha": "f530688",
        "curated_subject": "build: add license and metadata to pyproject.toml",
        "expected_types": ["build", "chore"],
        "expected_scopes": [],
        "expected_keywords": [
            ["license", "metadata", "pyproject"],
        ],
    },
    {
        "id": "dori-remove-persona-migration",
        "sha": "09511fd",
        "curated_subject": "refactor(commands): remove legacy persona migration",
        "expected_types": ["refactor", "chore"],
        "expected_scopes": ["commands"],
        "expected_keywords": [
            ["persona"],
            ["migration", "legacy", "remove"],
        ],
    },
]


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


def diff_files(diff_text: str) -> list[dict]:
    files = []
    current = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            path = line.split(" b/", 1)[1] if " b/" in line else line.split()[-1]
            current = {"path": path, "status": "modified"}
            files.append(current)
        elif current and line.startswith("new file mode"):
            current["status"] = "new"
        elif current and line.startswith("deleted file mode"):
            current["status"] = "deleted"
        elif current and line.startswith("rename to "):
            current["status"] = "renamed"
    return files


def diff_stat(diff_text: str) -> str:
    result = subprocess.run(
        ["git", "apply", "--stat"],
        input=diff_text,
        capture_output=True,
        text=True,
        cwd=DORI,
        check=True,
    )
    return result.stdout.strip()


def fetch_angular_diff(sha: str) -> str:
    url = f"https://github.com/angular/angular/commit/{sha}.diff"
    with urllib.request.urlopen(url) as response:
        return response.read().decode("utf-8")


def _github_json(url: str):
    request = urllib.request.Request(url)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def angular_recent_subjects(sha: str) -> list[str]:
    url = f"https://api.github.com/repos/angular/angular/commits?sha={sha}&per_page=6"
    commits = _github_json(url)
    return [c["commit"]["message"].splitlines()[0] for c in commits[1:6]]


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    for case in ANGULAR_CASES:
        sha = case["sha"]
        diff = fetch_angular_diff(sha)
        fixture = {
            "id": case["id"],
            "source": f"angular/angular@{sha}",
            "original_subject": None,  # filled below
            "expected_types": case["expected_types"],
            "expected_scopes": case["expected_scopes"],
            "expected_keywords": case["expected_keywords"],
            "files": diff_files(diff),
            "stat": diff_stat(diff),
            "diff": diff,
            "recent_subjects": angular_recent_subjects(sha),
        }
        url = f"https://api.github.com/repos/angular/angular/commits/{sha}"
        fixture["original_subject"] = _github_json(url)["commit"][
            "message"
        ].splitlines()[0]
        (OUT / f"{case['id']}.json").write_text(
            json.dumps(fixture, indent=2, ensure_ascii=False) + "\n"
        )
        print("wrote", case["id"], len(diff), "chars")

    for case in DORI_CASES:
        sha = case["sha"]
        diff = git(DORI, "show", "--format=", sha)
        subjects = (
            git(DORI, "log", "--format=%s", "-5", f"{sha}~1").strip().splitlines()
        )
        fixture = {
            "id": case["id"],
            "source": f"dori@{sha}",
            "original_subject": git(DORI, "log", "-1", "--format=%s", sha).strip(),
            "curated_subject": case["curated_subject"],
            "expected_types": case["expected_types"],
            "expected_scopes": case["expected_scopes"],
            "expected_keywords": case["expected_keywords"],
            "files": diff_files(diff),
            "stat": diff_stat(diff),
            "diff": diff,
            "recent_subjects": subjects,
        }
        (OUT / f"{case['id']}.json").write_text(
            json.dumps(fixture, indent=2, ensure_ascii=False) + "\n"
        )
        print("wrote", case["id"], len(diff), "chars")


if __name__ == "__main__":
    main()

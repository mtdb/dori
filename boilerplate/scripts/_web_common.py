import re
from collections.abc import Iterable, Mapping
from typing import Any

ABSTENTION_MESSAGE = "[Web]: I could not find enough reliable web evidence to answer."
VALID_FRESHNESS = {"day", "week", "month", "year"}
MAX_RESULTS = 5
MAX_SNIPPET_CHARS = 700
MAX_ANSWER_CHARS = 3000
URL_PATTERN = re.compile(r"https?://[^\s)>]+")


def normalize_freshness(value: Any) -> str | None:
    if value is None or value == "":
        return None

    freshness = str(value).strip().lower()
    if freshness not in VALID_FRESHNESS:
        raise ValueError("Unsupported freshness. Use day, week, month, or year.")
    return freshness


def normalize_evidence(results: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for result in results:
        url = str(result.get("url") or "").strip()
        if not url.startswith(("http://", "https://")) or url in seen_urls:
            continue

        title = str(result.get("title") or "Untitled source").strip()
        snippet = str(result.get("snippet") or "").strip()[:MAX_SNIPPET_CHARS]
        evidence.append({"title": title, "url": url, "snippet": snippet})
        seen_urls.add(url)

        if len(evidence) == MAX_RESULTS:
            break

    return evidence


def source_urls(evidence: Iterable[Mapping[str, str]]) -> list[str]:
    return [item["url"] for item in evidence if item.get("url")][:3]


def format_answer(answer: str, urls: Iterable[str]) -> str:
    clean_answer = answer.strip()[:MAX_ANSWER_CHARS]
    unique_urls = list(dict.fromkeys(urls))[:3]
    if not clean_answer or len(unique_urls) < 2:
        return ABSTENTION_MESSAGE

    sources = "\n".join(f"- {url}" for url in unique_urls)
    return f"{clean_answer}\n\nSources:\n{sources}"


def validate_grounded_answer(answer: str, allowed_urls: set[str]) -> bool:
    stripped = answer.strip()
    if not stripped or len(stripped) > MAX_ANSWER_CHARS:
        return False
    if "\n\nSources:\n" not in stripped:
        return False

    cited_urls = URL_PATTERN.findall(stripped.split("\n\nSources:\n", 1)[1])
    return (
        2 <= len(cited_urls) <= 3
        and len(cited_urls) == len(set(cited_urls))
        and all(url in allowed_urls for url in cited_urls)
    )

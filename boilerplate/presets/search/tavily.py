import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from _web_common import (
    ABSTENTION_MESSAGE,
    MAX_RESULTS,
    format_answer,
    normalize_evidence,
    normalize_freshness,
    source_urls,
)

TAVILY_ENDPOINT = "https://api.tavily.com/search"
REQUEST_TIMEOUT_SECONDS = 15
SEARCH_BACKEND = "tavily"


class WebSearchError(RuntimeError):
    pass


def build_request(query: str, freshness: str | None, api_key: str) -> Request:
    body: dict[str, Any] = {
        "query": query,
        "search_depth": "basic",
        "include_answer": "basic",
        "max_results": MAX_RESULTS,
    }
    if freshness is not None:
        body["time_range"] = freshness

    return Request(
        TAVILY_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )


def search(query: str, freshness: str | None, api_key: str) -> dict[str, Any]:
    request = build_request(query, freshness, api_key)
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == 401:
            message = "Tavily rejected TAVILY_API_KEY."
        elif error.code == 429:
            message = "Tavily rate limit reached. Please try again later."
        else:
            message = "Tavily search failed. Please try again."
        raise WebSearchError(message) from error
    except URLError as error:
        raise WebSearchError(
            "Could not connect to Tavily. Check your network and try again."
        ) from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WebSearchError("Tavily returned an invalid response.") from error

    if not isinstance(payload, dict):
        raise WebSearchError("Tavily returned an invalid response.")
    return payload


def answer_payload(payload: dict[str, Any]) -> str:
    query = str(payload.get("query") or "").strip()
    if not query:
        raise WebSearchError("Missing web search query.")

    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise WebSearchError(
            "TAVILY_API_KEY is required for the Tavily search backend."
        )

    freshness = normalize_freshness(payload.get("freshness"))
    response = search(query, freshness, api_key)
    answer = str(response.get("answer") or "").strip()
    raw_results = response.get("results")
    if not isinstance(raw_results, list):
        return ABSTENTION_MESSAGE

    evidence = normalize_evidence(
        {
            "title": item.get("title"),
            "url": item.get("url"),
            "snippet": item.get("content"),
        }
        for item in raw_results
        if isinstance(item, dict)
    )
    return format_answer(answer, source_urls(evidence))


def main() -> None:
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload", file=sys.stderr)
        raise SystemExit(1)

    try:
        payload = json.loads(sys.argv[1])
        if not isinstance(payload, dict):
            raise WebSearchError("Invalid web search payload.")
        print(answer_payload(payload))
    except json.JSONDecodeError as error:
        print("Error: Invalid JSON payload provided to web script.", file=sys.stderr)
        raise SystemExit(1) from error
    except (ValueError, WebSearchError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()

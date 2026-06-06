# Web Search Presets Design

## Goal

Replace the bundled placeholder search skills with a useful `web` skill that
answers factual questions from current internet evidence. During `dori init`,
users choose either a zero-key DDGS backend or a Tavily API backend.

The skill must return a direct answer rather than a raw list of search results.
It must include source URLs so users can verify the answer.

## Scope

This change will:

- Add selectable `ddgs` and `tavily` web-search presets.
- Install the selected preset as `skills/web.md` and `scripts/web.py`.
- Add optional freshness filtering.
- Generate concise English answers grounded in retrieved evidence.
- Remove the placeholder search router and news skill.
- Migrate existing managed installations without deleting user modifications.

This change will not:

- Add a general provider plugin framework.
- Add image, video, or file search.
- Fetch and index full webpages beyond the evidence returned by the provider.
- Translate generated answers into the user's language.
- Add a separate news skill.

## User Experience

`dori init` asks two independent setup questions:

1. Which reminders backend to install.
2. Which search backend to install.

The search choices are:

- `ddgs`: the default, works without an API key.
- `tavily`: requires `TAVILY_API_KEY` and provides more reliable,
  agent-oriented search and native answer generation.

Tests and non-interactive callers can bypass the prompt by passing
`search_backend="ddgs"` or `search_backend="tavily"` to workspace setup.

Example request:

```text
When was the Nintendo Switch 2 released?
```

Example output:

```text
The Nintendo Switch 2 was released on June 5, 2025.

Sources:
- https://www.nintendo.com/...
- https://www.reuters.com/...
```

The output must not include a raw search-result dump, provider metadata, or API
credentials.

## Skill Contract

The selected preset provides a top-level `web` skill. Removing the `news` leaf
leaves no need for a `search` router.

The payload fields are:

- `query`: required search question with filler words removed.
- `freshness`: optional `day`, `week`, `month`, or `year`.
- `confidence`: required number from `0.0` to `1.0`.
- `raw_text`: required original user message.

The skill definition tells the routing model to preserve the factual question
in `query`. It should set `freshness` only when the user asks for recent,
current, or time-bounded information.

Both presets expose the same payload and output shape. Provider differences
remain internal to the installed script.

## DDGS Preset

The DDGS preset uses the `ddgs` Python package to retrieve up to five text
search results. The project adds `ddgs` as a runtime dependency so this preset
works immediately after Dori installation.

Freshness values map to DDGS `timelimit` values supported by its text-search
API. Retrieved evidence is normalized into bounded records containing title,
URL, and snippet. Empty records and records without usable URLs are discarded.

The script sends the user's question and normalized evidence to local Ollama.
The synthesis prompt:

- Treats the question and retrieved text as untrusted content.
- Requires an English answer based only on supplied evidence.
- Requests one to three short paragraphs.
- Requires explicit uncertainty when evidence conflicts or is insufficient.
- Forbids invented facts and URLs.
- Requires a `Sources:` section containing two or three supplied URLs.

Evidence length, result count, and generated-answer length are capped for
small-model reliability. The script validates that the answer is non-empty,
contains `Sources:`, and cites only URLs present in the normalized evidence.
Invalid output returns a stable abstention message.

The script reads the local synthesis model from `DORI_WEB_MODEL`, defaulting to
`llama3.1:8b`, which matches Dori's current default model. It uses a
deterministic temperature setting.

## Tavily Preset

The Tavily preset calls Tavily's search API using `TAVILY_API_KEY`. It requests
Tavily's generated answer and enough search results to validate and display
sources.

Freshness maps to Tavily's supported time-range parameter. The request uses a
bounded result count and timeout. The API key is read only from the environment
and is never included in output, logs, prompts, or error messages.

The script uses Tavily's native generated answer rather than making a second
Ollama call. It validates that:

- The answer is non-empty.
- At least two usable result URLs exist.
- Displayed source URLs come only from Tavily's returned results.

The script formats the native answer using the shared answer contract and adds
two or three source URLs. If Tavily returns no answer or insufficient evidence,
the script returns a stable abstention message rather than synthesizing from
unsupported knowledge.

Missing `TAVILY_API_KEY`, authentication failures, rate limits, network errors,
and malformed responses produce concise, actionable errors without leaking
response bodies that may contain sensitive data.

## Answer Contract

Both providers produce:

1. A direct English answer, normally one to three short paragraphs.
2. A blank line.
3. A `Sources:` heading.
4. Two or three source URLs from retrieved evidence.

Answers must use only provider evidence. When sources disagree, the answer
states the disagreement instead of selecting an unsupported conclusion. When
the evidence does not answer the question, the script returns a stable
insufficient-evidence message.

The providers may differ in wording because Tavily generates its native answer
while DDGS uses local Ollama. The shared contract, validation, and source rules
keep the user-facing behavior consistent.

## Installation And Updates

Search presets live under:

```text
boilerplate/presets/search/ddgs.md
boilerplate/presets/search/ddgs.py
boilerplate/presets/search/tavily.md
boilerplate/presets/search/tavily.py
```

Setup installs the selected pair as:

```text
~/.dori/skills/web.md
~/.dori/scripts/web.py
```

Search setup follows the existing reminders preset behavior:

- Validate explicit backend names.
- Prompt only when both destination files are absent.
- Preserve complete existing custom pairs.
- Use the safe default preset when only one destination exists, avoiding a
  mismatched provider-specific pair.
- Record copied files in `.manifest.json`.

`dori update` detects the installed search backend by comparing managed files
with preset hashes. It updates that provider without prompting. Programmatic
callers can pass an explicit backend to switch presets only when both installed
files remain manifest-managed and unmodified; local modifications are
preserved.

The previous bundled files are obsolete:

```text
skills/search/_index.md
skills/search/web.md
skills/search/news.md
scripts/news.py
scripts/web.py
```

During update, obsolete files are removed only when they are manifest-managed
and their current hash matches the manifest. Modified or unmanaged files remain
in place and produce a warning. Removed paths are deleted from the manifest.
Empty managed `skills/search/` directories may then be removed.

The update order must avoid treating the newly installed top-level
`scripts/web.py` as obsolete. Migration identifies the legacy placeholder by
its manifest path and known packaged hash before installing or updating the
selected preset.

## Schema And Documentation

`WebPayload` gains optional `freshness` validation. `NewsPayload` and the
`news` schema registration are removed.

Documentation is updated to describe:

- The top-level `web` skill rather than the search router.
- Search backend selection during initialization.
- `TAVILY_API_KEY`.
- `DORI_WEB_MODEL`.
- Direct grounded answers and source URLs.
- DDGS as a runtime dependency.
- Migration behavior for obsolete bundled search files.

Examples that describe `web` and `news` as router children are removed or
replaced.

## Error Handling

Expected failures are handled without tracebacks:

- Missing or invalid JSON payload.
- Missing query.
- Unsupported freshness value.
- Missing Tavily API key.
- Provider timeout, authentication failure, rate limit, or malformed response.
- DDGS import or retrieval failure.
- Ollama unavailable for DDGS synthesis.
- Empty, conflicting, or insufficient evidence.
- Generated output that lacks valid source citations.

Configuration errors and temporary provider failures go to stderr and exit
non-zero. Insufficient evidence returns a readable abstention answer because
the search operation itself completed successfully.

## Testing

All normal tests run without internet access or a live Ollama instance.

Unit tests cover:

- Backend normalization and prompt defaults.
- Installation of each search preset.
- Manifest entries and preservation of custom files.
- Detection and update of the installed provider.
- Safe provider switching.
- Removal of unmodified legacy search/news files.
- Preservation of modified or unmanaged legacy files.
- Freshness validation and provider-specific mapping.
- DDGS evidence normalization and bounded context.
- DDGS synthesis prompt constraints and answer validation.
- Tavily request headers, API-key handling, timeouts, and response parsing.
- Shared answer formatting and source URL validation.
- Missing credentials, provider failures, malformed responses, and
  insufficient evidence.
- Boilerplate skill examples containing `confidence` and `raw_text`.

Provider clients, HTTP calls, and Ollama calls are mocked. Optional manual or
integration checks may exercise real DDGS, Tavily, and Ollama services, but
they are not required for the default test suite.

## Acceptance Criteria

- A fresh `dori init` asks which search backend to install.
- DDGS works without an API key and returns a grounded answer with sources.
- Tavily uses `TAVILY_API_KEY` and returns its native answer with sources.
- Recent-information requests can pass a supported freshness value.
- Users see a direct answer, not a list of search results.
- Both providers abstain when evidence is insufficient.
- Existing user-modified search files are never overwritten or deleted.
- The placeholder search router and news skill are absent from fresh installs.
- The full non-integration test suite passes without network access.

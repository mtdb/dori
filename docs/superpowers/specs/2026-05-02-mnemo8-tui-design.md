# mnemo8 TUI Design

**Date:** 2026-05-02
**Status:** Approved

## Summary

Replace mnemo8's current REPL chat loop with a Textual-based full-screen TUI that looks and feels like Claude Code / OpenCode — clean layout, high-contrast black palette with cyan and orange accents, spinner-while-thinking, and skill execution feedback inline.

---

## Layout

**Option A — fullscreen with fixed header and input bar.**

```
┌─────────────────────────────────────────────┐
│ ◆ Nemo                  llama3.1:8b · 3 sk │  ← NemoHeader
├─────────────────────────────────────────────┤
│                                             │
│  You                                        │
│  Set a reminder for 9am tomorrow            │
│                                             │
│  Nemo                                       │
│  ✓ reminders                                │
│  Done — please double-check the time.      │
│                                             │
│  Nemo                                       │
│  ⠸ thinking…                               │  ← ThinkingWidget (temporary)
│                                             │
├─────────────────────────────────────────────┤
│ ❯ _                                         │  ← PromptLabel + NemoInput
├─────────────────────────────────────────────┤
│ [ctrl+c] exit  [↑↓] history  [/retry] retry │  ← NemoFooter
└─────────────────────────────────────────────┘
```

---

## Color Palette

| Role | Color |
|------|-------|
| Background | `#000000` |
| Default text | `#ffffff` |
| You — speaker label + left border | `#6fc3df` (cyan) |
| Nemo — speaker label + left border | `#f38518` (orange) |
| Skill confirmation line (`✓ skill`) | `#6fc3df` (cyan) |
| Prompt glyph `❯` | `#6fc3df` (cyan) |
| Thinking spinner | `#555555` |
| Footer key hints | cyan + orange alternating |

---

## Widget Tree

```
NemoApp (App)
├── NemoHeader (Static)
├── MessageList (ScrollableContainer)
│   ├── MessageWidget (Static)   ×N   (one per message)
│   └── ThinkingWidget (Static)        (temporary, while model runs)
├── Horizontal
│   ├── PromptLabel (Static)           "❯"
│   └── NemoInput (Input)
└── NemoFooter (Static)
```

All layout and color is defined in a companion `tui.tcss` file — no inline style strings in Python.

---

## Message Rendering

Each `MessageWidget` renders Rich markup:

- **Speaker line:** `[bold #6fc3df]You[/]` or `[bold #f38518]Nemo[/]`
- **Body:** plain white text, or Rich `Markdown` if the response contains markdown
- **Skill confirmation:** `[#6fc3df]✓ {skill_name}[/]` prepended to the body
- **Left border:** applied via Textual CSS (`border-left: tall #6fc3df` / `border-left: tall #f38518`)

### Thinking state

While `ollama.chat()` is running, a `ThinkingWidget` is mounted at the bottom of `MessageList` showing an animated spinner and `thinking…` in grey. When the response arrives the `ThinkingWidget` is removed and a `MessageWidget` is mounted in its place.

`ollama.chat()` is blocking — it runs in a background thread via `asyncio.to_thread()` so the Textual event loop stays responsive.

---

## Input & Keyboard

| Key | Action |
|-----|--------|
| `Enter` | Submit message, clear input |
| `Up` / `Down` | Cycle in-session history (`list[str]` on app) |
| `Ctrl+C` | Exit cleanly |
| `/retry` (typed) | Resubmit last user message, remove last exchange |

`NemoInput` has no visible border — the `❯` glyph acts as the visual anchor. It takes all remaining width in the horizontal container.

---

## Skill Execution

Unchanged from current behaviour — if the model response contains a `{"skill": "name", ...}` JSON block, the skill's Python script is run via `subprocess.run()`. Stdout is appended inline to the same `MessageWidget` that shows the `✓ skill_name` confirmation. Errors are shown in red within the same widget.

---

## Files Changed

| File | Change |
|------|--------|
| `mnemo8/tui.py` | **New** — Textual app, all UI code |
| `mnemo8/tui.tcss` | **New** — Textual CSS (colors, borders, layout) |
| `mnemo8/chat.py` | **Deleted** — replaced by `tui.py` |
| `mnemo8/main.py` | `import start_tui from tui` instead of `start_chat from chat` |
| `pyproject.toml` | Add `textual>=0.52`, remove `prompt_toolkit` |
| `mnemo8/models.py` | Unchanged |
| `mnemo8/loader.py` | Unchanged |
| `mnemo8/commands.py` | Unchanged |

---

## Out of Scope

- Streaming token-by-token output (spinner + full response is sufficient)
- Persistent chat history across sessions
- Sidebar / session list
- Multiple concurrent conversations

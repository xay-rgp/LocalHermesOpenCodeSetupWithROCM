---
name: desktop-data-gui
description: "Build and verify a tkinter GUI that extracts public data."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [tkinter, gui, desktop, testing, verification, x11, data-extraction, sec, usaspending]
    related_skills: [dogfood, systematic-debugging, test-driven-development]
---

# Desktop Data-Searcher GUI: Build & Verify

## When to Use
- Building or extending a **tkinter / desktop GUI app that fetches + extracts data from external public sources** (SEC EDGAR, USAspending, OpenSanctions, or similar) — e.g. a person/company searcher.
- You need to **prove a GUI works**: run its data logic headlessly and/or capture a screenshot of the populated window on X11.
- **Not for:** web apps (use `dogfood`), or pure logic with no UI (use `test-driven-development`).

## Overview
Build a tkinter GUI app that searches one or more external public data sources by name/ID and extracts structured fields (salary, address, spouse, titles, emails, phones) from returned documents — then **prove it works**: logic headlessly and the real GUI visually.

**Core principle:** the app must be verifiable without a human sitting in front of it. A GUI you can't test headlessly is a GUI you can't trust. "Looks right" is not done; a red/green loop plus a screenshot of the populated window is done.

## Architecture (testability first)
1. **Separate the data engine from the GUI.** Plain importable classes/functions (e.g. a `SearchEngine`) do all fetching + extraction with zero GUI dependency. The `App` class is a thin tkinter layer over it. The engine must run with no display.
2. **Thread-safe Tk updates.** Worker threads must not touch widgets directly; route UI updates through a `_schedule(fn)` helper that wraps `root.after(0, fn)` in try/except TclError (the window may close mid-flight and raise).
3. **Add a `--self-test NAME` CLI mode** that runs the full search + extraction and prints structured results with no GUI. This is the tight red/green feedback loop you iterate against.

## Verification workflow (do all three)
1. **Headless logic loop:** `python3 main.py --self-test "Known Person"`. Fast, deterministic, assertable. Iterate until the extraction you care about is *clean*, not just non-empty.
2. **Headless test battery:** a script that `sys.path.insert`s the project dir, `import`s the module, drives the engine **and** `App()` (tk constructs fine without an open display as long as you don't spin `mainloop` forever), and asserts results. Add a **quality gate** — assert extracted values are *clean* (right format/range), not merely *present*.
3. **Visual GUI check:** launch the real app, programmatically set the input fields, call the real search handler, wait via `root.after()`, then screenshot the window and inspect the image (see `references/x11-screenshot.md`).

## Pitfalls
- **Probe regexes from a `.py` file, not `bash -c "..."`.** Inside bash double-quotes, `\$` loses its backslash and becomes the end-anchor `$`, so a regex like `\$[\d,]+` silently matches nothing (a false 0-count). Write the probe to a file. (Full rule: `systematic-debugging`.)
- **SEC proxy compensation is shorthand.** Filings write "$1.0 million", "$2.0" meaning millions. Capture the scale word (million/billion/thousand/M/B/K) and multiply it in; drop symbolic values under ~$1,000 (the "$1" base salary). Otherwise you surface a misleading "$1" next to a real "$10,906,079".
- **SEC EFTS `forms` filter is space-separated:** `forms=DEF 14A` returns hits, `forms=DEF+14A` returns 0. The unfiltered top-100 is dominated by 10-Q/Form 144, so also run a **targeted DEF 14A query** and merge (see `references/external-apis.md`).
- **USAspending `spending_by_award`: filter with `recipient_search_text: ["name"]`, never `recipient_name`.** `recipient_name` is silently ignored (the API admits it in `messages`) and returns a generic top list for any query — fabricated data, worse than a zero result. `time_period` (start ≥ 2007-10-01) is required for correct filtering; the search API only covers awards from 2007-10-01 onward. A zero-result with a clear note is a good outcome, not an error. Details in `references/external-apis.md`.
- **When an API returns the same rows for different queries, read the response `messages`/diagnostic fields before debugging your parsing** — the API often tells you exactly which filters were ignored or which parameter is malformed (USAspending: `filters not used: {'recipient_name'}`).
- **Name captures after a keyword ("spouse", "director") must require 2+ words** (or a single 4+ letter word that is not a stopword) — a 1-word capture grabs sentence-initial function words like "In 2025, the spouse…".
- **X11 screenshot:** capture the specific window with `import -window <winfo_id> png:file.png`. Do NOT use `-window root` (errors), `-window 0` (hangs), or PIL `ImageGrab.grab(xdisplay=...)` (fails) — see `references/x11-screenshot.md`.
- **`repr()` does not disambiguate fullwidth vs ASCII** (e.g. U+FF04 `＄` prints as `$`). When a regex "can't see" a character, print its codepoint (`ord`/`unicodedata`) in the **same** process as the match, or you're comparing two different fetches.

## References
- `references/external-apis.md` — exact SEC EFTS / USAspending / OpenSanctions endpoints, required parameters, retry guidance, and a golden example.
- `references/x11-screenshot.md` — the GUI-screenshot procedure and a table of what fails and why.

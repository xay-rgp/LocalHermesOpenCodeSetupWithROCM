---
name: html-accessibility
description: "Write semantic HTML5 with valid DOM, landmarks, and ARIA."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [html, html5, accessibility, a11y, aria, wcag, semantic-html, responsive]
    related_skills: [testing-qa, debugging-mastery]
---

# HTML Semantics & Accessibility

Authoring valid, semantic HTML5 documents with strict DOM nesting, WCAG 2.2 landmarks, ARIA attributes, accessible forms/tables, keyboard navigation, and responsive structure.

## When to Use

- Building or auditing HTML5 pages, templates, forms, tables, dialogs, tabs, or disclosure widgets
- Fixing DOM nesting violations, broken heading hierarchies, unlabeled controls, or invalid ARIA references
- Implementing keyboard accessibility, skip links, focus management, and responsive layouts
- Don't use for: non-HTML backend code

## Core Discipline

1. **Always include full HTML5 document metadata:**
   - `<!DOCTYPE html>`, `<html lang="en">` (or appropriate BCP-47 tag), `<meta charset="UTF-8">`, `<meta name="viewport" content="width=device-width, initial-scale=1.0">`, and a descriptive `<title>`.
2. **Use native semantic landmarks properly:**
   - Provide a skip-to-main-content link (`<a href="#main-content" class="skip-link">Skip to main content</a>`) as the first focusable element inside `<body>`.
   - Use `<header>`, `<nav aria-label="...">`, a single `<main id="main-content">` (never nested inside `<article>`, `<aside>`, `<footer>`, `<header>`, or `<nav>`), and `<footer>`.
   - When multiple `<nav>` or `<section>`/`<aside>` landmarks exist, distinguish them with `aria-label` or `aria-labelledby`.
3. **Maintain strict heading hierarchy and valid DOM nesting:**
   - Exactly one `<h1>` per page; never skip heading levels (`h1` -> `h2` -> `h3`, never `h1` -> `h3`).
   - Never put block elements (`<div>`, `<p>`, `<section>`, `<ul>`) inside `<p>` or inline elements (`<span>`, `<a>` where phrasing is required, `<label>`).
   - Never nest interactive elements (`<button>` inside `<a>`, `<a>` inside `<button>`, `<form>` inside `<form>`).
   - Never put closing tags on void elements (`<img>`, `<input>`, `<meta>`, `<link>`, `<br>`, `<hr>`).
   - Every `id` must be non-empty and strictly unique across the document.
4. **Verify ARIA syntax and IDREF integrity:**
   - All ARIA attributes use **hyphens**, never colons (`aria-label`, `aria-labelledby`, `aria-describedby`, `aria-controls`, `aria-expanded`, `aria-selected`, `aria-live`, `aria-invalid`, `aria-current`) — typos like `aria:label` are silently ignored by browsers and screen readers.
   - Every ID referenced by `<label for="...">`, `aria-labelledby`, `aria-describedby`, `aria-controls`, or `aria-owns` MUST match an existing unique `id` in the document.
   - Prefer native HTML elements (`<button>`, `<a href>`, `<dialog>`, `<details>/<summary>`) over ARIA roles on `<div>`/`<span>`.
5. **Accessible forms, tables, media, and keyboard focus:**
   - Group related inputs with `<fieldset>` and `<legend>`. Associate EVERY input, `<select>`, and `<textarea>` with `<label for="...">` (or wrapping `<label>`). Link help/error text via `aria-describedby`.
   - Give every `<table>` a `<caption>`, `<thead>`, `<tbody>`, and explicit `<th scope="col">` / `<th scope="row">`.
   - Give every `<img>` an `alt` attribute (descriptive text for informative images; `alt=""` for purely decorative images).
   - Never use positive `tabindex` (`tabindex="1"` breaks natural tab order; use only `0` or `-1`).
   - Always define visible `:focus-visible` styles and responsive `@media` layout rules.

## Common Pitfalls

- **Attribute & role typos:** Always verify valid ARIA attribute names (`aria-label`, `aria-labelledby`, `aria-describedby`, `aria-controls`, `aria-live="polite"`) and valid roles (`tablist`, `tab`, `tabpanel`, `status`, `alert`) using the Python check below right after `write_file`.
- **Backticks in `write_file` paths:** Pass plain paths like `page.html`, NEVER `` `./page.html` `` with backticks.
- **Unclosed tags or stray closing tags:** Check tag nesting carefully, especially inside nested `<section>`, `<table>`, `<dialog>`, and `<form>` blocks.
- **Orphaned or duplicate IDs:** Renaming an input's `id` without updating `<label for>`, `aria-describedby`, `aria-labelledby`, or `aria-controls` silently breaks screen reader association.
- **Missing button/link accessible names:** Icon-only `<button>` or `<a>` must have `aria-label` (or visually hidden text) and decorative SVG icons should carry `aria-hidden="true"`.

## Verification

- Right after `write_file`, run this fast 1-line check via `terminal` (replace `FILE.html`) and `patch` any printed error before replying:
  ```bash
  python3 -c 'import re,sys; from html.parser import HTMLParser
  s=open(sys.argv[1]).read(); v={"meta","link","input","img","br","hr","source","area","base","col","embed","param","track","wbr"}; st=[]; ids=[]; refs=[]
  class P(HTMLParser):
   def handle_starttag(self,t,a):
    d=dict(a)
    if t not in v: st.append((t,self.getpos()[0]))
    if "id" in d: ids.append(d["id"])
    for k in ("for","aria-labelledby","aria-describedby","aria-controls"):
     if k in d: refs.extend(d[k].split())
    for k,_ in a:
     if k.startswith("ariaaria") or ":" in k: print("BAD_ATTR",k,self.getpos())
   def handle_endtag(self,t):
    if t in v: return
    if not st or st[-1][0]!=t: print("TAG_MISMATCH",t,self.getpos(),st[-1] if st else None)
    else: st.pop()
  P().feed(s); print("UNCLOSED",st,"DUP_IDS",[x for x in set(ids) if ids.count(x)>1],"BAD_REFS",[r for r in refs if r not in set(ids)])' FILE.html
  ```

## Course 3 Senior HTML Table Accessibility Pitfall (Verified)
- **`<td headers="...">` MUST reference `<th id="...">` (never `<col id="...">`):** `<col>` elements inside `<colgroup>` are formatting-only; always put the column `id`s (`id="col-basic"`, etc.) on the `<th scope="col">` elements in `<thead>`, and double-check every `headers="row-x col-y"` token matches an actual `<th id="...">`.
- **WCAG 2.2 SC 2.5.8 Target Size:** Always include `min-width: 24px; min-height: 24px;` on interactive controls (`a, button`).

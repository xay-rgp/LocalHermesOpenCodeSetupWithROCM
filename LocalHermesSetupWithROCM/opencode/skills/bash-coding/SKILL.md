---
name: bash-coding
description: "Write strict Bash scripts with safe quoting and pipes."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [bash, shell, scripting, posix, pipes, quoting, automation]
    related_skills: [debugging-mastery, testing-qa, polyglot-programming]
---

# Bash Coding

Strict, injection-safe Bash scripting covering `set -euo pipefail`, quoting, NUL-delimited file traversal, exit-code handling, pipelines, and process automation.

## When to Use

- Writing, refactoring, or debugging Bash scripts (`.sh`) and shell automation pipelines
- Handling filenames with spaces, quotes, globs (`*`, `?`, `[]`), newlines, or leading hyphens (`-`)
- Diagnosing subtle `set -euo pipefail` failures, subshell variable-loss bugs, or pipeline exit codes
- Don't use for: complex JSON/binary parsing better suited to Python or Rust

## Core Discipline

1. **Always start with strict mode:**
   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   ```
2. **Validate `$#` before dereferencing `$1`, `$2`, ...** Under `set -u` (`nounset`), assigning `ARG="$1"` before checking `if [[ $# -ne 1 ]]` crashes with `$1: unbound variable` instead of printing your usage error. Use `${1:-}` when inspecting optional parameters.
3. **Never parse `ls` output or split `find` on newlines.** Traverse arbitrary filenames with NUL delimiters and process substitution (avoids subshell variable loss):
   ```bash
   count=0
   while IFS= read -r -d '' file; do
     ((count += 1))
   done < <(find "$dir" -type f -name '*.log' -print0)
   ```
   Do **not** pipe `find -print0` into default `awk` without NUL record separation (default `RS` is `\n`, so all NUL-separated paths collapse into 1 record!).
4. **Guard `set -e` traps explicitly:**
   - `((count++))` returns exit code 1 when `count` starts at `0`! Use `((count += 1))` or `count=$((count + 1))`.
   - `grep` / `grep -c` exits `1` when 0 lines match. Guard with `|| true` or count via `awk 'length($0) > 0 { n++ } END { print n + 0 }'`.
   - With `-exec grep -c ... {} \;`, `grep` prints only `<count>` (no `filename:` prefix!), whereas multiple files print `filename:<count>` (which also breaks on colons in filenames). Prefer per-file processing inside a `while IFS= read -r -d '' file` loop.
5. **Quote every expansion and terminate options with `--`:**
   - Always write `"$var"`, `"$@"`, `"${arr[@]}"`. Never use unquoted `$@` or legacy backticks (use `$(...)`).
   - Pass `--` before user/file paths in commands (`rm -f -- "$f"`, `mv -- "$src" "$dst"`, `grep -E -- "$pat" "$f"`).
   - Always use `read -r` so backslashes are not stripped.
   - Never use `eval` on untrusted data.
6. **Handle cleanup and temporary files safely:** Use `mktemp` / `mktemp -d` with a **global** variable (`TMPFILE=""`) and register `trap 'rm -rf -- "${TMPFILE:-}"' EXIT` so cleanup still works after a function returns. For atomic file updates, create the temp file in the same directory (`mktemp -- "$(dirname -- "$file")/.tmp.XXXXXX"`) and commit with `mv -f -- "$TMPFILE" "$file"`.
7. **Prefer pure-Bash literal prefix matching over regex `grep` for keys:** `grep "^${key}="` treats `.` in keys as a regex wildcard and `grep -v` exits `1` when deleting the last line under `set -e`. Use `while IFS= read -r line || [[ -n "$line" ]]; do` with `[[ "$line" == "${key}="* ]]` (and `${line#*=}` for the value) for exact literal matching.
8. **Always run real edge-case tests before claiming success:** Test with `bash -n <script>` plus temporary fixtures containing spaces, quotes, `*`, leading `-`, empty dirs, files without trailing newlines, and invalid CLI args.

## Common Pitfalls

- **Accessing `$1` before checking `$#`:** Crashes under `set -u` with an ugly bash error instead of controlled stderr output.
- **Pipe into `while read` loses variables:** `find ... | while read ...; do count=$((count+1)); done` runs `while` in a subshell; `count` stays 0 outside! Use `< <(find ...)` process substitution.
- **Forgetting last line without trailing newline:** `while IFS= read -r line` stops on EOF if the last line lacks `\n`! Use `while IFS= read -r line || [[ -n "$line" ]]; do ... done`. Also avoid `wc -l` when counting non-empty lines or lines without a trailing newline — `wc -l` counts `\n` characters only (so it counts blank lines AND misses an unterminated final line). Use `awk 'length($0) > 0 { n++ } END { print n + 0 }' -- "$file"` (or `NR > 1 && length($0) > 0` to skip a header row).
- **`xargs -0 printf '.'` excess-argument bug:** `printf '.' f1 f2 f3` ignores extra arguments and prints only ONE dot! Count files directly inside `while IFS= read -r -d '' file; do ((files += 1)); ... done < <(find ...)`.
- **`((i++))` under `set -e`:** When `i=0`, post-increment evaluates to `0` (falsy -> exit status 1) and kills the script silently! ALWAYS write `((++i))` or `i=$((i + 1))` — NEVER `((i++))`.
- **Trimming whitespace cleanly without `sed` regex typos:** For single-token lines, `read -r var <<< "$line"` trims leading/trailing whitespace cleanly; for arbitrary strings, use pure-Bash parameter expansion (`s="${s#"${s%%[![:space:]]*}"}"` and `s="${s%"${s##*[![:space:]]}"}"`) instead of `echo | sed`.
- **Single-bracket `[ $var = foo ]` word splitting:** Prefer `[[ "$var" == "foo" ]]` in Bash and always quote variables.
- **Signal-responsive sleeps & portable math:** Foreground `sleep` blocks `SIGTERM`/`SIGINT` trap delivery until it finishes; run `sleep "$secs" & CHILD_PID=$!; wait "$CHILD_PID"` and kill `"$CHILD_PID"` in your `EXIT` trap (with `trap 'exit 143' TERM` and `trap 'exit 130' INT`). Never write bare `kill $(jobs -p)` inside an `EXIT` trap under `set -e` — when `jobs -p` is empty, `kill` exits `2`, aborts cleanup, and overwrites the script's exit code! Guard with `pids=$(jobs -p); [[ -n "$pids" ]] && kill $pids 2>/dev/null || true`. Use `awk -v ms="$HOLD_MS" 'BEGIN { printf "%.3f", ms / 1000 }'` instead of `bc` (which may not be installed).

## Verification

- Run `bash -n <script.sh>` for syntax validation AND a 1-line runtime smoke test (e.g., creating/reading/deleting a key in a temp file and removing it) — `bash -n` alone does NOT catch misspelled commands or runtime exit codes!
- Execute the script against edge-case fixtures (spaces, globs, leading `-`, empty directories, missing trailing newline, bad arg counts) and inspect exact stdout, stderr, and exit codes.
- **Check `$#` BEFORE Reading `$1`/`$2` Under `set -u`:** Never assign `ARG1="$1"` before validating `if [[ $# -ne N ]]; then ... exit 2; fi`; with `set -u`, referencing `$1` with 0 arguments aborts with exit code 1 (`unbound variable`) instead of your usage error exit code 2.

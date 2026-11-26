# External Public-Data APIs (exact specs)

Verified endpoints and the non-obvious parameters that make them work.

## SEC EDGAR full-text search (EFTS)
- Base: `https://efts.sec.gov/LATEST/search-index?q="Name"&forms=DEF 14A&size=100`
  - **`forms` is space-separated:** `forms=DEF 14A` works; `forms=DEF+14A` returns 0 hits.
  - `size` caps hits returned (100 is fine).
  - An unfiltered top-100 is dominated by 10-Q / Form 144; DEF 14A is only a small fraction.
- **Recommended strategy:** run a **targeted DEF 14A query** (`size` ~20) AND an unfiltered query (`size` ~100), merge, then tier-sort: `14A → 10-K → other`, date-desc within tier. Cap the displayed list (e.g. 60) to keep the GUI responsive. A 45s deadline across the two queries prevents indefinite hangs.
- **Filing docs:** `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/index.json` → read `directory.item[]` → pick the `.htm`/`.html` (or `.txt`) doc → fetch it from the same directory.
- **Filing URL:** `https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}`
- **Retry:** SEC intermittently returns 500s. Retry with backoff (e.g. 4 attempts, ~1.2s × n) on 5xx / 429. Reducing query count lowers the failure surface.

## USAspending
- Endpoint: `POST https://api.usaspending.gov/api/v2/search/spending_by_award/`
- **Recipient filter: `filters.recipient_search_text: ["Name"]`** (a list, ≤ 1 item). The query must be a substring of the recipient name — full names rarely match, so try full name first, then fall back to the surname. **Do NOT use `recipient_name`**: it is silently ignored (the response `messages` says `filters not used: {'recipient_name'}`) and the endpoint returns a generic top list for ANY query — fabricated data, worse than a zero result.
- Payload requirements (each has a distinct failure mode):
  - `fields`: non-empty list; the `sort` value must be **in** `fields` (400 `Sort value 'X' not found in requested fields`). Valid awards-level sort values include `Award ID`, `Recipient Name`, `Award Amount`, `Start Date`, `End Date`.
  - `filters.award_type_codes`: required (422). This endpoint is contracts-only: `A/B/C/D` + `IDV_*` — mixing in grant codes (`K`, `L`, `N`…) → 400 `outside valid values`.
  - `time_period`: `[{"start_date":...,"end_date":...}]`, start ≥ 2007-10-01 (422 `start_date cannot be earlier than '2007-10-01'`). Search-API coverage starts 2007-10-01; older data is in the download/bulk APIs — say so in the note when a valid name returns 0.
  - `spending_level`: `"awards"` | `"subawards"` (422 otherwise). Sub-award responses use different field names (`Sub-Awardee Name`, `Sub-Award ID`, …).
- **Dates:** request `"Start Date"` / `"End Date"` — they carry values; `"Action Date"` is frequently null.
- **Recipient autocomplete (resolve exact names):** `POST https://api.usaspending.gov/api/v2/autocomplete/recipient/` with `{"search_text": "..."}` → `results[].recipient_name`. GET → 405; the field is `search_text`, not `search`. Useful for sanity-checking which recipients exist before blaming the search query.
- Zero results for a valid name is normal (the recipient may only have pre-2007 awards): return "OK with a note", not an error.

## OpenSanctions
- Requires a free API key (`OPENSANCTIONS_API_KEY` env), sent as `Authorization: ApiKey <key>`.
- Matching: `POST https://api.opensanctions.org/match/default` with `{"queries": {"q": <name string or Person schema object with firstName/lastName>}}`. 401 = key invalid/expired → friendly "refresh your key" note, not a crash.
- Without a key, endpoints return 404/empty — surface a friendly note ("no API key set"), not an error.

## Golden example
Search "Satya Nadella" → SEC returns ~10,000; the top DEF 14A is MICROSOFT CORP; extracting his proxy yields clean comp values (base ~$1M, total ~$25M) **after** scale-word normalization. A common name ("John Smith") should still return SEC results and not crash.

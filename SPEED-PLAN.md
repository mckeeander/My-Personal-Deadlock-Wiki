# Loading speed plan

Measured on 2026-11-12. Biggest wins first. Each step can be shipped and checked on its own.

## What happens on every open today

1. The service worker fetches `index.html` from the network first (490 KB, 150 KB gzipped) before anything shows, even when a saved copy exists.
2. The app shows the copy saved in the browser (IndexedDB), then **re-downloads every data file**: `fetch(... "?t=" + Date.now(), { cache: "no-store" })`, so nothing is ever cached by the browser.
   - `items.json` 4.97 MB (418 KB gz), `heroes.json` 0.78 MB, `patchhistory.json` 0.79 MB, `wiki.json` 0.18 MB, `patchnotes.json` 0.14 MB, plus the small ones. About **7 MB to parse, ~700 KB over the wire, every open**, though the data changes about once a day.
3. `dataSig()` runs `JSON.stringify` over heroes + items (~5.7 MB) on every load to decide whether anything changed. That alone is likely hundreds of ms on a phone.
4. Each refresh then re-saves everything to IndexedDB.

## Step 1: Only download data when it changed (DONE)

Correction to the notes above: the app already skipped downloads when its saved copy was under 24 hours old, so it didn't re-download on every open. It did re-download everything once a day even when nothing changed, and could show data up to a day late. Now every open checks `updated.txt` and downloads only when it changed.


- Fetch the tiny `data/updated.txt` (already exists; `getStamp()`) first.
- If it matches the stamp saved with the IndexedDB copy, **skip every data download** and skip `dataSig()`.
- If it differs, download as today. Keep the `?t=` cache-buster only for `updated.txt`; data files can use `?v=<stamp>` so the browser can cache each version.
- Expected: most opens go from ~700 KB + 7 MB of parsing to a ~30-byte request.
- Check: open twice. The second open makes one small request and no data parsing.

## Step 2: Show the saved page first, update in the background

- Service worker: switch the app shell (`index.html` etc.) from network-first to **stale-while-revalidate**. Serve the saved copy instantly, then fetch the new one for next time.
- Bump the cache name (`codex-shell-v4`) so the change takes effect.
- Trade-off: a code update appears on the *second* open after it ships, not the first. Fine for a personal app; a small "updated, reload" hint is optional.
- Check: in airplane mode and online, the page paints with no wait.

## Step 3: Make items.json much smaller

- `properties` is 3.0 MB of the 5 MB (`description` 0.68 MB, `tooltip_details` 0.59 MB).
- `tools/trim.py` already exists. Extend it to keep only the property fields the app reads (`value`, `label`, `postfix`, `css_class`, `icon`, scaling info) and drop the rest. Have the daily job run it after downloading.
- Before trimming, search `index.html` for every property field used, so nothing visible breaks. Then run `tools/check.py` (the daily safety check) and compare a few hero and item pages before and after.
- Expected: items.json likely drops to about a third. Faster download, parse and IndexedDB save.

## Step 4: Cheaper work after load

- Replace `dataSig()` with the stamp from step 1. If kept, hash only lengths and ids.
- `heroTags()` builds a big regular expression on every call. Build it once per data load.
- Patch history (0.79 MB) is only needed when Patch history is opened on a hero or item page. Load it lazily on first open instead of at startup.
- Same for `wiki.json` notes, if they're only shown inside ability cards that are folded.

## Step 5 (optional, later): Split the page file

- `index.html` is one 4,900-line file holding the CSS, the code and the glossary text. Moving the code and CSS into separate files lets the browser cache them separately, and lets the page start drawing sooner.
- Only worth it once steps 1–4 are done. Biggest effort, smallest gain after them.

## How to measure (before and after each step)

- Playwright with a throttled phone profile (CPU 4× slower, "Fast 3G"). Record time to first hero list, time to a hero page, and bytes downloaded, on a first visit and on a repeat visit.
- Run `tools/check.py` after each step: it opens every hero and item and catches anything broken.

## Order to implement

Step 1 → measure → Step 2 → measure → Step 3 (needs the daily job; run it once by hand) → Step 4 → decide on Step 5.

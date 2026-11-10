# My-Personal-Deadlock-Wiki
This site is a personal study reference for Deadlock heroes, abilities and items. It is not affiliated with or endorsed by Valve.

## Credits

- Deadlock is a trademark of Valve Corporation. Game data and art belong to Valve.
- Hero, ability and item data come from the game files via the [Deadlock API](https://deadlock-api.com).
- Ability notes, interactions and some glossary definitions are adapted from the [Deadlock Wiki](https://deadlock.wiki) and its contributors, used under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). This content (including `data/wiki.json`) is shared under the same license.

## How the data updates

A GitHub Action (`.github/workflows/update-data.yml`) runs once a day:

1. Downloads hero and item data from the Deadlock API, records what changed (`tools/revisions.py`) and trims fields the site never reads (`tools/trim.py`).
2. Pulls patch notes and powerups from the wiki's data repo (`tools/wikidata.py`) and popular items from match statistics (`tools/popular.py`).
3. **Safety net:** `tools/check.py` opens the site in a headless browser on the new data and checks that every hero page, item, shop tab, the glossary and search still work.
4. If the download or the check fails, every data file goes back to the previous day's copy, `data/status.json` records why, the site shows a notice, and the run is marked failed (GitHub emails you).

`tools/wiki_notes.py` and `tools/wiki_pages.py` fetched ability notes from deadlock.wiki; they are switched off because the wiki blocks automated requests since Nov 3, 2026.

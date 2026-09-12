# DeckGrabber

DeckGrabber is a small Python utility for turning a Magic: The Gathering deck into a formatted JSON payload by fetching card metadata from Scryfall.

It supports:

- Decks stored as a plain text list of `count name` lines
- Archidekt deck URLs (using the public deck page payload)
- Batched Scryfall collection lookups with fallback individual lookups
- Generated output JSON that includes card metadata such as mana cost, type line, oracle text, power, toughness, colors, and creature subtypes

## Project layout

- `run.py` - entry point
- `src/main.py` - core deck loading, Archidekt parsing, Scryfall fetching, and JSON generation
- `data/deck.txt` - input deck source
- `output/formatted_deck.json` - generated output
- `logs/debug_log.jsonl` - debug and error logging

## Input formats

### 1. Archidekt URL

Put a public Archidekt deck URL in `data/deck.txt`, for example:

```text
https://archidekt.com/decks/26337976/dorves
```

The app will detect the deck ID from the URL and load the public deck page’s embedded JSON payload.

### 2. Plain deck list

You can also provide a regular deck list in `data/deck.txt`, one card per line:

```text
4 Island
4 Mountain
2 Snap
```

Each line must be:

```text
<count> <card name>
```

## Running the app

From the project root:

```bash
python run.py
```

This will:

1. Load the deck from `data/deck.txt`
2. Query Scryfall for card data
3. Write the formatted result to `output/formatted_deck.json`

## Output format

The generated JSON file contains a top-level `source_deck` value and a `cards` array. Each card item includes fields such as:

- `count`
- `name`
- `mana_cost`
- `cmc`
- `type_line`
- `creature_types`
- `oracle_text`
- `power`
- `toughness`
- `colors`

## Environment variables

You can override defaults with environment variables:

- `SCRYFALL_API_BASE_URL` - defaults to `https://api.scryfall.com`
- `ARCHIDEKT_DECK_URL` - optional direct Archidekt deck URL override

## Notes

- The app writes debug events to `logs/debug_log.jsonl` for troubleshooting.
- The generated `output/formatted_deck.json` file is intended to be a build artifact and is excluded from source control in the project ignore rules.

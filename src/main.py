from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
import json
import os
import re
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
DECK_FILE = ROOT / "data" / "deck.txt"
OUTPUT_FILE = ROOT / "output" / "formatted_deck.json"
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "debug_log.jsonl"
SCRYFALL_API_BASE_URL = os.environ.get("SCRYFALL_API_BASE_URL", "https://api.scryfall.com")
ARCHIDEKT_API_BASE_URL = "https://archidekt.com/api/decks"
ARCHIDEKT_DECK_URL = os.environ.get("ARCHIDEKT_DECK_URL")


def write_debug_log(event, **details):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
    }
    entry.update(details)
    with LOG_FILE.open("a", encoding="utf-8") as log_handle:
        log_handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def fetch_json(url, method="GET", data=None):
    last_error = None

    request = Request(
        url,
        data=data,
        headers={
            "User-Agent": "ScryfallGrab/1.0",
            "Accept": "*/*",
            "Content-Type": "application/json",
        },
        method=method,
    )

    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        last_error = error
        write_debug_log(
            "scryfall_request_failed",
            url=url,
            method=method,
            error_type=type(error).__name__,
            error_message=str(error),
            error_code=getattr(error, "code", None),
            error_reason=getattr(error, "reason", None),
            payload=data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data,
        )
    except Exception as error:
        last_error = error
        write_debug_log(
            "scryfall_request_failed",
            url=url,
            method=method,
            error_type=type(error).__name__,
            error_message=str(error),
            error_code=getattr(error, "code", None),
            error_reason=getattr(error, "reason", None),
            payload=data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data,
        )

    raise last_error


def fetch_card_by_name(card_name):
    encoded_name = quote(card_name, safe="")
    request = Request(
        f"{SCRYFALL_API_BASE_URL}/cards/named?fuzzy={encoded_name}&format=json",
        headers={
            "User-Agent": "ScryfallGrab/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except Exception as error:
        write_debug_log(
            "card_lookup_failed",
            card_name=card_name,
            url=request.full_url,
            error_type=type(error).__name__,
            error_message=str(error),
            error_code=getattr(error, "code", None),
            error_reason=getattr(error, "reason", None),
        )
        raise


def extract_archidekt_deck_id(source):
    if not source:
        return None

    stripped = source.strip()

    if stripped.isdigit():
        return stripped

    match = re.search(r"archidekt\.com(?:/api/decks)?/decks/(\d+)", stripped)
    if match:
        return match.group(1)

    match = re.search(r"archidekt\.com/api/decks/(\d+)", stripped)
    if match:
        return match.group(1)

    return None


def fetch_archidekt_deck(deck_id_or_url):
    deck_id = extract_archidekt_deck_id(deck_id_or_url)
    if not deck_id:
        raise ValueError(
            "Unable to determine an Archidekt deck ID from the provided source. "
            "Use a deck URL or numeric deck ID."
        )

    page_url = deck_id_or_url
    if not page_url.startswith("http://") and not page_url.startswith("https://"):
        page_url = f"https://archidekt.com/decks/{deck_id}/crimes"
    elif "/decks/" not in page_url:
        page_url = f"https://archidekt.com/decks/{deck_id}/crimes"

    request = Request(
        page_url,
        headers={
            "User-Agent": "ScryfallGrab/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
        method="GET",
    )

    with urlopen(request, timeout=30) as response:
        raw_html = response.read().decode("utf-8", errors="ignore")

    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*)</script>',
        raw_html,
        re.S,
    )
    if not match:
        raise ValueError(
            f"Archidekt deck {deck_id} did not include the expected embedded JSON payload."
        )

    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Archidekt deck {deck_id} returned malformed embedded JSON: {error}"
        ) from error

    deck = payload.get("props", {}).get("pageProps", {}).get("redux", {}).get("deck", {})
    card_map = deck.get("cardMap") or {}
    excluded_categories = {"Maybeboard", "Sideboard"}

    deck_cards = []
    for card_entry in card_map.values():
        if not isinstance(card_entry, dict):
            continue

        categories = set(card_entry.get("categories") or [])
        if categories.intersection(excluded_categories):
            continue

        card_name = (card_entry.get("name") or "").strip()
        if not card_name:
            continue

        quantity = int(card_entry.get("qty") or card_entry.get("quantity") or 1)
        deck_cards.append({"count": quantity, "name": card_name})

    if not deck_cards:
        raise ValueError(
            f"Archidekt deck {deck_id} did not return any usable mainboard/commander cards."
        )

    return deck_cards


def parse_deck(file_path):
    cards = []

    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(None, 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid deck list line: {raw_line!r}")

        count = int(parts[0])
        name = parts[1].strip()

        cards.append({"count": count, "name": name})

    return cards


def load_deck_cards():
    if ARCHIDEKT_DECK_URL:
        return fetch_archidekt_deck(ARCHIDEKT_DECK_URL)

    content = DECK_FILE.read_text(encoding="utf-8").strip()
    if content and extract_archidekt_deck_id(content):
        return fetch_archidekt_deck(content)

    return parse_deck(DECK_FILE)


def fetch_collection_cards(deck_cards):
    card_lookup = {}
    batch_size = 75
    total_cards = len(deck_cards)

    print(f"Preparing batched collection requests for {total_cards} cards")

    for start in range(0, total_cards, batch_size):
        batch = deck_cards[start : start + batch_size]
        batch_names = [entry["name"] for entry in batch]
        payload = {"identifiers": [{"name": name} for name in batch_names]}

        print(
            f"[Batch {start // batch_size + 1}] Posting {len(batch_names)} identifiers to /cards/collection"
        )

        try:
            response = fetch_json(
                f"{SCRYFALL_API_BASE_URL}/cards/collection",
                method="POST",
                data=json.dumps(payload).encode("utf-8"),
            )
        except Exception as error:
            write_debug_log(
                "batch_request_failed",
                batch_index=start // batch_size + 1,
                batch_start=start,
                batch_size=len(batch),
                card_names=batch_names,
                error_type=type(error).__name__,
                error_message=str(error),
                error_code=getattr(error, "code", None),
                error_reason=getattr(error, "reason", None),
            )
            print(f"  -> Batch request failed: {error}")
            print("  -> Falling back to individual card lookups")
            for entry in batch:
                try:
                    card_lookup[entry["name"]] = fetch_card_by_name(entry["name"])
                except Exception as lookup_error:
                    card_lookup[entry["name"]] = {
                        "error": f"Unable to fetch card data from Scryfall: {lookup_error}"
                    }
                    write_debug_log(
                        "fallback_card_lookup_failed",
                        card_name=entry["name"],
                        error_type=type(lookup_error).__name__,
                        error_message=str(lookup_error),
                        error_code=getattr(lookup_error, "code", None),
                        error_reason=getattr(lookup_error, "reason", None),
                    )
            break

        for card in response.get("data", []):
            card_lookup[card["name"]] = card

        not_found = response.get("not_found", [])
        for missing in not_found:
            card_name = missing.get("name") or missing.get("id") or "unknown"
            try:
                card_lookup[card_name] = fetch_card_by_name(card_name)
            except Exception as lookup_error:
                card_lookup[card_name] = {
                    "error": f"Unable to fetch card data from Scryfall: {lookup_error}"
                }
                write_debug_log(
                    "fallback_card_lookup_failed",
                    card_name=card_name,
                    error_type=type(lookup_error).__name__,
                    error_message=str(lookup_error),
                    error_code=getattr(lookup_error, "code", None),
                    error_reason=getattr(lookup_error, "reason", None),
                )
            else:
                write_debug_log(
                    "card_not_found_in_collection_response_recovered",
                    card_name=card_name,
                    missing_record=missing,
                )

        if start + batch_size < total_cards:
            print("  -> Waiting 0.5 seconds before next collection request")
            time.sleep(0.5)

    return card_lookup


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    deck_cards = load_deck_cards()
    formatted_cards = []

    print(f"Starting deck processing for {len(deck_cards)} cards from {DECK_FILE.name}")
    card_lookup = fetch_collection_cards(deck_cards)

    print("Building output JSON...")
    for index, deck_entry in enumerate(deck_cards, start=1):
        card_data = card_lookup.get(
            deck_entry["name"],
            {"error": f"Missing card data from Scryfall collection response for {deck_entry['name']}"},
        )

        card_entry_output = {
            "count": deck_entry["count"],
            "name": deck_entry["name"],
            "mana_cost": None,
            "cmc": None,
            "type_line": None,
            "creature_types": [],
            "oracle_text": None,
            "power": None,
            "toughness": None,
            "colors": [],
        }

        if isinstance(card_data, dict) and "error" not in card_data:
            creature_types = card_data.get("subtypes") or []
            if not creature_types and isinstance(card_data.get("type_line"), str):
                type_line = card_data["type_line"]
                if "Creature" in type_line and "—" in type_line:
                    creature_types = [
                        part.strip()
                        for part in type_line.split("—", 1)[1].split()
                        if part.strip()
                    ]

            card_entry_output.update(
                {
                    "mana_cost": card_data.get("mana_cost"),
                    "cmc": card_data.get("cmc"),
                    "type_line": card_data.get("type_line"),
                    "creature_types": creature_types,
                    "oracle_text": card_data.get("oracle_text"),
                    "power": card_data.get("power"),
                    "toughness": card_data.get("toughness"),
                    "colors": card_data.get("colors", []),
                }
            )
            print(f"[{index}/{len(deck_cards)}] Success for {deck_entry['name']}")
        else:
            print(f"[{index}/{len(deck_cards)}] Error for {deck_entry['name']}: {card_data.get('error', 'unknown error')}")

        formatted_cards.append(card_entry_output)

    result = {
        "source_deck": DECK_FILE.name,
        "cards": formatted_cards,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Wrote {len(formatted_cards)} card entries to {OUTPUT_FILE.name}")

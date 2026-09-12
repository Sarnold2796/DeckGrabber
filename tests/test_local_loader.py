import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import main


class LoadDeckCardsTests(unittest.TestCase):
    def test_prefers_local_archidekt_url_over_environment_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            deck_file = Path(temp_dir) / "deck.txt"
            deck_file.write_text("https://archidekt.com/decks/26337976/dorves\n", encoding="utf-8")

            with mock.patch.object(main, "DECK_FILE", deck_file), mock.patch.object(
                main,
                "ARCHIDEKT_DECK_URL",
                "https://archidekt.com/decks/99999/marchesa",
            ), mock.patch.object(main, "fetch_archidekt_deck", return_value=[{"count": 1, "name": "Dorves"}]) as fetch_mock:
                cards = main.load_deck_cards()

            self.assertEqual(cards, [{"count": 1, "name": "Dorves"}])
            fetch_mock.assert_called_once_with("https://archidekt.com/decks/26337976/dorves")

    def test_parses_plain_local_deck_list(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            deck_file = Path(temp_dir) / "deck.txt"
            deck_file.write_text("4 Island\n2 Mountain\n", encoding="utf-8")

            with mock.patch.object(main, "DECK_FILE", deck_file):
                cards = main.load_deck_cards()

            self.assertEqual(
                cards,
                [
                    {"count": 4, "name": "Island"},
                    {"count": 2, "name": "Mountain"},
                ],
            )


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from core import store


def _sample_match(match_id: str, puuid: str) -> dict:
    return {
        "metadata": {
            "matchid": match_id,
            "game_start_patched": "2024-01-01",
            "map": "Ascent",
            "mode": "Unrated",
        },
        "players": {
            "all_players": [
                {
                    "puuid": puuid,
                    "team": "red",
                    "stats": {"kills": 10, "deaths": 8, "assists": 5},
                }
            ]
        },
        "teams": {
            "red": {"has_won": True, "rounds_won": 13},
            "blue": {"has_won": False, "rounds_won": 5},
        },
    }


class StoreMatchBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._original_db_file = store.DB_FILE
        store.DB_FILE = Path(self._tmpdir.name) / "bot.sqlite3"
        store._ensure_schema()

    def tearDown(self) -> None:
        store.DB_FILE = self._original_db_file

    def test_counts_only_new_rows(self) -> None:
        owner_key = "alias:test"
        puuid = "test-puuid"
        match = _sample_match("match-1", puuid)

        inserted = store.store_match_batch(owner_key, puuid, [match])
        self.assertEqual(inserted, 1)

        repeated = store.store_match_batch(owner_key, puuid, [match])
        self.assertEqual(repeated, 0)

    def test_handles_nested_metadata_labels(self) -> None:
        owner_key = "alias:test"
        puuid = "test-puuid"
        match = _sample_match("match-2", puuid)
        match["metadata"]["map"] = {
            "name": "Sunset",
            "localized": {"ko-KR": "선셋"},
        }
        match["metadata"]["mode"] = {
            "localized": {"en-US": "Swiftplay"},
        }

        inserted = store.store_match_batch(owner_key, puuid, [match])
        self.assertEqual(inserted, 1)

        latest = store.latest_match(owner_key)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["map"], "Sunset")
        self.assertEqual(latest["mode"], "Swiftplay")

    def test_infers_result_from_team_metadata(self) -> None:
        owner_key = "alias:test"
        puuid = "test-puuid"
        match = _sample_match("match-3", puuid)
        match["players"]["all_players"][0]["team"] = "BLUE"
        match["teams"] = {
            "blue": {"has_won": "TRUE", "rounds_won": 13, "rounds_lost": 7},
            "red": {"has_won": "FALSE", "rounds_won": 7, "rounds_lost": 13},
        }

        inserted = store.store_match_batch(owner_key, puuid, [match])
        self.assertEqual(inserted, 1)

        latest = store.latest_match(owner_key)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["result"], "win")


if __name__ == "__main__":
    unittest.main()

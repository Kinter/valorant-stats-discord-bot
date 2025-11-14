import tempfile
from pathlib import Path
import unittest

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


if __name__ == "__main__":
    unittest.main()

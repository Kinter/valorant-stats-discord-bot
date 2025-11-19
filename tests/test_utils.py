import unittest

from core.utils import team_result


class TeamResultTests(unittest.TestCase):
    def test_handles_sequence_team_structure(self) -> None:
        teams = [
            {"team": "red", "has_won": 0},
            {"team": "blue", "has_won": 1},
        ]

        self.assertIs(team_result(teams, "blue"), True)
        self.assertIs(team_result(teams, "red"), False)


if __name__ == "__main__":
    unittest.main()

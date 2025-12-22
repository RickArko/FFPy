"""
ESPN Fantasy Football League Integration.

This module provides access to ESPN Fantasy Football private league data
including rosters, lineups, standings, and matchups.

Requires authentication cookies (swid and espn_s2) for private leagues.
"""

import requests
import pandas as pd
from typing import Optional, List, Dict, Any
import os
from ffpy.config import Config


class ESPNLeagueIntegration:
    """Access ESPN Fantasy Football private league data."""

    BASE_URL = "https://fantasy.espn.com/apis/v3/games/ffl"

    # Lineup slot mappings
    LINEUP_SLOTS = {
        0: "QB",
        2: "RB",
        4: "WR",
        6: "TE",
        16: "D/ST",
        17: "K",
        20: "BENCH",
        21: "IR",
        23: "FLEX",
        7: "OP",  # Offensive Player (superflex)
    }

    def __init__(
        self, league_id: int, season: int = 2024, swid: Optional[str] = None, espn_s2: Optional[str] = None
    ):
        """
        Initialize ESPN league integration.

        Args:
            league_id: Your ESPN league ID
            season: NFL season year (default: 2024)
            swid: ESPN SWID cookie (for private leagues)
            espn_s2: ESPN S2 cookie (for private leagues)

        Note:
            For public leagues, swid and espn_s2 are not required.
            For private leagues, get these from your browser cookies after logging in.
        """
        self.league_id = league_id
        self.season = season

        # Try to get from environment if not provided
        self.swid = swid or os.getenv("ESPN_SWID", "")
        self.espn_s2 = espn_s2 or os.getenv("ESPN_S2", "")

        # Build cookies dict
        self.cookies = {}
        if self.swid:
            self.cookies["swid"] = self.swid
        if self.espn_s2:
            self.cookies["espn_s2"] = self.espn_s2

    def _make_request(self, params: Dict[str, Any]) -> Dict:
        """
        Make authenticated request to ESPN API.

        Args:
            params: Query parameters

        Returns:
            JSON response as dict

        Raises:
            requests.HTTPError: If request fails
        """
        url = f"{self.BASE_URL}/seasons/{self.season}/segments/0/leagues/{self.league_id}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }

        response = requests.get(url, params=params, headers=headers, cookies=self.cookies, timeout=10)
        response.raise_for_status()

        return response.json()

    def get_league_info(self) -> Dict:
        """
        Get basic league information.

        Returns:
            Dict with league name, size, settings, etc.
        """
        data = self._make_request({"view": "mSettings"})

        settings = data.get("settings", {})

        return {
            "name": data.get("settings", {}).get("name", "Unknown"),
            "size": len(data.get("teams", [])),
            "scoring_type": self._get_scoring_type(settings),
            "roster_slots": self._parse_roster_settings(settings),
            "playoff_teams": settings.get("playoffTeamCount", 0),
            "season": self.season,
        }

    def get_all_teams(self) -> List[Dict]:
        """
        Get all teams in the league.

        Returns:
            List of team dicts with id, name, owner, record
        """
        data = self._make_request({"view": "mTeam"})

        teams = []
        for team_data in data.get("teams", []):
            teams.append(
                {
                    "id": team_data.get("id"),
                    "name": team_data.get("name", "Unknown"),
                    "abbrev": team_data.get("abbrev", ""),
                    "owner": team_data.get("primaryOwner", "Unknown"),
                    "wins": team_data.get("record", {}).get("overall", {}).get("wins", 0),
                    "losses": team_data.get("record", {}).get("overall", {}).get("losses", 0),
                    "ties": team_data.get("record", {}).get("overall", {}).get("ties", 0),
                    "points_for": team_data.get("record", {}).get("overall", {}).get("pointsFor", 0),
                    "points_against": team_data.get("record", {}).get("overall", {}).get("pointsAgainst", 0),
                }
            )

        return teams

    def get_team_roster(self, team_id: int, week: Optional[int] = None) -> pd.DataFrame:
        """
        Get roster for a specific team.

        Args:
            team_id: Team ID (1-based, find using get_all_teams())
            week: Specific week (optional, defaults to current week)

        Returns:
            DataFrame with player info and roster slots
        """
        params = {"view": "mRoster"}
        if week:
            params["scoringPeriodId"] = week

        data = self._make_request(params)

        # Find the team
        team_data = None
        for team in data.get("teams", []):
            if team.get("id") == team_id:
                team_data = team
                break

        if not team_data:
            raise ValueError(f"Team ID {team_id} not found in league")

        # Parse roster
        roster_entries = team_data.get("roster", {}).get("entries", [])

        players = []
        for entry in roster_entries:
            player_data = entry.get("playerPoolEntry", {}).get("player", {})

            player_info = {
                "player_id": player_data.get("id"),
                "player": player_data.get("fullName", "Unknown"),
                "position": self._get_position(player_data.get("defaultPositionId", 0)),
                "team": self._get_team_abbr(player_data.get("proTeamId", 0)),
                "lineup_slot": self.LINEUP_SLOTS.get(entry.get("lineupSlotId", 20), "BENCH"),
                "acquisition_type": entry.get("acquisitionType", ""),
                "injury_status": player_data.get("injuryStatus", "ACTIVE"),
            }

            players.append(player_info)

        return pd.DataFrame(players)

    def get_league_rosters(self, week: Optional[int] = None) -> Dict[int, pd.DataFrame]:
        """
        Get rosters for all teams in the league.

        Args:
            week: Specific week (optional)

        Returns:
            Dict mapping team_id to roster DataFrame
        """
        rosters = {}
        teams = self.get_all_teams()

        for team in teams:
            team_id = team["id"]
            rosters[team_id] = self.get_team_roster(team_id, week)

        return rosters

    def get_standings(self) -> pd.DataFrame:
        """
        Get current league standings.

        Returns:
            DataFrame with team rankings and records
        """
        teams = self.get_all_teams()

        # Sort by wins (descending), then points for
        standings = pd.DataFrame(teams)
        standings = standings.sort_values(["wins", "points_for"], ascending=[False, False])
        standings["rank"] = range(1, len(standings) + 1)

        return standings[["rank", "name", "wins", "losses", "ties", "points_for", "points_against"]]

    def get_matchups(self, week: int) -> List[Dict]:
        """
        Get matchups for a specific week.

        Args:
            week: Week number

        Returns:
            List of matchup dicts
        """
        data = self._make_request({"view": "mMatchup", "scoringPeriodId": week})

        matchups = []
        schedule = data.get("schedule", [])

        for matchup in schedule:
            if matchup.get("matchupPeriodId") == week:
                matchups.append(
                    {
                        "home_team_id": matchup.get("home", {}).get("teamId"),
                        "away_team_id": matchup.get("away", {}).get("teamId"),
                        "home_score": matchup.get("home", {}).get("totalPoints", 0),
                        "away_score": matchup.get("away", {}).get("totalPoints", 0),
                        "winner": matchup.get("winner", "UNDECIDED"),
                    }
                )

        return matchups

    def get_scoring_settings(self) -> Dict:
        """
        Get league scoring settings.

        Returns:
            Dict with scoring configuration
        """
        data = self._make_request({"view": "mSettings"})

        settings = data.get("settings", {})
        scoring = settings.get("scoringSettings", {})

        return {
            "scoring_type": self._get_scoring_type(settings),
            "scoring_items": scoring.get("scoringItems", {}),
        }

    def _get_scoring_type(self, settings: Dict) -> str:
        """Determine scoring type (PPR, Half-PPR, Standard)."""
        scoring = settings.get("scoringSettings", {})

        # Look for reception scoring (stat ID 53)
        for item in scoring.get("scoringItems", []):
            if item.get("statId") == 53:  # Receptions
                points = item.get("points", 0)
                if points == 1.0:
                    return "PPR"
                elif points == 0.5:
                    return "Half-PPR"

        return "Standard"

    def _parse_roster_settings(self, settings: Dict) -> Dict[str, int]:
        """Parse roster position requirements from settings."""
        roster_settings = settings.get("rosterSettings", {})
        lineup_slots = roster_settings.get("lineupSlotCounts", {})

        # Map ESPN slot IDs to position names
        positions = {}
        for slot_id, count in lineup_slots.items():
            slot_id = int(slot_id)
            position = self.LINEUP_SLOTS.get(slot_id, f"SLOT_{slot_id}")

            # Skip bench and IR
            if position not in ["BENCH", "IR"] and count > 0:
                positions[position] = count

        return positions

    def _get_position(self, position_id: int) -> str:
        """Convert ESPN position ID to abbreviation."""
        positions = {
            1: "QB",
            2: "RB",
            3: "WR",
            4: "TE",
            5: "K",
            16: "D/ST",
        }
        return positions.get(position_id, "UNK")

    def _get_team_abbr(self, team_id: int) -> str:
        """Convert ESPN team ID to abbreviation."""
        teams = {
            1: "ATL",
            2: "BUF",
            3: "CHI",
            4: "CIN",
            5: "CLE",
            6: "DAL",
            7: "DEN",
            8: "DET",
            9: "GB",
            10: "TEN",
            11: "IND",
            12: "KC",
            13: "LV",
            14: "LAR",
            15: "MIA",
            16: "MIN",
            17: "NE",
            18: "NO",
            19: "NYG",
            20: "NYJ",
            21: "PHI",
            22: "ARI",
            23: "PIT",
            24: "LAC",
            25: "SF",
            26: "SEA",
            27: "TB",
            28: "WAS",
            29: "CAR",
            30: "JAX",
            33: "BAL",
            34: "HOU",
        }
        return teams.get(team_id, "FA")


def main():
    """Example usage of ESPN League Integration."""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    # Get credentials from environment
    league_id = int(os.getenv("ESPN_LEAGUE_ID", "0"))
    swid = os.getenv("ESPN_SWID", "")
    espn_s2 = os.getenv("ESPN_S2", "")

    if not league_id:
        print("Error: Set ESPN_LEAGUE_ID in .env file")
        return

    # Initialize
    espn = ESPNLeagueIntegration(league_id, swid=swid, espn_s2=espn_s2)

    # Get league info
    print("\n=== League Info ===")
    info = espn.get_league_info()
    print(f"League: {info['name']}")
    print(f"Size: {info['size']} teams")
    print(f"Scoring: {info['scoring_type']}")
    print(f"Roster: {info['roster_slots']}")

    # Get standings
    print("\n=== Standings ===")
    standings = espn.get_standings()
    print(standings.to_string(index=False))

    # Get your team's roster (change team_id to yours)
    print("\n=== Your Roster ===")
    my_team_id = 1  # Change this to your team ID
    roster = espn.get_team_roster(my_team_id)
    print(roster[["player", "position", "team", "lineup_slot"]].to_string(index=False))


if __name__ == "__main__":
    main()

"""CFB FAAB waiver processor."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from ffpy.database import FFPyDatabase


class CfbWaiverError(ValueError):
    """Waiver claim validation error."""


class CfbWaiverService:
    """Process pending add/drop claims with FAAB priority."""

    def __init__(self, db: FFPyDatabase):
        self.db = db

    def submit_claim(
        self,
        league_id: str,
        team_id: str,
        add_player_id: int,
        drop_player_id: Optional[int] = None,
        faab_bid: Optional[float] = None,
        week: Optional[int] = None,
    ) -> int:
        league = self.db.get_cfb_league(league_id)
        if not league:
            raise CfbWaiverError("League not found")
        settings = self.db.get_cfb_league_settings(league_id)
        if settings.get("waiver_type") == "none":
            raise CfbWaiverError("Waivers disabled for this league")

        try:
            self.db.validate_cfb_roster_move(league_id, add_player_id, action="add")
        except ValueError as exc:
            raise CfbWaiverError(str(exc)) from exc

        if drop_player_id:
            roster = self.db.get_cfb_league_roster(team_id)
            if drop_player_id not in set(roster["player_id"].tolist()):
                raise CfbWaiverError("Drop player not on roster")

        bid = faab_bid if faab_bid is not None else 0.0
        if settings.get("waiver_type") == "faab" and bid <= 0:
            raise CfbWaiverError("FAAB bid required")

        team = next(
            (t for t in self.db.get_cfb_league_teams(league_id) if t["league_team_id"] == team_id),
            None,
        )
        if team and float(team.get("faab_budget") or 0) < bid:
            raise CfbWaiverError("Insufficient FAAB budget")

        return self.db.create_cfb_transaction(
            {
                "league_id": league_id,
                "league_team_id": team_id,
                "tx_type": "add",
                "player_id": add_player_id,
                "drop_player_id": drop_player_id,
                "faab_bid": bid,
                "status": "pending",
                "week": week,
            }
        )

    def run_waivers(self, league_id: str, week: int) -> dict[str, Any]:
        league = self.db.get_cfb_league(league_id)
        if not league:
            raise CfbWaiverError("League not found")
        season = int(league["season"])
        settings = self.db.get_cfb_league_settings(league_id)

        claims = self.db.list_cfb_transactions(league_id, status="pending", week=week)
        add_claims = [c for c in claims if c.get("tx_type") == "add"]
        if not add_claims:
            return {"processed": 0, "failed": 0, "results": []}

        standings = {
            s["league_team_id"]: s["rank"] for s in self.db.get_cfb_standings(league_id, season, week)
        }

        def sort_key(c: dict) -> tuple:
            bid = float(c.get("faab_bid") or 0)
            created = c.get("created_at") or ""
            rank = standings.get(c["league_team_id"], 999)
            return (-bid, created, rank)

        add_claims.sort(key=sort_key)

        processed = 0
        failed = 0
        results: list[dict] = []
        awarded: set[int] = set()

        for claim in add_claims:
            tx_id = claim["transaction_id"]
            add_id = int(claim["player_id"])
            team_id = claim["league_team_id"]
            drop_id = claim.get("drop_player_id")

            if add_id in awarded:
                self.db.update_cfb_transaction(
                    tx_id,
                    {
                        "status": "failed",
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                        "failure_reason": "Player claimed by higher bid",
                    },
                )
                failed += 1
                results.append({"transaction_id": tx_id, "status": "failed"})
                continue

            try:
                rostered = self.db.get_cfb_league_rostered_player_ids(league_id)
                if add_id in rostered:
                    raise CfbWaiverError("Player already rostered")

                if drop_id:
                    self.db.drop_cfb_roster_player(team_id, int(drop_id))
                else:
                    roster = self.db.get_cfb_league_roster(team_id)
                    if len(roster) >= self.db._cfb_max_roster_size(league):
                        raise CfbWaiverError("Roster full — specify drop player")

                self.db.add_cfb_roster_player(team_id, add_id, slot="BENCH")
                awarded.add(add_id)

                bid = float(claim.get("faab_bid") or 0)
                if settings.get("waiver_type") == "faab" and bid > 0:
                    self.db.decrement_cfb_faab(team_id, bid)

                self.db.update_cfb_transaction(
                    tx_id,
                    {"status": "completed", "processed_at": datetime.now(timezone.utc).isoformat()},
                )
                processed += 1
                results.append({"transaction_id": tx_id, "status": "completed"})
            except (ValueError, CfbWaiverError) as exc:
                self.db.update_cfb_transaction(
                    tx_id,
                    {
                        "status": "failed",
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                        "failure_reason": str(exc),
                    },
                )
                failed += 1
                results.append({"transaction_id": tx_id, "status": "failed", "reason": str(exc)})

        self.db.log_cfb_waiver_run(league_id, season, week, processed, failed)
        return {"processed": processed, "failed": failed, "results": results}

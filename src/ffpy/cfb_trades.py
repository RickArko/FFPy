"""CFB trade proposal, acceptance, and league veto."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ffpy.database import FFPyDatabase


class CfbTradeError(ValueError):
    """Trade validation or state error."""


class CfbTradeService:
    """State machine for two-team trades with optional league veto."""

    def __init__(self, db: FFPyDatabase):
        self.db = db

    def _check_deadline(self, league_id: str, week: int) -> None:
        settings = self.db.get_cfb_league_settings(league_id)
        deadline = int(settings.get("trade_deadline_week") or 12)
        if week > deadline:
            raise CfbTradeError(f"Trade deadline passed (week {deadline})")

    def propose(
        self,
        league_id: str,
        proposer_team_id: str,
        recipient_team_id: str,
        items: list[dict],
        week: int = 1,
    ) -> dict[str, Any]:
        if proposer_team_id == recipient_team_id:
            raise CfbTradeError("Cannot trade with yourself")
        self._check_deadline(league_id, week)
        if not items:
            raise CfbTradeError("Trade must include at least one player")

        settings = self.db.get_cfb_league_settings(league_id)
        review_hours = int(settings.get("trade_review_hours") or 24)
        expires = datetime.now(timezone.utc) + timedelta(hours=review_hours)
        trade_id = f"trade:{uuid.uuid4().hex[:12]}"

        validated_items: list[dict] = []
        for item in items:
            player_id = int(item["player_id"])
            from_team = item["from_team_id"]
            to_team = item["to_team_id"]
            roster = self.db.get_cfb_league_roster(from_team)
            if player_id not in set(roster["player_id"].tolist()):
                raise CfbTradeError(f"Player {player_id} not on roster {from_team}")
            validated_items.append(
                {
                    "trade_id": trade_id,
                    "player_id": player_id,
                    "from_team_id": from_team,
                    "to_team_id": to_team,
                }
            )

        self.db.create_cfb_trade(
            {
                "trade_id": trade_id,
                "league_id": league_id,
                "proposer_team_id": proposer_team_id,
                "recipient_team_id": recipient_team_id,
                "expires_at": expires.isoformat(),
            }
        )
        for item in validated_items:
            self.db.add_cfb_trade_item(item)
        return self.get_trade(league_id, trade_id)

    def accept(self, league_id: str, trade_id: str, accepting_team_id: str) -> dict[str, Any]:
        trade = self.db.get_cfb_trade(trade_id)
        if not trade or trade["league_id"] != league_id:
            raise CfbTradeError("Trade not found")
        if trade["status"] != "proposed":
            raise CfbTradeError(f"Trade status is {trade['status']}")
        if accepting_team_id != trade["recipient_team_id"]:
            raise CfbTradeError("Only recipient can accept")

        self.db.update_cfb_trade_status(trade_id, "accepted")
        return self._try_complete(league_id, trade_id)

    def veto(self, league_id: str, trade_id: str, team_id: str) -> dict[str, Any]:
        trade = self.db.get_cfb_trade(trade_id)
        if not trade or trade["league_id"] != league_id:
            raise CfbTradeError("Trade not found")
        if trade["status"] not in ("proposed", "accepted"):
            raise CfbTradeError(f"Cannot veto trade in status {trade['status']}")

        self.db.add_cfb_trade_vote(trade_id, team_id, "veto")
        settings = self.db.get_cfb_league_settings(league_id)
        threshold = int(settings.get("veto_threshold") or 0)
        vetoes = self.db.count_cfb_trade_vetoes(trade_id)
        if threshold > 0 and vetoes >= threshold:
            self.db.update_cfb_trade_status(trade_id, "vetoed")
        return self.get_trade(league_id, trade_id)

    def _try_complete(self, league_id: str, trade_id: str) -> dict[str, Any]:
        trade = self.db.get_cfb_trade(trade_id)
        if not trade:
            raise CfbTradeError("Trade not found")

        settings = self.db.get_cfb_league_settings(league_id)
        threshold = int(settings.get("veto_threshold") or 0)
        vetoes = self.db.count_cfb_trade_vetoes(trade_id)
        if threshold > 0 and vetoes >= threshold:
            self.db.update_cfb_trade_status(trade_id, "vetoed")
            return self.get_trade(league_id, trade_id)

        if trade["status"] not in ("accepted", "proposed"):
            return self.get_trade(league_id, trade_id)

        self.db.update_cfb_trade_status(trade_id, "processing")
        items = self.db.get_cfb_trade_items(trade_id)
        try:
            for item in items:
                self.db.drop_cfb_roster_player(item["from_team_id"], int(item["player_id"]))
            for item in items:
                self.db.add_cfb_roster_player(item["to_team_id"], int(item["player_id"]), slot="BENCH")
            self.db.update_cfb_trade_status(trade_id, "completed")
        except ValueError as exc:
            self.db.update_cfb_trade_status(trade_id, "cancelled")
            raise CfbTradeError(str(exc)) from exc

        return self.get_trade(league_id, trade_id)

    def get_trade(self, league_id: str, trade_id: str) -> dict[str, Any]:
        trade = self.db.get_cfb_trade(trade_id)
        if not trade or trade["league_id"] != league_id:
            raise CfbTradeError("Trade not found")
        items = self.db.get_cfb_trade_items(trade_id)
        return {**trade, "items": items}

    def list_trades(self, league_id: str, status: Optional[str] = None) -> list[dict]:
        trades = self.db.list_cfb_trades(league_id, status=status)
        return [{**t, "items": self.db.get_cfb_trade_items(t["trade_id"])} for t in trades]

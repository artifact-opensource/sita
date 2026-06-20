"""
SITA — Discord Integration
Posts trade alerts, signals, health status, and daily reports to Discord.

Uses discord.py (same library Hermes uses natively).
"""

from __future__ import annotations
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger("sita.discord")

# Channel IDs (configured via env or config)
# Use a factory function to avoid mutable default sharing
def _default_channels() -> Dict[str, Optional[int]]:
    return {
        "alerts": None,    # Trade alerts (entries, exits, SL hits)
        "signals": None,   # Signal generation notifications
        "health": None,    # System health / heartbeat
        "journal": None,   # Daily reflection / strategy updates
        "reports": None,   # Performance reports
    }


class DiscordNotifier:
    """
    Discord notification system for SITA.
    Posts rich embeds for trades, signals, and reports.
    """

    def __init__(self, token: str = None, channels: Dict[str, int] = None):
        self.token = token
        self.channels = channels if channels is not None else _default_channels()
        self._client = None
        self._enabled = bool(token)

        if self._enabled:
            logger.info("Discord notifier initialized")
        else:
            logger.info("Discord notifier disabled (no token)")

    def post_alert(self, title: str, description: str, color: str = "blue", fields: Dict = None):
        """Post a trade alert."""
        if not self._enabled:
            return

        embed = {
            "title": title,
            "description": description,
            "color": self._color(color),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fields": [{"name": k, "value": str(v), "inline": True} for k, v in (fields or {}).items()],
        }

        self._send_to_channel("alerts", embed)

    def post_signal(self, symbol: str, direction: str, confidence: float, strategy: str, confluence_score: float):
        """Post a signal notification."""
        if not self._enabled:
            return

        emoji = "🟢" if direction == "long" else "🔴"
        embed = {
            "title": f"{emoji} Signal: {symbol}",
            "description": f"**{direction.upper()}** | Strategy: {strategy}",
            "color": self._color("green" if direction == "long" else "red"),
            "fields": [
                {"name": "Confidence", "value": f"{confidence:.0%}", "inline": True},
                {"name": "Confluence", "value": f"{confluence_score:.0f}/100", "inline": True},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self._send_to_channel("signals", embed)

    def post_trade(self, symbol: str, side: str, size: float, entry: float, sl: float, tp: float, pnl: float = None):
        """Post a trade execution."""
        if not self._enabled:
            return

        emoji = "📈" if side == "long" else "📉"
        fields = [
            {"name": "Size", "value": f"{size}", "inline": True},
            {"name": "Entry", "value": f"{entry}", "inline": True},
            {"name": "Stop Loss", "value": f"{sl}", "inline": True},
            {"name": "Take Profit", "value": f"{tp}", "inline": True},
        ]

        if pnl is not None:
            pnl_emoji = "✅" if pnl > 0 else "❌"
            fields.append({"name": "P&L", "value": f"{pnl_emoji} ${pnl:.2f}", "inline": True})

        embed = {
            "title": f"{emoji} Trade: {symbol}",
            "description": f"**{side.upper()}** position {'closed' if pnl is not None else 'opened'}",
            "color": self._color("green" if side == "long" else "red"),
            "fields": fields,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self._send_to_channel("alerts", embed)

    def post_health(self, status: Dict):
        """Post system health status."""
        if not self._enabled:
            return

        positions = status.get("open_positions", 0)
        balance = status.get("balance", 0)
        stats = status.get("stats", {})

        embed = {
            "title": "💓 SITA Health",
            "color": self._color("blue"),
            "fields": [
                {"name": "Balance", "value": f"${balance:.2f}", "inline": True},
                {"name": "Open Positions", "value": str(positions), "inline": True},
                {"name": "Total Trades", "value": str(stats.get("total_trades", 0)), "inline": True},
                {"name": "Win Rate", "value": f"{stats.get('win_rate', 0):.0%}", "inline": True},
                {"name": "Total P&L", "value": f"${stats.get('total_pnl', 0):.2f}", "inline": True},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self._send_to_channel("health", embed)

    def post_reflection(self, result: Dict):
        """Post reflection cycle results."""
        if not self._enabled:
            return

        hypothesis = result.get("hypothesis", {})
        embed = {
            "title": "🧠 Reflection Cycle",
            "description": hypothesis.get("description", "No change"),
            "color": self._color("purple"),
            "fields": [
                {"name": "Score", "value": f"{result.get('score', 0):.2f}", "inline": True},
                {"name": "Version", "value": result.get("result", {}).get("version", "?"), "inline": True},
                {"name": "Reasoning", "value": hypothesis.get("reasoning", "N/A")[:200], "inline": False},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self._send_to_channel("journal", embed)

    def post_daily_report(self, stats: Dict, trades: List[Dict]):
        """Post daily performance report."""
        if not self._enabled:
            return

        total = stats.get("total_trades", 0)
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        win_rate = stats.get("win_rate", 0)
        total_pnl = stats.get("total_pnl", 0)
        avg_pnl = stats.get("avg_pnl", 0)

        emoji = "📊"
        if total_pnl > 0:
            emoji = "🟢📈"
        elif total_pnl < 0:
            emoji = "🔴📉"

        embed = {
            "title": f"{emoji} Daily Report",
            "color": self._color("green" if total_pnl >= 0 else "red"),
            "fields": [
                {"name": "Trades", "value": f"{total} (W{wins}/L{losses})", "inline": True},
                {"name": "Win Rate", "value": f"{win_rate:.0%}", "inline": True},
                {"name": "Total P&L", "value": f"${total_pnl:.2f}", "inline": True},
                {"name": "Avg P&L", "value": f"${avg_pnl:.2f}", "inline": True},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Add recent trades
        if trades:
            recent = trades[-5:]
            trade_lines = []
            for t in recent:
                pnl = t.get("pnl", 0)
                sym = t.get("symbol", "?")
                side = t.get("side", "?")
                trade_lines.append(f"{'✅' if pnl > 0 else '❌'} {side.upper()} {sym}: ${pnl:.2f}")

            embed["fields"].append({
                "name": "Recent Trades",
                "value": "\n".join(trade_lines) or "None",
                "inline": False,
            })

        self._send_to_channel("reports", embed)

    def _send_to_channel(self, channel_key: str, embed: Dict):
        """Send an embed to a Discord channel via webhook or bot API."""
        import json, urllib.request, urllib.error

        channel_id = self.channels.get(channel_key)
        webhook_url = self.channels.get("webhook_url")

        _ua = "DiscordBot (https://github.com/artifact-opensource/sita, 1.0.0)"

        # Prefer webhook for simple posting
        if webhook_url:
            try:
                payload = json.dumps({"embeds": [embed]}).encode()
                req = urllib.request.Request(
                    webhook_url,
                    data=payload,
                    headers={"Content-Type": "application/json", "User-Agent": _ua},
                    method="POST",
                )
                resp = urllib.request.urlopen(req, timeout=10)
                logger.info(f"Discord [{channel_key}] webhook sent: {embed.get('title')} (status {resp.status})")
                return
            except Exception as e:
                logger.warning(f"Discord webhook failed: {e}")

        # Fallback: try bot API with channel ID
        if channel_id and self.token:
            try:
                url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
                payload = json.dumps({"embeds": [embed]}).encode()
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={
                        "Authorization": f"Bot {self.token}",
                        "Content-Type": "application/json",
                        "User-Agent": _ua,
                    },
                    method="POST",
                )
                resp = urllib.request.urlopen(req, timeout=10)
                logger.info(f"Discord [{channel_key}] bot sent: {embed.get('title')} (status {resp.status})")
                return
            except Exception as e:
                logger.warning(f"Discord bot API failed: {e}")

        logger.info(f"Discord [{channel_key}] (no delivery): {embed.get('title')}")

    @staticmethod
    def _color(name: str) -> int:
        """Convert color name to Discord embed color integer."""
        colors = {
            "red": 0xFF0000,
            "green": 0x00FF00,
            "blue": 0x0000FF,
            "yellow": 0xFFFF00,
            "orange": 0xFF8800,
            "purple": 0x8800FF,
            "white": 0xFFFFFF,
            "black": 0x000000,
        }
        return colors.get(name, 0x0000FF)

"""Snapshots: save a full run (market data + AI outputs) so the app works offline in demo mode."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DEMO_PATH = Path(__file__).resolve().parent.parent / "data" / "demo_snapshot.json"


def save_snapshot(market: dict, player_voice: dict, concepts: list, country: str,
                  path: Path = DEMO_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "country": country,
        "market": market,
        "player_voice": player_voice,
        "concepts": concepts,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load_snapshot(path: Path = DEMO_PATH) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

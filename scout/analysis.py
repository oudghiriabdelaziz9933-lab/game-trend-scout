"""Market analysis: cross the two charts and turn them into signals a designer can read."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

# Genres that describe the store category rather than the game itself
NON_GAME_GENRES = {"Games", "Entertainment", "Social Networking", "Lifestyle", "Utilities"}
NEW_GAME_DAYS = 365


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_market_table(market: dict, today: datetime | None = None) -> pd.DataFrame:
    """One row per game with its rank in each chart and its details."""
    today = today or datetime.now(timezone.utc)
    rows: dict[str, dict] = {}
    for chart in ("free", "grossing"):
        for game in market.get(chart, []):
            row = rows.setdefault(
                game["id"],
                {"id": game["id"], "name": game["name"], "developer": game["developer"],
                 "rank_free": None, "rank_grossing": None},
            )
            row[f"rank_{chart}"] = game["rank"]

    details = market.get("details", {})
    for game_id, row in rows.items():
        info = details.get(game_id, {})
        subgenres = [g for g in info.get("genres", []) if g not in NON_GAME_GENRES]
        released = _parse_date(info.get("release_date"))
        row.update(
            {
                "subgenres": subgenres,
                "main_genre": subgenres[0] if subgenres else "Other",
                "rating": info.get("rating"),
                "rating_count": info.get("rating_count", 0),
                "release_date": released.date().isoformat() if released else None,
                "age_days": (today - released).days if released else None,
                "description": info.get("description", ""),
                "icon": info.get("icon", ""),
                "url": info.get("url", ""),
            }
        )

    df = pd.DataFrame(list(rows.values()))
    if df.empty:
        return df
    df["in_both"] = df["rank_free"].notna() & df["rank_grossing"].notna()
    df["is_new"] = df["age_days"].notna() & (df["age_days"] <= NEW_GAME_DAYS)
    # A simple, explainable momentum score: chart presence weighted by rank, bonus for new games
    free_score = (101 - df["rank_free"].fillna(101)) / 100
    gross_score = (101 - df["rank_grossing"].fillna(101)) / 100
    df["momentum"] = (free_score + gross_score + df["is_new"] * 0.3).round(2)
    return df.sort_values("momentum", ascending=False).reset_index(drop=True)


def genre_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per genre: presence in each chart, crossovers, newcomers and player satisfaction."""
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("main_genre").agg(
        games=("id", "count"),
        in_free=("rank_free", lambda s: s.notna().sum()),
        in_grossing=("rank_grossing", lambda s: s.notna().sum()),
        crossovers=("in_both", "sum"),
        newcomers=("is_new", "sum"),
        avg_rating=("rating", "mean"),
    )
    g["avg_rating"] = g["avg_rating"].round(2)
    # Monetisation strength: share of a genre's chart slots that sit in the grossing chart
    g["grossing_share"] = (g["in_grossing"] / (g["in_free"] + g["in_grossing"])).round(2)
    return g.sort_values("games", ascending=False).reset_index()


def key_signals(df: pd.DataFrame, genres: pd.DataFrame) -> list[str]:
    """Plain-language observations computed from the data (no AI involved)."""
    if df.empty:
        return []
    signals = []
    both = df[df["in_both"]]
    signals.append(
        f"{len(both)} games rank in both the top free and top grossing charts: "
        "they combine reach and revenue."
    )
    new = df[df["is_new"]].sort_values("momentum", ascending=False)
    if not new.empty:
        names = ", ".join(new["name"].head(3))
        signals.append(f"{len(new)} games released in the last 12 months reached the charts, led by {names}.")
    if not genres.empty:
        top = genres.iloc[0]
        signals.append(f"{top['main_genre']} is the most represented genre ({int(top['games'])} games).")
        money = genres[genres["games"] >= 3].sort_values("grossing_share", ascending=False)
        if not money.empty:
            m = money.iloc[0]
            signals.append(
                f"{m['main_genre']} monetises best: {int(m['in_grossing'])} of its "
                f"{int(m['in_free'] + m['in_grossing'])} chart slots are in the grossing chart."
            )
        reach = genres[(genres["in_free"] >= 3)].sort_values("grossing_share")
        if not reach.empty:
            r = reach.iloc[0]
            signals.append(
                f"{r['main_genre']} drives downloads but monetises weakly "
                f"({int(r['in_free'])} free-chart games, {int(r['in_grossing'])} in grossing): "
                "room for a better monetised take."
            )
    return signals


def market_brief(df: pd.DataFrame, genres: pd.DataFrame, top_n: int = 25) -> str:
    """Compact text summary of the market, used as grounding for the AI."""
    lines = ["TOP GAMES (by momentum):"]
    for _, r in df.head(top_n).iterrows():
        ranks = []
        if pd.notna(r["rank_free"]):
            ranks.append(f"free #{int(r['rank_free'])}")
        if pd.notna(r["rank_grossing"]):
            ranks.append(f"grossing #{int(r['rank_grossing'])}")
        rating = f"{r['rating']:.1f}/5" if pd.notna(r["rating"]) else "n/a"
        new = ", NEW" if r["is_new"] else ""
        genres_txt = "/".join(r["subgenres"]) or "Other"
        lines.append(f"- {r['name']} [{genres_txt}] {', '.join(ranks)}, rating {rating}{new}")
    lines.append("\nGENRES (games, free, grossing, crossovers, newcomers, avg rating):")
    for _, g in genres.iterrows():
        lines.append(
            f"- {g['main_genre']}: {int(g['games'])}, {int(g['in_free'])}, {int(g['in_grossing'])}, "
            f"{int(g['crossovers'])}, {int(g['newcomers'])}, {g['avg_rating']}"
        )
    return "\n".join(lines)

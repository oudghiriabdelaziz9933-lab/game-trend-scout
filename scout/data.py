"""Data layer: public Apple App Store feeds (no scraping, no API key).

- Top charts: iTunes RSS feeds, filtered on the Games genre (6014)
- Game details: iTunes Lookup API (genres, rating, release date, description)
- Reviews: iTunes customer-reviews RSS feed (most recent reviews)
"""
from __future__ import annotations

import time

import requests

BASE = "https://itunes.apple.com"
GAMES_GENRE_ID = 6014
CHART_FEEDS = {
    "free": "topfreeapplications",
    "grossing": "topgrossingapplications",
}
HEADERS = {"User-Agent": "game-trend-scout/1.0 (case study prototype)"}
TIMEOUT = 15


class DataError(RuntimeError):
    """Raised when an App Store feed cannot be reached or parsed."""


def _get_json(url: str, params: dict | None = None, retries: int = 2) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            time.sleep(1 + attempt)
    raise DataError(f"Could not load {url}: {last_error}")


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse_chart(payload: dict, chart: str) -> list[dict]:
    """Turn an iTunes RSS chart payload into a ranked list of games."""
    entries = _as_list(payload.get("feed", {}).get("entry"))
    games = []
    for rank, entry in enumerate(entries, start=1):
        try:
            games.append(
                {
                    "id": entry["id"]["attributes"]["im:id"],
                    "name": entry["im:name"]["label"],
                    "developer": entry.get("im:artist", {}).get("label", ""),
                    "chart": chart,
                    "rank": rank,
                }
            )
        except (KeyError, TypeError):
            continue  # skip malformed entries rather than failing the whole chart
    return games


def fetch_chart(chart: str, country: str = "us", limit: int = 100) -> list[dict]:
    if chart not in CHART_FEEDS:
        raise ValueError(f"Unknown chart '{chart}'. Use one of {list(CHART_FEEDS)}")
    url = f"{BASE}/{country}/rss/{CHART_FEEDS[chart]}/limit={limit}/genre={GAMES_GENRE_ID}/json"
    return parse_chart(_get_json(url), chart)


def parse_lookup(payload: dict) -> dict[str, dict]:
    details = {}
    for item in payload.get("results", []):
        if "trackId" not in item:
            continue
        details[str(item["trackId"])] = {
            "genres": item.get("genres", []),
            "primary_genre": item.get("primaryGenreName", ""),
            "rating": item.get("averageUserRating"),
            "rating_count": item.get("userRatingCount", 0),
            "release_date": item.get("releaseDate"),
            "last_update": item.get("currentVersionReleaseDate"),
            "price": item.get("price", 0.0),
            "description": (item.get("description") or "")[:1500],
            "icon": item.get("artworkUrl100", ""),
            "url": item.get("trackViewUrl", ""),
        }
    return details


def fetch_details(app_ids: list[str], country: str = "us") -> dict[str, dict]:
    """Look up game details in batches (the Lookup API accepts many ids per call)."""
    details: dict[str, dict] = {}
    ids = list(dict.fromkeys(app_ids))
    for start in range(0, len(ids), 100):
        batch = ids[start : start + 100]
        payload = _get_json(f"{BASE}/lookup", {"id": ",".join(batch), "country": country})
        details.update(parse_lookup(payload))
    return details


def parse_reviews(payload: dict) -> list[dict]:
    reviews = []
    for entry in _as_list(payload.get("feed", {}).get("entry")):
        if "im:rating" not in entry:
            continue  # the first entry of some feeds describes the app, not a review
        reviews.append(
            {
                "rating": int(entry["im:rating"]["label"]),
                "title": entry.get("title", {}).get("label", ""),
                "text": entry.get("content", {}).get("label", ""),
                "version": entry.get("im:version", {}).get("label", ""),
                "date": entry.get("updated", {}).get("label", ""),
            }
        )
    return reviews


def fetch_reviews(app_id: str, country: str = "us", pages: int = 2) -> list[dict]:
    """Most recent reviews (50 per page, Apple caps the feed at 10 pages)."""
    reviews: list[dict] = []
    for page in range(1, pages + 1):
        url = f"{BASE}/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
        try:
            batch = parse_reviews(_get_json(url, retries=1))
        except DataError:
            break  # partial reviews are still useful
        if not batch:
            break
        reviews.extend(batch)
    return reviews


def fetch_market(country: str = "us", limit: int = 100) -> dict:
    """Both charts plus details for every game that appears in either."""
    free = fetch_chart("free", country, limit)
    warnings = []
    try:
        grossing = fetch_chart("grossing", country, limit)
    except DataError as exc:  # keep the app usable on the free chart alone
        grossing = []
        warnings.append(f"Top grossing chart unavailable: {exc}")
    try:
        details = fetch_details([g["id"] for g in free + grossing], country)
    except DataError as exc:
        details = {}
        warnings.append(f"Game details unavailable (genres, ratings): {exc}")
    return {"free": free, "grossing": grossing, "details": details, "warnings": warnings}

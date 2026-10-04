"""Fetch live App Store data and save it as the demo snapshot (data/demo_snapshot.json).

Usage:
    python3 build_demo.py            charts + AI review summaries + AI concepts (needs GEMINI_API_KEY)
    python3 build_demo.py --no-ai    charts only, no key needed (AI tabs stay empty in demo mode)
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from scout.analysis import build_market_table, genre_summary, market_brief
from scout.data import DataError, fetch_market, fetch_reviews
from scout.insights import generate_concepts, summarize_reviews
from scout.llm import GeminiClient, LLMError
from scout.snapshot import save_snapshot

COUNTRY = "us"
GAMES_TO_SUMMARISE = 5


def main() -> None:
    load_dotenv()
    use_ai = "--no-ai" not in sys.argv

    print("1/3 Fetching App Store charts...")
    try:
        market = fetch_market(COUNTRY)
    except DataError as exc:
        sys.exit(f"Could not reach the App Store: {exc}")
    for warning in market.get("warnings", []):
        print(f"   ! {warning}")
    df = build_market_table(market)
    genres = genre_summary(df)
    print(f"   {len(market['free'])} top free games, {len(market['grossing'])} top grossing games, "
          f"{len(df)} unique games")

    player_voice, concepts = {}, []
    if use_ai:
        try:
            llm = GeminiClient(os.getenv("GEMINI_API_KEY", ""))
        except LLMError as exc:
            sys.exit(f"{exc}\nTip: run `python3 build_demo.py --no-ai` to save the charts only.")

        print("2/3 Summarising player reviews...")
        for _, game in df.head(GAMES_TO_SUMMARISE).iterrows():
            reviews = fetch_reviews(game["id"], COUNTRY)
            try:
                player_voice[game["name"]] = summarize_reviews(llm, game["name"], reviews)
                print(f"   - {game['name']}: {len(reviews)} reviews")
            except LLMError as exc:
                print(f"   ! {game['name']}: {exc}")

        print("3/3 Generating game concepts...")
        try:
            concepts = generate_concepts(llm, market_brief(df, genres), player_voice, df["name"].tolist(), n=3)
        except LLMError as exc:
            print(f"   ! {exc}")
    else:
        print("2/3 and 3/3 skipped (--no-ai)")

    path = save_snapshot(market, player_voice, concepts, COUNTRY)
    print(f"Done. Snapshot saved to {path}")


if __name__ == "__main__":
    main()

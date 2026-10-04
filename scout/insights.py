"""AI features: player-voice synthesis and grounded game-concept generation."""
from __future__ import annotations

import random

REVIEW_SYSTEM = (
    "You are a senior mobile game user researcher. You summarise App Store reviews for game "
    "designers. Be specific and concrete (mechanics, features, monetisation, difficulty, ads), "
    "never generic. Only use what the reviews say."
)

CONCEPT_SYSTEM = (
    "You are a lead game designer at a casual / hybrid-casual mobile publisher like Voodoo. "
    "Your games are instantly understandable, playable with one hand in sessions of 1-5 minutes, "
    "cheap to prototype, and easy to test with short video ads. You turn market data into "
    "original game concepts. Every claim about the market must come from the data you are given: "
    "never invent games, ranks or numbers."
)


def sample_reviews(reviews: list[dict], max_reviews: int = 60, seed: int = 7) -> list[dict]:
    """Keep the prompt small and balanced: mix of low and high ratings, longest texts first."""
    if len(reviews) <= max_reviews:
        return reviews
    low = [r for r in reviews if r["rating"] <= 2]
    high = [r for r in reviews if r["rating"] >= 4]
    mid = [r for r in reviews if r["rating"] == 3]
    rng = random.Random(seed)
    picked = []
    for bucket, share in ((low, 0.4), (high, 0.4), (mid, 0.2)):
        bucket = sorted(bucket, key=lambda r: len(r["text"]), reverse=True)[: max_reviews]
        rng.shuffle(bucket)
        picked.extend(bucket[: int(max_reviews * share)])
    return picked[:max_reviews]


def review_prompt(game_name: str, reviews: list[dict]) -> str:
    lines = [f"Game: {game_name}", f"{len(reviews)} recent App Store reviews:"]
    for r in reviews:
        text = r["text"].replace("\n", " ")[:400]
        lines.append(f"- [{r['rating']}/5] {r['title']}: {text}")
    lines.append(
        "\nReturn JSON with keys: "
        '"verdict" (one sentence on how players feel), '
        '"loves" (3-5 short bullet strings), "hates" (3-5), "requests" (2-4 features players ask for), '
        '"design_lesson" (one sentence: what a designer should copy or avoid).'
    )
    return "\n".join(lines)


def summarize_reviews(llm, game_name: str, reviews: list[dict]) -> dict:
    if not reviews:
        return {"verdict": "No reviews available for this game.", "loves": [], "hates": [],
                "requests": [], "design_lesson": ""}
    sample = sample_reviews(reviews)
    result = llm.generate_json(review_prompt(game_name, sample), REVIEW_SYSTEM, temperature=0.2)
    result["reviews_used"] = len(sample)
    result["avg_review_rating"] = round(sum(r["rating"] for r in sample) / len(sample), 1)
    return result


def concept_prompt(brief: str, player_voice: dict[str, dict], n: int, focus: str, designer_note: str) -> str:
    parts = ["MARKET DATA (US App Store, Games):", brief]
    if player_voice:
        parts.append("\nPLAYER VOICE (AI summaries of recent reviews):")
        for game, s in player_voice.items():
            parts.append(
                f"- {game}: loves {s.get('loves', [])}; hates {s.get('hates', [])}; "
                f"requests {s.get('requests', [])}"
            )
    if focus and focus != "Any genre":
        parts.append(f"\nFOCUS: concepts must sit in or next to the {focus} genre.")
    if designer_note:
        parts.append(f"\nDESIGNER BRIEF: {designer_note}")
    parts.append(
        f"\nPropose {n} original game concepts that exploit what is working now and fix what players "
        "complain about. Do not clone an existing game. Return JSON: a list of objects with keys "
        '"title", "pitch" (one sentence), "genre", "core_mechanic", '
        '"game_loop" (list of 3-5 short steps: what the player does again and again), '
        '"twist" (what makes it fresh vs the charts), '
        '"evidence" (list of 2-4 objects {"game": exact game name from the market data, '
        '"signal": what in the data or reviews supports the concept}), '
        '"opportunity_score" (1-10) and "main_risk" (one sentence).'
    )
    return "\n".join(parts)


def generate_concepts(llm, brief: str, player_voice: dict[str, dict], known_games: list[str],
                      n: int = 3, focus: str = "Any genre", designer_note: str = "") -> list[dict]:
    raw = llm.generate_json(concept_prompt(brief, player_voice, n, focus, designer_note),
                            CONCEPT_SYSTEM, temperature=0.9)
    concepts = raw.get("concepts", raw) if isinstance(raw, dict) else raw
    return [check_evidence(c, known_games) for c in concepts if isinstance(c, dict)]


def check_evidence(concept: dict, known_games: list[str]) -> dict:
    """Guardrail against hallucination: flag evidence that cites a game not in the data."""
    known = {g.lower().strip() for g in known_games}
    checked = []
    for item in concept.get("evidence", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("game", "")).strip()
        lowered = name.lower()
        # exact match, or one name contains the other ("Royal Match" vs "Royal Match: Puzzle")
        verified = lowered in known or any(
            len(lowered) >= 4 and len(k) >= 4 and (lowered in k or k in lowered) for k in known
        )
        checked.append({**item, "verified": verified})
    concept["evidence"] = checked
    concept["grounded_share"] = round(sum(e["verified"] for e in checked) / len(checked), 2) if checked else 0.0
    return concept

"""Offline tests: parsers, analysis and the AI guardrails (no network, no API key)."""
from datetime import datetime, timezone

from scout.analysis import build_market_table, genre_summary, key_signals, market_brief
from scout.data import parse_chart, parse_lookup, parse_reviews
from scout.insights import check_evidence, generate_concepts, sample_reviews, summarize_reviews
from scout.llm import extract_json

TODAY = datetime(2026, 10, 1, tzinfo=timezone.utc)


def chart_payload(names_ids):
    return {"feed": {"entry": [
        {"id": {"attributes": {"im:id": i}}, "im:name": {"label": n}, "im:artist": {"label": "Studio"}}
        for n, i in names_ids
    ]}}


def market():
    free = parse_chart(chart_payload([("Block Blast", "1"), ("Rope Rescue", "2"), ("Hole Hero", "3")]), "free")
    grossing = parse_chart(chart_payload([("Royal Tiles", "4"), ("Block Blast", "1")]), "grossing")
    details = parse_lookup({"results": [
        {"trackId": 1, "genres": ["Games", "Puzzle", "Entertainment"], "averageUserRating": 4.6,
         "userRatingCount": 1000, "releaseDate": "2026-03-01T07:00:00Z"},
        {"trackId": 2, "genres": ["Games", "Casual"], "averageUserRating": 3.9, "releaseDate": "2020-01-01T07:00:00Z"},
        {"trackId": 3, "genres": ["Games", "Arcade"], "averageUserRating": 4.1, "releaseDate": "2019-01-01T07:00:00Z"},
        {"trackId": 4, "genres": ["Games", "Puzzle"], "averageUserRating": 4.7, "releaseDate": "2018-01-01T07:00:00Z"},
    ]})
    return {"free": free, "grossing": grossing, "details": details}


def test_parse_chart_ranks_and_skips_bad_entries():
    payload = chart_payload([("A", "10"), ("B", "11")])
    payload["feed"]["entry"].append({"broken": True})
    games = parse_chart(payload, "free")
    assert [g["rank"] for g in games] == [1, 2]
    assert games[0]["id"] == "10"


def test_parse_reviews_ignores_app_entry():
    payload = {"feed": {"entry": [
        {"im:name": {"label": "App info, not a review"}},
        {"im:rating": {"label": "2"}, "title": {"label": "Too many ads"}, "content": {"label": "Ads every level"}},
    ]}}
    reviews = parse_reviews(payload)
    assert len(reviews) == 1 and reviews[0]["rating"] == 2


def test_market_table_crosses_charts():
    df = build_market_table(market(), today=TODAY)
    block = df[df["name"] == "Block Blast"].iloc[0]
    assert block["in_both"] and block["is_new"]
    assert block["main_genre"] == "Puzzle"          # store-level genres are dropped
    assert df.iloc[0]["name"] == "Block Blast"      # highest momentum first
    assert df["in_both"].sum() == 1


def test_genre_summary_and_signals():
    df = build_market_table(market(), today=TODAY)
    genres = genre_summary(df)
    puzzle = genres[genres["main_genre"] == "Puzzle"].iloc[0]
    assert puzzle["games"] == 2 and puzzle["in_grossing"] == 2
    signals = key_signals(df, genres)
    assert any("both" in s for s in signals)
    assert "Block Blast" in market_brief(df, genres)


def test_extract_json_handles_code_fences():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('[1, 2]') == [1, 2]


def test_check_evidence_flags_invented_games():
    concept = {"evidence": [{"game": "Block Blast", "signal": "x"}, {"game": "Made Up Saga", "signal": "y"}]}
    checked = check_evidence(concept, ["Block Blast", "Rope Rescue"])
    assert [e["verified"] for e in checked["evidence"]] == [True, False]
    assert checked["grounded_share"] == 0.5


def test_sample_reviews_is_bounded_and_balanced():
    reviews = [{"rating": r, "title": "", "text": "x" * i} for i in range(100) for r in (1, 5)]
    sample = sample_reviews(reviews, max_reviews=20)
    assert len(sample) <= 20
    assert {r["rating"] for r in sample} == {1, 5}


class FakeLLM:
    """Stands in for Gemini so the pipeline can be tested without a key."""
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def generate_json(self, prompt, system, temperature=0.4):
        self.prompts.append(prompt)
        return self.response


def test_concept_pipeline_with_fake_llm():
    llm = FakeLLM({"concepts": [{"title": "T", "evidence": [{"game": "Rope Rescue", "signal": "s"}]}]})
    concepts = generate_concepts(llm, "brief", {"Rope Rescue": {"hates": ["ads"]}}, ["Rope Rescue"], n=1,
                                 focus="Puzzle", designer_note="one thumb")
    assert concepts[0]["evidence"][0]["verified"]
    assert "FOCUS" in llm.prompts[0] and "one thumb" in llm.prompts[0]


def test_summarize_reviews_handles_no_reviews():
    assert summarize_reviews(FakeLLM({}), "X", [])["loves"] == []


def test_fetch_market_survives_missing_grossing_chart(monkeypatch):
    import scout.data as data

    def fake_chart(chart, country="us", limit=100):
        if chart == "grossing":
            raise data.DataError("feed down")
        return [{"id": "1", "name": "A", "developer": "", "chart": "free", "rank": 1}]

    monkeypatch.setattr(data, "fetch_chart", fake_chart)
    monkeypatch.setattr(data, "fetch_details", lambda ids, country="us": {})
    result = data.fetch_market()
    assert result["grossing"] == [] and len(result["free"]) == 1
    assert "grossing" in result["warnings"][0]

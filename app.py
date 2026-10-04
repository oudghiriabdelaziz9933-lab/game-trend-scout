"""Game Trend Scout: from App Store trends to grounded game concepts, in three steps."""
from __future__ import annotations

import os
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from scout.analysis import build_market_table, genre_summary, key_signals, market_brief
from scout.data import DataError, fetch_market, fetch_reviews
from scout.insights import generate_concepts, summarize_reviews
from scout.llm import DEFAULT_MODEL, GeminiClient, LLMError
from scout.snapshot import load_snapshot

load_dotenv()
st.set_page_config(page_title="Game Trend Scout", page_icon="🎮", layout="wide")

COUNTRIES = {"United States": "us", "United Kingdom": "gb", "France": "fr", "Germany": "de", "Japan": "jp"}


# ---------- data loading (cached so the App Store is not hit on every click) ----------
@st.cache_data(ttl=3600, show_spinner="Loading App Store charts...")
def load_live_market(country: str) -> dict:
    return fetch_market(country)


@st.cache_data(ttl=3600, show_spinner=False)
def load_reviews(app_id: str, country: str) -> list[dict]:
    return fetch_reviews(app_id, country)


def get_llm(api_key: str, model: str) -> GeminiClient | None:
    if not api_key:
        return None
    try:
        return GeminiClient(api_key, model)
    except LLMError as exc:
        st.error(str(exc))
        return None


# ---------- sidebar ----------
snapshot = load_snapshot()
with st.sidebar:
    st.title("🎮 Game Trend Scout")
    st.caption("Spot what works on the App Store, hear what players say, and turn it into new game concepts.")
    # Demo first when available: the app opens instantly, then one click switches to live data
    modes = ["Demo snapshot", "Live App Store data"] if snapshot else ["Live App Store data"]
    mode = st.radio("Data source", modes, help="Demo mode replays a saved run: no network or API key needed.")
    if mode == "Live App Store data":
        country_label = st.selectbox("Store", list(COUNTRIES))
        country = COUNTRIES[country_label]
    else:
        country = snapshot["country"]
        st.info(f"Snapshot of the {country.upper()} store taken on {snapshot['generated_at'][:10]}.")

    st.divider()
    api_key = st.text_input("Gemini API key", value=os.getenv("GEMINI_API_KEY", ""), type="password",
                            help="Free key from aistudio.google.com. Needed only for new AI analyses.")
    model = st.text_input("Gemini model", value=DEFAULT_MODEL)
    if not api_key:
        st.caption("No key: you can browse trends and the saved demo analyses.")

llm = get_llm(api_key, model)

# ---------- load and analyse the market ----------
state = st.session_state
source_key = f"{mode}-{country}"
if state.get("source_key") != source_key:
    state.source_key = source_key
    state.player_voice = dict(snapshot["player_voice"]) if mode == "Demo snapshot" else {}
    state.concepts = list(snapshot["concepts"]) if mode == "Demo snapshot" else []

try:
    if mode == "Demo snapshot":
        market = snapshot["market"]
        as_of = datetime.fromisoformat(snapshot["generated_at"])
    else:
        market = load_live_market(country)
        as_of = None
except DataError as exc:
    st.error(f"Could not reach the App Store ({exc}). Check your connection, or use the demo snapshot.")
    st.stop()

for warning in market.get("warnings", []):
    st.warning(warning)
df = build_market_table(market, today=as_of)
genres = genre_summary(df)
if df.empty:
    st.warning("The App Store returned no games. Try another store or the demo snapshot.")
    st.stop()

st.title("From App Store trends to your next game")
st.caption("See what is winning  →  hear what players say  →  generate concepts grounded in that evidence")
tab_trends, tab_voice, tab_concepts = st.tabs(["① Trends", "② Player voice", "③ Game concepts"])

# ---------- 1. Trends ----------
with tab_trends:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Games in the charts", len(df), help="Top 100 free + top 100 grossing games, deduplicated")
    c2.metric("In both charts", int(df["in_both"].sum()), help="Games that combine downloads and revenue")
    c3.metric("Released < 12 months", int(df["is_new"].sum()))
    c4.metric("Leading genre", genres.iloc[0]["main_genre"])

    st.subheader("What the data says")
    for signal in key_signals(df, genres):
        st.markdown(f"- {signal}")

    st.subheader("Where genres win: downloads vs revenue")
    chart_data = genres.head(12).melt(
        id_vars="main_genre", value_vars=["in_free", "in_grossing"], var_name="chart", value_name="count"
    )
    chart_data["chart"] = chart_data["chart"].map({"in_free": "Top free", "in_grossing": "Top grossing"})
    order = genres.head(12)["main_genre"].tolist()
    bars = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            y=alt.Y("main_genre:N", sort=order, title=None),
            x=alt.X("count:Q", title="Number of games in the chart"),
            yOffset="chart:N",
            color=alt.Color("chart:N", title=None, scale=alt.Scale(range=["#9CA3AF", "#2563EB"]),
                            legend=alt.Legend(orient="top")),
            tooltip=["main_genre", "chart", "count"],
        )
        .properties(height=420)
    )
    st.altair_chart(bars, use_container_width=True)
    st.caption("A genre with many free-chart games but few grossing ones has reach without monetisation: "
               "an opening for a better-monetised hybrid-casual take.")

    st.subheader("Games")
    f1, f2, f3 = st.columns([2, 1, 1])
    pick_genres = f1.multiselect("Genre", genres["main_genre"].tolist())
    only_both = f2.toggle("Only games in both charts")
    only_new = f3.toggle("Only new games")
    view = df.copy()
    if pick_genres:
        view = view[view["main_genre"].isin(pick_genres)]
    if only_both:
        view = view[view["in_both"]]
    if only_new:
        view = view[view["is_new"]]
    st.dataframe(
        view[["icon", "name", "main_genre", "rank_free", "rank_grossing", "rating", "rating_count",
              "release_date", "momentum", "url"]],
        hide_index=True,
        use_container_width=True,
        column_config={
            "icon": st.column_config.ImageColumn("", width="small"),
            "name": "Game",
            "main_genre": "Genre",
            "rank_free": st.column_config.NumberColumn("Free #", format="%d"),
            "rank_grossing": st.column_config.NumberColumn("Grossing #", format="%d"),
            "rating": st.column_config.NumberColumn("Rating", format="%.1f ⭐"),
            "rating_count": st.column_config.NumberColumn("Ratings", format="%d"),
            "release_date": "Released",
            "momentum": st.column_config.ProgressColumn("Momentum", min_value=0, max_value=2.3, format="%.2f",
                                                        help="Rank in both charts, plus a bonus for new games"),
            "url": st.column_config.LinkColumn("Store", display_text="Open"),
        },
    )

# ---------- 2. Player voice ----------
with tab_voice:
    st.markdown("Pick games and let the AI read their latest App Store reviews: "
                "what players love, hate and ask for.")
    default_games = df.head(3)["name"].tolist()
    chosen = st.multiselect("Games to analyse", df["name"].tolist(), default=default_games, max_selections=6)
    run_voice = st.button("Summarise reviews", type="primary", disabled=llm is None or not chosen)
    if llm is None:
        st.caption("Add a Gemini API key in the sidebar to analyse new games.")

    if run_voice:
        progress = st.progress(0.0)
        for i, name in enumerate(chosen):
            app_id = df.loc[df["name"] == name, "id"].iloc[0]
            with st.spinner(f"Reading reviews of {name}..."):
                try:
                    reviews = load_reviews(app_id, country)
                    state.player_voice[name] = summarize_reviews(llm, name, reviews)
                except (DataError, LLMError) as exc:
                    st.warning(f"{name}: {exc}")
            progress.progress((i + 1) / len(chosen))
        progress.empty()

    if not state.player_voice:
        st.info("No review analysis yet.")
    for name, s in state.player_voice.items():
        with st.container(border=True):
            st.markdown(f"#### {name}")
            meta = f"{s.get('reviews_used', '?')} reviews read · average {s.get('avg_review_rating', '?')}/5"
            st.caption(meta)
            st.markdown(f"**{s.get('verdict', '')}**")
            a, b, c = st.columns(3)
            a.markdown("**👍 Loves**\n" + "\n".join(f"- {x}" for x in s.get("loves", [])))
            b.markdown("**👎 Hates**\n" + "\n".join(f"- {x}" for x in s.get("hates", [])))
            c.markdown("**🙋 Asks for**\n" + "\n".join(f"- {x}" for x in s.get("requests", [])))
            if s.get("design_lesson"):
                st.success(f"Design lesson: {s['design_lesson']}")

# ---------- 3. Concepts ----------
with tab_concepts:
    st.markdown("Generate original casual / hybrid-casual concepts grounded in the charts "
                "and in the player voice above. Each concept cites the games that justify it.")
    g1, g2 = st.columns([1, 2])
    focus = g1.selectbox("Genre focus", ["Any genre"] + genres["main_genre"].tolist())
    n_concepts = g1.slider("Number of concepts", 1, 5, 3)
    note = g2.text_area("Designer brief (optional)",
                        placeholder="e.g. one-thumb controls, short sessions, works for a 35+ audience")
    if state.player_voice:
        g2.caption(f"Uses the player voice of {len(state.player_voice)} games from step ②.")
    run_concepts = st.button("Generate concepts", type="primary", disabled=llm is None)

    if run_concepts:
        with st.spinner("Designing concepts from the market data..."):
            try:
                state.concepts = generate_concepts(
                    llm, market_brief(df, genres), state.player_voice, df["name"].tolist(),
                    n=n_concepts, focus=focus, designer_note=note,
                )
            except LLMError as exc:
                st.error(str(exc))

    if not state.concepts:
        st.info("No concepts yet." + ("" if llm else " Add a Gemini API key in the sidebar to generate them."))

    for concept in state.concepts:
        with st.container(border=True):
            head, score = st.columns([5, 1])
            head.markdown(f"### {concept.get('title', 'Untitled')}")
            head.markdown(f"*{concept.get('pitch', '')}*")
            score.metric("Opportunity", f"{concept.get('opportunity_score', '?')}/10")
            left, right = st.columns(2)
            left.markdown(f"**Genre:** {concept.get('genre', '')}  \n**Core mechanic:** {concept.get('core_mechanic', '')}")
            left.markdown("**Game loop**\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(concept.get("game_loop", []), 1)))
            left.markdown(f"**Twist:** {concept.get('twist', '')}")
            right.markdown("**Why now: market evidence**")
            for ev in concept.get("evidence", []):
                mark = "✅" if ev.get("verified") else "⚠️ not found in the data"
                right.markdown(f"- **{ev.get('game', '')}** {mark}: {ev.get('signal', '')}")
            right.markdown(f"**Main risk:** {concept.get('main_risk', '')}")

    if state.concepts:
        lines = []
        for c in state.concepts:
            lines += [f"## {c.get('title')}", c.get("pitch", ""), "", f"Core mechanic: {c.get('core_mechanic', '')}",
                      "Game loop:"] + [f"- {s}" for s in c.get("game_loop", [])] + [
                      f"Twist: {c.get('twist', '')}", "Evidence:"] + [
                      f"- {e.get('game')}: {e.get('signal')}" for e in c.get("evidence", [])] + [
                      f"Main risk: {c.get('main_risk', '')}", ""]
        st.download_button("Download concepts (Markdown)", "\n".join(lines), file_name="game_concepts.md")

st.caption("Data: public Apple App Store feeds (top charts, Lookup API, customer reviews). AI: Google Gemini.")

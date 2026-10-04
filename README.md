# Game Trend Scout

**From App Store trends to your next game, in three steps.**

Game Trend Scout helps a game designer turn the daily App Store charts into new game ideas:

1. **Trends:** it crosses the US top 100 free games with the top 100 grossing games, groups them by genre and surfaces plain-language signals (games that win on both downloads and revenue, recent hits, genres with reach but weak monetisation).
2. **Player voice:** the AI reads the latest App Store reviews of the games you pick and summarises what players love, hate and ask for.
3. **Game concepts:** the AI proposes original casual / hybrid-casual concepts (pitch, core mechanic, game loop, twist). Each concept cites the games and reviews that justify it, and the app checks that every cited game really exists in the data.

Built for the Blitz Games (Voodoo) Operations Engineer case study, Option A.

---

## How to run it

**Fastest: no install.** On the GitHub page, click **Code → Codespaces → Create codespace on main**. The environment installs itself and the app opens in a preview tab after about two minutes. Add your Gemini key in the app sidebar.

**Locally:** you need **Python 3.10+** and, for the AI features, a **free Google Gemini API key**.

### 1. Get the code and install

```bash
git clone https://github.com/<your-account>/game-trend-scout.git
cd game-trend-scout
python -m venv .venv
# Windows:     .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Add your Gemini key (optional but recommended)

Create a free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey), then copy `.env.example` to `.env` and paste it:

```
GEMINI_API_KEY=your-key-here
```

You can also paste the key in the app sidebar instead.

### 3. Launch

```bash
streamlit run app.py
```

The app opens at http://localhost:8501. One-click launchers create the environment, install everything and start the app: **`run.command` on macOS** (double-click; if macOS blocks it, right-click → Open) and **`run.bat` on Windows**.

### Demo mode: no key, no network

When `data/demo_snapshot.json` exists, the app opens on it: a real run of the US App Store with its AI analyses, saved so that the whole product can be reviewed in seconds without any key or connection. Switch to **Live App Store data** in the sidebar to fetch today's charts.

To create or refresh the snapshot:

```bash
python3 build_demo.py           # charts + AI analyses (needs a key)
python3 build_demo.py --no-ai   # charts only, no key needed
```

### Tests

```bash
pytest
```

The tests run fully offline: parsers, market analysis and the AI pipeline (with a fake model).

---

## Key decisions

### Product

- **One job, one flow.** The target moment is a designer's weekly trend review that should end with an idea worth prototyping. The three tabs follow that path: *what is winning → why players care → what we could build*. I left out features that do not serve that path (clustering, multi-country comparison) to ship a complete flow in the time box.
- **Free + grossing, crossed.** Downloads alone say what is viral; revenue alone says what monetises. A game in both charts is the strongest signal, and a genre with many free games but few grossing ones points to an opening for a better-monetised hybrid-casual take. That is the Voodoo playbook, so the analysis is built around it.
- **Concepts shaped for Voodoo.** The AI is briefed as a casual / hybrid-casual designer: instant understanding, one-hand play, short sessions, cheap to prototype and easy to test with video ads.
- **Evidence over inspiration.** A concept is only useful if the designer can defend it. Each concept must cite the games and player feedback behind it, and those citations are verified against the data (✅ / ⚠️). This turns a creative AI output into something reviewable.
- **Demo-first.** Reviewers and stakeholders should see the value before setting anything up, so the app opens on a saved real run.

### Technical

- **Data: Apple's public feeds only.** iTunes RSS top charts (filtered on the Games genre), the iTunes Lookup API for genres, ratings and release dates, and the customer-reviews RSS feed. They are free, need no key and no scraping, which keeps the project legal and easy to run.
- **Deterministic analysis first, AI second.** Ranks, genre counts, momentum and signals are computed in plain Python (`scout/analysis.py`), so they are exact and testable. The AI only does what code cannot: reading hundreds of reviews and inventing concepts. The AI receives a compact market brief generated from that analysis, which grounds it in real data.
- **Gemini, free tier.** Good quality, generous free quota, simple key. Outputs are requested as JSON so the app can render and check them. Calls retry on rate limits and malformed JSON.
- **Hallucination guardrail.** `check_evidence` flags any concept that cites a game missing from the charts.
- **Cost and quota control.** Reviews are sampled (max 60 per game, balanced between positive and negative) and App Store calls are cached for an hour.
- **Streamlit.** A full interactive app in one Python file, launched with one command: the fastest way to ship a usable tool in a few hours.
- **AI coding assistant.** The code was written with an AI coding assistant, used to scaffold modules, write tests and iterate on the UI, while I drove the product decisions and reviewed the output.

### Assumptions

- The user is a game designer or product manager at a casual / hybrid-casual publisher, looking at the US market.
- The top 100 of each chart is a good enough proxy for "what works now"; a game's genre is the first App Store sub-genre that describes gameplay.
- "New" means released in the last 12 months.

---

## Known limitations

- **Charts are a snapshot, not a trend.** Without stored history, the app cannot show which games are *rising*; "momentum" is a proxy based on today's ranks and release dates.
- **App Store genres are coarse.** "Puzzle" covers match-3, block puzzles and sort games alike; real mechanics are not extracted yet.
- **Reviews are recent and limited.** Apple's feed exposes only the latest reviews (up to 500 per game; the app reads 100), skewed toward the current version and toward unhappy players.
- **AI output varies.** Concepts change between runs and the opportunity score is the model's judgement, not a forecast. The evidence check verifies that cited games exist, not that every claim about them is right.
- **Free-tier limits.** Heavy use can hit Gemini's per-minute quota; the app retries, then shows an error.
- **No downloads or revenue figures.** Public feeds give ranks, not volumes.

---

## What I would build with one more week

1. **History and real momentum:** a daily scheduled job storing the charts, to show rank changes, breakouts and how long games stay in the top.
2. **Mechanic extraction:** use the AI on store descriptions and screenshots to tag each game's core mechanics (merge, sort, tap-timing, idle...), then cluster games by mechanic rather than by store genre.
3. **Opportunity map:** a demand vs satisfaction view per mechanic (chart presence vs review sentiment) to point at underserved niches.
4. **Concept validation loop:** generate an ad-test brief, a one-page GDD and a prototype scope for a chosen concept, and let designers rate concepts to improve the prompts.
5. **More markets and stores:** multi-country comparison (spot a trend before it reaches the US) and Google Play.
6. **Evaluation:** a small benchmark of review summaries checked by a human, to measure and improve AI quality.

---

## Project structure

```
app.py               Streamlit interface (3 tabs)
build_demo.py        Refreshes the demo snapshot with live data and AI
scout/data.py        App Store feeds: charts, details, reviews
scout/analysis.py    Market table, genre summary, signals, market brief
scout/insights.py    Review synthesis, concept generation, evidence check
scout/llm.py         Gemini wrapper returning parsed JSON
scout/snapshot.py    Save / load the demo snapshot
tests/               Offline tests (pytest)
```

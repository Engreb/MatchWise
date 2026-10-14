# Matchwise

A personal football prediction app for the Premier League, La Liga, Serie A, Bundesliga and Ligue 1.

## Using it

1. **Update predictions:** double-click `update.bat`. It downloads the latest results and odds from football-data.co.uk and the season schedules from fixturedownload.com, then refits the model. It takes about 10 seconds. Run it before each round of matches.
2. **Open the app:** double-click `start-app.bat`, which opens http://localhost:8770.

## How it works

- `engine/` is the Python prediction engine.
  - `matchwise/data.py` downloads and parses results, odds and fixtures.
  - `matchwise/model.py` is the Dixon–Coles model: team attack and defence ratings, home advantage and a low-score correction. Recent matches carry more weight.
  - `matchwise/backtest.py` replays past seasons week by week, using only earlier results, to measure real accuracy.
  - `matchwise/pipeline.py` fits the current models and writes `app/data/*.json`.
- `app/` is the web app (plain HTML, CSS and JavaScript). It only displays what the engine produced.
- `prototype/` is the original design prototype, which uses sample data.

## Commands (run in `engine/`)

```
..\.venv\Scripts\python -m matchwise update     # refresh data + predictions
..\.venv\Scripts\python -m matchwise backtest   # re-tune and re-test on past seasons (~2 min)
..\.venv\Scripts\python -m pytest               # model tests
```

## Accuracy (held-out 2024–25 and 2025–26, 3,504 matches)

| | Log loss | Top pick correct |
|---|---|---|
| Model only (70% goals, 30% shots on target) | 0.988 | 52.3% |
| Model only, goals-based ratings | 0.989 | 52.3% |
| Model + pre-match odds (odds-adjusted) | 0.972 | 53.5% |
| Bookmaker pre-match odds | 0.971 | 53.5% |
| Bookmaker closing odds | 0.969 | 54.1% |
| League averages | 1.077 | 43.0% |

The probabilities are well calibrated (average gap 1%). The model uses results only, so it doesn't know about injuries or team news.

When bookmaker odds are published for a fixture (usually a few days before), the app shows an **odds-adjusted** prediction. It combines the model with the pre-match odds (weights tuned on 2023–24: 100% odds for home/draw/away, 80% for over/under 2.5), then refits one coherent score distribution so every market agrees. "Model only" stays available on the match page.

Team names in the schedule are mapped explicitly in `engine/matchwise/teams.py`. An unknown name is reported during the update and that fixture shows as "unable to assess" until it's added.

## Team news

Premier League injuries, suspensions and doubts come from the official Fantasy Premier League data. They appear on each Premier League match page for context only; they are not used in predictions yet. Each update archives them in `engine/data/news/` so their value can be tested later.

## Promoted teams

A promoted side starts at the average rating of the teams relegated from that league and updates as results come in. Ratings based on little data are flagged as "Limited data" in the app.

## Saved predictions

Each `update` stores the upcoming-fixture predictions in `engine/data/snapshots/`. Once those matches are played, the "This season" page shows the saved pre-kick-off prediction instead of a replay.

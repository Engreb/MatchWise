# Matchwise

A personal football prediction app covering 19 European leagues: the top five (Premier League, La Liga, Serie A, Bundesliga, Ligue 1), the Championship, League One, League Two, Scottish Premiership and Championship, Eredivisie, Primeira Liga, 2. Bundesliga, Serie B, Segunda División, Ligue 2, Süper Lig, Belgian Pro League and Greek Super League.

## Using it

**Online:** https://engreb.github.io/MatchWise/ (updates itself every morning at 06:00 UTC via GitHub Actions).

**On your PC:**


1. **Update predictions:** double-click `update.bat`. It downloads the latest results and odds from football-data.co.uk and the season schedules from fixturedownload.com, then refits the model. It takes about 10 seconds. Run it before each round of matches.
2. **Open the app:** double-click `start-app.bat`, which opens http://localhost:8770.

## How it works

- `engine/` is the Python prediction engine.
  - `matchwise/data.py` downloads and parses results, odds and fixtures.
  - `matchwise/model.py` is the Dixon–Coles model: team attack and defence ratings, home advantage and a low-score correction. Recent matches carry more weight. Ratings are fitted to 50% goals + 50% xG in the top five leagues (xG history from Understat) and 70% goals + 30% shots on target elsewhere.
  - `matchwise/backtest.py` replays past seasons week by week, using only earlier results, to measure real accuracy.
  - `matchwise/pipeline.py` fits the current models and writes `app/data/*.json`.
  - `matchwise/pages.py` writes a static page per upcoming fixture (`app/m/…`), an index and `app/sitemap.xml`, so predictions are visible to search engines and link previews. They're rebuilt on every update and not committed.
  - `matchwise/strategies.py` is the betting backtest (1X2 and over/under 2.5) shown on the Model accuracy page.
  - `matchwise/injuries.py` is a one-off test of whether team news improves predictions (see below).
- `app/` is the web app (plain HTML, CSS and JavaScript). It only displays what the engine produced.
- `prototype/` is the original design prototype, which uses sample data.

## Commands (run in `engine/`)

```
..\.venv\Scripts\python -m matchwise update     # refresh data + predictions
..\.venv\Scripts\python -m matchwise backtest   # re-tune and re-test on past seasons (~2 min)
..\.venv\Scripts\python -m matchwise injuries   # re-run the team-news test (needs API_FOOTBALL_KEY)
..\.venv\Scripts\python -m pytest               # model tests
```

## Accuracy (held-out 2024–25 and 2025–26, 13,503 matches in 19 leagues)

| | Log loss | Top pick correct | Over 2.5 log loss |
|---|---|---|---|
| Model only | 1.014 | 49.3% | 0.685 |
| Model only, goals-based ratings | 1.017 | 49.2% | 0.688 |
| Model + pre-match odds (odds-adjusted) | 0.999 | 50.8% | 0.679 |
| Bookmaker pre-match odds | 0.998 | 50.8% | 0.678 |
| Bookmaker closing odds | 0.995 | 51.2% | 0.676 |
| League averages | 1.078 | 43.4% | 0.692 |

Settings are tuned on 2023–24 in the original nine leagues only; the ten leagues added in October 2026 are a fully out-of-sample test. Lower divisions are harder for everyone, which is why these figures are lower than the earlier nine-league numbers (0.988 log loss, 52.3% top pick).

Home/draw/away probabilities are well calibrated (average gap 0.7%). Over/under 2.5 and both-teams-to-score from the model alone are less so (gaps 2.0% and 2.0%): it is too sure about low-scoring games. Pulling each match's expected total goals 10% of the way towards the league's average over the past year (chosen on 2023–24) narrowed those gaps from 2.6% and 2.3% and cut held-out log loss by 0.0007 (over 2.5) and 0.0005 (both teams to score), both 95% intervals below zero, with home/draw/away unchanged; a bigger pull made log loss worse, so the gap isn't fully closed. Once odds are published, the odds-adjusted goals figures are well calibrated (0.8%).

**Betting:** every strategy tested lost money at typical prices, for 1X2 and for over/under 2.5 (the app's top pick −4.5%, its over/under lean −6.2%, "value" bets worse). The predictions are for understanding matches, not choosing bets.

**Team news:** `python -m matchwise injuries` tests whether knowing who is missing helps, using API-Football injury lists for the top five leagues in 2022–23 to 2024–25 (fitted on 2022–23, tested on the other two). Each extra missing player, compared with the team's usual, was worth about 1.7% of its goals and improved model-only log loss by 0.0018 (95% interval 0.0000 to 0.0036): a borderline gain. It isn't in the model, because there's no free live source outside the Premier League and the past lists may include late withdrawals.

When bookmaker odds are published for a fixture (usually a few days before), the app shows an **odds-adjusted** prediction. It combines the model with the pre-match odds (weights tuned on 2023–24: 100% odds for home/draw/away and for over/under 2.5), then refits one coherent score distribution so every market agrees. "Model only" stays available on the match page.

Thirteen leagues have full-season schedules from fixturedownload.com: the top five, the Championship, League One, League Two, Scottish Premiership, Eredivisie, Primeira Liga, Ligue 2 and Süper Lig. The others (2. Bundesliga, Serie B, Segunda, Belgium, Greece, Scottish Championship) only list fixtures once football-data.co.uk publishes them, usually a few days ahead, and their projected tables assume every team still plays every remaining opponent. In Belgium and Greece the projection covers the regular season only.

Team names in the schedule are mapped explicitly in `engine/matchwise/teams.py`. An unknown name is reported during the update and that fixture shows as "unable to assess" until it's added.

## Tables and projections

Each update simulates the rest of every league season 10,000 times from the model's predictions (allowing team strength to drift over the season) to give projected points and title, top-4/promotion and relegation chances, plus each team's chance of finishing in every position. Code: `engine/matchwise/projections.py`.

## Team news

Premier League injuries, suspensions and doubts come from the official Fantasy Premier League data. They appear on each Premier League match page for context only; they are not used in predictions yet. Each update archives them in `engine/data/news/` so their value can be tested later.

## Promoted teams

A promoted side starts at the average rating of the teams relegated from that league and updates as results come in. Ratings based on little data are flagged as "Limited data" in the app.

## Saved predictions

Each `update` stores the upcoming-fixture predictions in `engine/data/snapshots/`. Once those matches are played, the "This season" page shows the saved pre-kick-off prediction instead of a replay.

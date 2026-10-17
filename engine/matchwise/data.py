"""Download and parse football-data.co.uk results, odds and fixtures."""
from __future__ import annotations

import csv
import io
import json
import socket
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
UK = ZoneInfo("Europe/London")

# football-data division code -> (app key, display name)
LEAGUES = {
    "E0": ("epl", "Premier League"),
    "SP1": ("laliga", "La Liga"),
    "I1": ("seriea", "Serie A"),
    "D1": ("bundesliga", "Bundesliga"),
    "F1": ("ligue1", "Ligue 1"),
    "E1": ("championship", "Championship"),
    "SC0": ("scotland", "Scottish Premiership"),
    "N1": ("eredivisie", "Eredivisie"),
    "P1": ("portugal", "Primeira Liga"),
}
SEASONS = ["2021", "2122", "2223", "2324", "2425", "2526", "2627"]
CURRENT_SEASON = SEASONS[-1]

RESULTS_URL = "https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"
FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"
# Full-season schedules (football-data only lists the next few days' fixtures).
SCHEDULE_URL = "https://fixturedownload.com/feed/json/{slug}-20{yy}"
SCHEDULE_SLUGS = {"E0": "epl", "SP1": "la-liga", "I1": "serie-a", "D1": "bundesliga", "F1": "ligue-1",
                  "E1": "championship", "SC0": "scottish-premiership", "N1": "eredivisie", "P1": "primeira-liga"}


@dataclass
class Match:
    div: str
    season: str
    date: date
    kickoff_utc: datetime | None
    home: str
    away: str
    hg: int | None = None
    ag: int | None = None
    hst: int | None = None  # shots on target
    ast: int | None = None
    hxg: float | None = None  # expected goals (football-data this season, Understat before)
    axg: float | None = None
    # Margin-free implied probabilities from average bookmaker odds, when available.
    market_open: tuple[float, float, float] | None = None
    market_close: tuple[float, float, float] | None = None
    market_o25_close: float | None = None
    market_o25_open: float | None = None
    odds_avg: tuple[float, float, float] | None = None
    odds_skybet: tuple[float, float, float] | None = None
    odds_max: tuple[float, float, float] | None = None  # best pre-match price across bookmakers
    odds_b365: tuple[float, float, float] | None = None
    extra: dict = field(default_factory=dict)

    @property
    def played(self) -> bool:
        return self.hg is not None and self.ag is not None


_getaddrinfo = socket.getaddrinfo


def _ipv4_first(*args, **kwargs):
    # Some networks advertise IPv6 but stall on it; Python then waits for the full timeout
    # before falling back. Trying IPv4 addresses first avoids a ~30 s delay per request.
    return sorted(_getaddrinfo(*args, **kwargs), key=lambda a: a[0] != socket.AF_INET)


socket.getaddrinfo = _ipv4_first


def _fetch(url: str, timeout: int = 30, attempts: int = 3) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "matchwise-personal/0.1"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def download(force_current: bool = True, log=print) -> None:
    """Fetch season files (cached; the current season and fixtures are always refreshed)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for season in SEASONS:
        for div in LEAGUES:
            path = RAW_DIR / f"{season}_{div}.csv"
            if path.exists() and not (force_current and season == CURRENT_SEASON):
                continue
            log(f"  downloading {season} {div}")
            path.write_bytes(_fetch(RESULTS_URL.format(season=season, div=div)))
    log("  downloading fixtures")
    (RAW_DIR / "fixtures.csv").write_bytes(_fetch(FIXTURES_URL))
    download_understat(log)
    for div, slug in SCHEDULE_SLUGS.items():
        log(f"  downloading {slug} schedule")
        try:
            (RAW_DIR / f"schedule_{CURRENT_SEASON}_{div}.json").write_bytes(
                _fetch(SCHEDULE_URL.format(slug=slug, yy=CURRENT_SEASON[:2]), timeout=15, attempts=1))
        except Exception as e:
            # Schedules change rarely, so the saved copy is fine; if the site is down, don't
            # spend minutes timing out on every league.
            log(f"    schedule site unreachable ({type(e).__name__}); using saved schedules")
            break


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _float(row: dict, key: str) -> float | None:
    v = (row.get(key) or "").strip()
    try:
        f = float(v)
        return f if f > 1.0 else None
    except ValueError:
        return None


def _triple(row: dict, keys: tuple[str, str, str]) -> tuple[float, float, float] | None:
    vals = [_float(row, k) for k in keys]
    if any(v is None for v in vals):
        return None
    return tuple(vals)  # type: ignore[return-value]


def implied(odds: tuple[float, ...] | None) -> tuple[float, ...] | None:
    """Remove the bookmaker margin by normalising inverse odds of a complete outcome set."""
    if not odds:
        return None
    inv = [1.0 / o for o in odds]
    s = sum(inv)
    return tuple(i / s for i in inv)


def _parse_date(s: str) -> date:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"bad date {s!r}")


def _kickoff(d: date, t: str) -> datetime | None:
    t = (t or "").strip()
    if not t:
        return None
    hh, mm = t.split(":")[:2]
    local = datetime(d.year, d.month, d.day, int(hh), int(mm), tzinfo=UK)
    return local.astimezone(timezone.utc)


def _row_to_match(row: dict, div: str, season: str, with_result: bool) -> Match | None:
    if not row.get("HomeTeam") or not row.get("Date"):
        return None
    d = _parse_date(row["Date"])
    m = Match(div=div, season=season, date=d, kickoff_utc=_kickoff(d, row.get("Time", "")),
              home=row["HomeTeam"].strip(), away=row["AwayTeam"].strip())
    if with_result:
        try:
            m.hg, m.ag = int(row["FTHG"]), int(row["FTAG"])
        except (KeyError, ValueError, TypeError):
            return None
        try:
            m.hst, m.ast = int(row["HST"]), int(row["AST"])
        except (KeyError, ValueError, TypeError):
            pass
    avg = _triple(row, ("AvgH", "AvgD", "AvgA"))
    m.odds_avg = avg
    m.market_open = implied(avg)
    m.market_close = implied(_triple(row, ("AvgCH", "AvgCD", "AvgCA")))
    o, u = _float(row, "AvgC>2.5"), _float(row, "AvgC<2.5")
    if o and u:
        m.market_o25_close = implied((o, u))[0]
    o, u = _float(row, "Avg>2.5"), _float(row, "Avg<2.5")
    if o and u:
        m.market_o25_open = implied((o, u))[0]
    m.odds_skybet = _triple(row, ("SKBH", "SKBD", "SKBA"))
    m.odds_max = _triple(row, ("MaxH", "MaxD", "MaxA"))
    m.odds_b365 = _triple(row, ("B365H", "B365D", "B365A"))
    if row.get("HxG") and row.get("AxG"):
        m.extra["xg"] = (row["HxG"], row["AxG"])
        try:
            m.hxg, m.axg = float(row["HxG"]), float(row["AxG"])
        except ValueError:
            pass
    return m


def load_results(div: str) -> list[Match]:
    out: list[Match] = []
    for season in SEASONS:
        path = RAW_DIR / f"{season}_{div}.csv"
        if not path.exists():
            continue
        for row in csv.DictReader(io.StringIO(_decode(path.read_bytes()))):
            m = _row_to_match(row, div, season, with_result=True)
            if m:
                out.append(m)
    out.sort(key=lambda m: (m.date, m.kickoff_utc or datetime.min.replace(tzinfo=timezone.utc), m.home))
    attach_understat_xg(div, out)
    return out


# ---------- Understat xG history (top five leagues; football-data only has xG from 2026-27) ----------
UNDERSTAT_LEAGUES = {"E0": "EPL", "SP1": "La_liga", "I1": "Serie_A", "D1": "Bundesliga", "F1": "Ligue_1"}
UNDERSTAT_URL = "https://understat.com/getLeagueData/{league}/{year}"


def download_understat(log=print) -> None:
    """Fetch past seasons' match xG once (cached; past seasons never change)."""
    import gzip
    for div, league in UNDERSTAT_LEAGUES.items():
        for season in SEASONS[:-1]:
            path = RAW_DIR / f"understat_{season}_{div}.json"
            if path.exists():
                continue
            year = "20" + season[:2]
            req = urllib.request.Request(UNDERSTAT_URL.format(league=league, year=year), headers={
                "User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest",
                "Referer": f"https://understat.com/league/{league}/{year}"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read()
                data = json.loads(gzip.decompress(raw) if raw[:2] == bytes([0x1F, 0x8B]) else raw)
                rows = [{"h": x["h"]["title"], "a": x["a"]["title"], "dt": x["datetime"],
                         "hxg": float(x["xG"]["h"]), "axg": float(x["xG"]["a"])}
                        for x in data["dates"] if x.get("isResult") and x["xG"]["h"] is not None]
                path.write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
                log(f"  Understat xG {league} {year}: {len(rows)} matches")
            except Exception as e:
                log(f"  Understat xG {league} {year} unavailable ({type(e).__name__}); continuing without it")


def attach_understat_xg(div: str, matches: list[Match], log=None) -> int:
    """Copy Understat xG onto past-season matches that lack it. Names are mapped explicitly
    (teams.py); an unmatched match simply has no xG and falls back to goals + shots."""
    if div not in UNDERSTAT_LEAGUES:
        return 0
    from .teams import canonical
    attached = 0
    by_season: dict[str, dict] = {}
    for m in matches:
        by_season.setdefault(m.season, {})[(m.date, m.home, m.away)] = m
    for season, idx in by_season.items():
        path = RAW_DIR / f"understat_{season}_{div}.json"
        if not path.exists():
            continue
        known = {t for (_, h, a) in idx for t in (h, a)}
        for x in json.loads(path.read_text(encoding="utf-8")):
            h, a = canonical(x["h"], known), canonical(x["a"], known)
            if not h or not a:
                continue
            ko = datetime.strptime(x["dt"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            d0 = ko.astimezone(UK).date()
            for d in (d0, d0 - timedelta(days=1), d0 + timedelta(days=1)):
                m = idx.get((d, h, a))
                if m is not None:
                    if m.hxg is None:
                        m.hxg, m.axg = x["hxg"], x["axg"]
                        attached += 1
                    break
    return attached


def load_schedule(div: str, include_played: bool = False) -> list[dict]:
    """Fixtures from the season schedule (unplayed only by default): raw names, UTC kick-off."""
    path = RAW_DIR / f"schedule_{CURRENT_SEASON}_{div}.json"
    if not path.exists():
        return []
    out = []
    for x in json.loads(path.read_text(encoding="utf-8")):
        if x.get("HomeTeamScore") is not None and not include_played:
            continue
        ko = datetime.strptime(x["DateUtc"].replace("Z", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        out.append({"home": x["HomeTeam"], "away": x["AwayTeam"], "kickoff_utc": ko,
                    "date": ko.astimezone(UK).date(), "round": x.get("RoundNumber"),
                    "hg": x.get("HomeTeamScore"), "ag": x.get("AwayTeamScore")})
    out.sort(key=lambda f: f["kickoff_utc"])
    return out


def load_fixtures() -> list[Match]:
    path = RAW_DIR / "fixtures.csv"
    if not path.exists():
        return []
    out = []
    for row in csv.DictReader(io.StringIO(_decode(path.read_bytes()))):
        div = (row.get("Div") or "").strip()
        if div not in LEAGUES:
            continue
        m = _row_to_match(row, div, CURRENT_SEASON, with_result=False)
        if m:
            out.append(m)
    out.sort(key=lambda m: (m.kickoff_utc or datetime.combine(m.date, datetime.min.time(), timezone.utc)))
    return out

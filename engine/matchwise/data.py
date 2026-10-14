"""Download and parse football-data.co.uk results, odds and fixtures."""
from __future__ import annotations

import csv
import io
import json
import socket
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
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
}
SEASONS = ["2021", "2122", "2223", "2324", "2425", "2526", "2627"]
CURRENT_SEASON = SEASONS[-1]

RESULTS_URL = "https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"
FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"
# Full-season schedules (football-data only lists the next few days' fixtures).
SCHEDULE_URL = "https://fixturedownload.com/feed/json/{slug}-20{yy}"
SCHEDULE_SLUGS = {"E0": "epl", "SP1": "la-liga", "I1": "serie-a", "D1": "bundesliga", "F1": "ligue-1"}


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
    # Margin-free implied probabilities from average bookmaker odds, when available.
    market_open: tuple[float, float, float] | None = None
    market_close: tuple[float, float, float] | None = None
    market_o25_close: float | None = None
    market_o25_open: float | None = None
    odds_avg: tuple[float, float, float] | None = None
    odds_skybet: tuple[float, float, float] | None = None
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
    if row.get("HxG") and row.get("AxG"):
        m.extra["xg"] = (row["HxG"], row["AxG"])
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
    return out


def load_schedule(div: str) -> list[dict]:
    """Unplayed fixtures from the season schedule: raw names, UTC kick-off."""
    path = RAW_DIR / f"schedule_{CURRENT_SEASON}_{div}.json"
    if not path.exists():
        return []
    out = []
    for x in json.loads(path.read_text(encoding="utf-8")):
        if x.get("HomeTeamScore") is not None:
            continue
        ko = datetime.strptime(x["DateUtc"].replace("Z", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        out.append({"home": x["HomeTeam"], "away": x["AwayTeam"], "kickoff_utc": ko,
                    "date": ko.astimezone(UK).date(), "round": x.get("RoundNumber")})
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

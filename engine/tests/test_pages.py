from matchwise import pages


def _fixture(**kw):
    grid = [0.0] * 36
    grid[1 * 6 + 1] = 0.13  # 1-1 most likely
    model = [1.2, 1.2, 0.38, 0.28, 0.34, 0.9, 0.7, 0.43, 0.2, 0.1, 0.49, *grid]
    return {"league": "seriea", "date": "2026-10-24", "kickoff": "2026-10-24T16:00:00Z", "home": "Napoli",
            "away": "Roma", "assessable": True, "model": model, "blend": None, **kw}


def test_slug_folds_accents_and_punctuation():
    assert pages.slug("Nott'm Forest") == "nott-m-forest"
    assert pages.slug("Fenerbahçe") == "fenerbahce"


def test_match_page_carries_the_prediction():
    html = pages.match_page(_fixture(), "Serie A")
    assert "<title>Napoli vs Roma prediction, Serie A · Matchwise</title>" in html
    assert "Napoli 38%, draw 28%, Roma 34%" in html
    assert "1–1" in html and "17:00 UK time" in html  # kick-off shown in UK time (BST)
    assert "#/match/seriea/Napoli/Roma" in html


def test_write_skips_started_and_unassessable(tmp_path):
    rows = [_fixture(), _fixture(home="Inter", status="started"), _fixture(home="Milan", assessable=False, model=None)]
    n = pages.write(tmp_path, rows, {"seriea": "Serie A"}, "2026-10-19T06:00:00Z", log=lambda *_: None)
    assert n == 1
    assert (tmp_path / "m" / "seriea" / "napoli-vs-roma-2026-10-24.html").exists()
    assert (tmp_path / "sitemap.xml").read_text().count("<url>") == 3

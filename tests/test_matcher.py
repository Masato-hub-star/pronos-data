"""Tests for ratingbet_matcher.py."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ratingbet_matcher import match_events, build_merged_view


def _make_rb_match(home, away, slug="", league="Test League"):
    return {
        "match_id": slug or f"{home.lower().replace(' ','-')}-vs-{away.lower().replace(' ','-')}",
        "home_team": home,
        "away_team": away,
        "date": "2026-09-20",
        "time_utc": "",
        "time_paris": "15:00",
        "league": league,
        "markets": {
            "result": {
                "W1": {"odd": 1.5, "prob_pct": 60},
                "X": {"odd": None, "prob_pct": None},
                "W2": {"odd": None, "prob_pct": None},
            },
            "total_25": {
                "over": {"odd": 1.7, "prob_pct": 55},
                "under": {"odd": None, "prob_pct": None},
            },
            "btts": {
                "yes": {"odd": 1.8, "prob_pct": 50},
                "no": {"odd": None, "prob_pct": None},
            },
        },
        "best_tip": {"market": "Result", "outcome": "W1", "odd": 1.5},
    }


def _make_fs_event(home, away, mid="ABC123", competition="Test Cup"):
    return {
        "sport": "football",
        "competition": competition,
        "date": "2026-09-20",
        "time_paris": "15:00",
        "participants": [home, away],
        "mid": mid,
        "url": f"https://www.flashscore.fr/match/{mid}/",
        "preview_available": True,
        "preview_full_text": f"Preview of {home} vs {away}. This is a long text for testing."
    }


class TestMatchEvents:
    def test_matched_exact_names(self):
        rb = [_make_rb_match("Manchester City", "Sunderland")]
        fs = [_make_fs_event("Manchester City", "Sunderland")]
        results = match_events(rb, fs)
        assert len(results) == 1
        assert results[0]["status"] == "MATCHED"
        assert results[0]["fs_event"] is not None

    def test_matched_via_normalization(self):
        rb = [_make_rb_match("Olympique Lyonnais", "Stade Rennais")]
        fs = [_make_fs_event("Olympique Lyonnais", "Stade Rennais")]
        results = match_events(rb, fs)
        assert results[0]["status"] == "MATCHED"

    def test_matched_alias(self):
        rb = [_make_rb_match("Man City", "Sunderland")]
        fs = [_make_fs_event("Manchester City", "Sunderland")]
        results = match_events(rb, fs)
        assert results[0]["status"] == "MATCHED"

    def test_matched_cross_home_away_swap(self):
        rb = [_make_rb_match("Juventus", "Atalanta", slug="atalanta-vs-juventus-2")]
        fs = [_make_fs_event("Atalanta", "Juventus")]
        results = match_events(rb, fs)
        assert results[0]["status"] == "MATCHED"

    def test_matched_via_slug_normalization(self):
        rb = [_make_rb_match("FC Porto", "Benfica", slug="benfica-vs-fc-porto")]
        fs = [_make_fs_event("SL Benfica", "FC Porto")]
        results = match_events(rb, fs)
        assert results[0]["status"] == "MATCHED"

    def test_ambiguous_one_team_match(self):
        rb = [_make_rb_match("Manchester City", "Liverpool")]
        fs = [_make_fs_event("Manchester City", "Arsenal")]
        results = match_events(rb, fs)
        assert results[0]["status"] == "AMBIGUOUS"
        assert results[0]["fs_event"] is None

    def test_unmatched(self):
        rb = [_make_rb_match("Barcelona", "Real Madrid")]
        fs = [_make_fs_event("Manchester City", "Sunderland")]
        results = match_events(rb, fs)
        assert results[0]["status"] == "UNMATCHED"

    def test_no_flashscore_events(self):
        rb = [_make_rb_match("Arsenal", "Chelsea")]
        results = match_events(rb, [])
        assert results[0]["status"] == "UNMATCHED"

    def test_non_football_filtered(self):
        rb = [_make_rb_match("Team A", "Team B")]
        fs = [{"sport": "tennis", "participants": ["Team A", "Team B"], "mid": "T1"}]
        results = match_events(rb, fs)
        assert results[0]["status"] == "UNMATCHED"

    def test_multiple_matches(self):
        rb = [_make_rb_match("Arsenal", "Chelsea"), _make_rb_match("Liverpool", "Everton")]
        fs = [_make_fs_event("Arsenal", "Chelsea", "M1"), _make_fs_event("Liverpool", "Everton", "M2")]
        results = match_events(rb, fs)
        assert all(r["status"] == "MATCHED" for r in results)

    def test_ambiguous_no_forced_data(self):
        rb = [_make_rb_match("Manchester City", "Liverpool")]
        fs = [_make_fs_event("Manchester City", "Arsenal")]
        results = match_events(rb, fs)
        merged = build_merged_view(results)
        assert merged[0]["match_status"] == "AMBIGUOUS"
        assert merged[0]["flashscore_mid"] is None

    def test_matched_ligue1_aliases(self):
        rb = [_make_rb_match("Nice", "Lille", slug="lille-vs-nice")]
        fs = [_make_fs_event("LOSC Lille", "OGC Nice")]
        results = match_events(rb, fs)
        assert results[0]["status"] == "MATCHED"


class TestBuildMergedView:
    def test_matched_merged_format(self):
        rb = [_make_rb_match("Manchester City", "Sunderland")]
        fs = [_make_fs_event("Manchester City", "Sunderland", "XYZ789", "Premier League")]
        results = match_events(rb, fs)
        merged = build_merged_view(results)
        assert len(merged) == 1
        m = merged[0]
        assert m["match_status"] == "MATCHED"
        assert m["home_team_rb"] == "Manchester City"
        assert m["away_team_rb"] == "Sunderland"
        assert m["home_team_fs"] == "Manchester City"
        assert m["away_team_fs"] == "Sunderland"
        assert m["flashscore_mid"] == "XYZ789"
        assert m["competition_fs"] == "Premier League"
        assert m["ratingbet_probs"]["W1_pct"] == 60
        assert m["ratingbet_best_tip"]["market"] == "Result"

    def test_unmatched_has_null_fs_fields(self):
        rb = [_make_rb_match("Barcelona", "Real Madrid")]
        results = match_events(rb, [])
        merged = build_merged_view(results)
        m = merged[0]
        assert m["match_status"] == "UNMATCHED"
        assert m["flashscore_mid"] is None
        assert m["home_team_fs"] is None
        assert m["away_team_fs"] is None
        assert m["competition_fs"] is None
        assert m["flashscore_preview_snippet"] is None

    def test_preview_snippet_truncation(self):
        rb = [_make_rb_match("Arsenal", "Chelsea")]
        long_preview = "A" * 500
        fs = [_make_fs_event("Arsenal", "Chelsea")]
        fs[0]["preview_full_text"] = long_preview
        results = match_events(rb, fs)
        merged = build_merged_view(results)
        assert len(merged[0]["flashscore_preview_snippet"]) == 200

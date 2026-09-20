"""Tests for ratingbet_performance.py — Phase 1B"""

import json
import os
from copy import deepcopy

import pytest

from ratingbet_performance import (
    _get_bracket,
    load_stats,
    save_stats,
    update_stats,
)

# ─── Fixture audit data ───

AUDIT_MATCH = {
    "flashscore_mid": "TEST001",
    "ratingbet_slug": "lyon-vs-rennes",
    "match_date": "2026-09-20",
    "match_time_paris": "20:45",
    "home_team": "Lyon",
    "away_team": "Rennes",
    "league": "France: Ligue 1",
    "prospective_valid": True,
    "actual_score": "2-1",
    "actual_result": "HOME",
    "actual_total_goals": 3,
    "actual_over_25": True,
    "actual_btts": True,
    "audit_result": {"rb_prediction": "W1", "rb_prob_pct": 67, "correct": True},
    "audit_over25": {"rb_prediction": "over", "rb_prob_pct": 60, "correct": True},
    "audit_btts": {"rb_prediction": "yes", "rb_prob_pct": 55, "correct": True},
}

AUDIT_TEMPLATE = {
    "audit_date": "2026-09-20",
    "generated_at": "2026-09-21T09:30:00+02:00",
    "ratingbet_fetched_at": "2026-09-20T09:30:00+02:00",
    "total_matched": 1,
    "total_with_results": 1,
    "prospective_valid_count": 1,
    "matches": [AUDIT_MATCH],
}


def _empty_stats():
    return {
        "updated_at": "",
        "processed_match_ids": [],
        "total_prospective_valid": 0,
        "markets": {
            "result": {"n": 0, "correct": 0, "accuracy": 0.0, "by_bracket": {}},
            "over_25": {"n": 0, "correct": 0, "accuracy": 0.0, "by_bracket": {}},
            "btts": {"n": 0, "correct": 0, "accuracy": 0.0, "by_bracket": {}},
        },
        "by_league": {},
    }


class TestIdempotentNoDuplicate:
    def test_idempotent_no_duplicate(self):
        """1. appeler update_stats() 2x avec le même match → ID une seule fois, n=1"""
        stats = _empty_stats()
        audit = deepcopy(AUDIT_TEMPLATE)

        stats = update_stats(stats, audit)
        stats = update_stats(stats, audit)

        assert stats["processed_match_ids"].count("TEST001") == 1
        assert stats["markets"]["result"]["n"] == 1


class TestBracketAssignment:
    def test_bracket_assignment(self):
        """2. prob_pct=67% → tranche '65-69'"""
        assert _get_bracket(67) == "65-69"

    def test_bracket_50(self):
        assert _get_bracket(50) == "50-54"

    def test_bracket_79(self):
        assert _get_bracket(79) == "75-79"


class TestBracket80Plus:
    def test_bracket_80plus(self):
        """3. prob_pct=82% → tranche '80+'"""
        assert _get_bracket(82) == "80+"

    def test_bracket_100(self):
        assert _get_bracket(100) == "80+"


class TestAccuracyCalculated:
    def test_accuracy_calculated(self):
        """4. n=4, correct=3 → accuracy=0.75"""
        stats = _empty_stats()
        audit = deepcopy(AUDIT_TEMPLATE)

        # Create 4 matches, 3 correct for result
        matches = []
        for i in range(4):
            m = deepcopy(AUDIT_MATCH)
            m["flashscore_mid"] = f"MATCH_{i}"
            m["audit_result"] = {
                "rb_prediction": "W1",
                "rb_prob_pct": 67,
                "correct": i < 3,  # first 3 correct, last wrong
            }
            m["audit_over25"] = None
            m["audit_btts"] = None
            matches.append(m)

        audit["matches"] = matches
        stats = update_stats(stats, audit)

        assert stats["markets"]["result"]["n"] == 4
        assert stats["markets"]["result"]["correct"] == 3
        assert stats["markets"]["result"]["accuracy"] == 0.75


class TestByLeague:
    def test_by_league(self):
        """5. match 'France: Ligue 1' → dans stats.by_league"""
        stats = _empty_stats()
        audit = deepcopy(AUDIT_TEMPLATE)

        stats = update_stats(stats, audit)

        assert "France: Ligue 1" in stats["by_league"]
        assert stats["by_league"]["France: Ligue 1"]["result"]["n"] == 1
        assert stats["by_league"]["France: Ligue 1"]["result"]["correct"] == 1


class TestNewLeague:
    def test_new_league(self):
        """6. premier match d'une ligue → crée l'entrée dans by_league"""
        stats = _empty_stats()
        audit = deepcopy(AUDIT_TEMPLATE)
        audit["matches"][0]["league"] = "Spain: La Liga"

        stats = update_stats(stats, audit)

        assert "Spain: La Liga" in stats["by_league"]
        assert stats["by_league"]["Spain: La Liga"]["result"]["n"] == 1


class TestInvalidMatchExcluded:
    def test_invalid_match_excluded(self):
        """7. match prospective_valid=False → pas compté dans les stats"""
        stats = _empty_stats()
        audit = deepcopy(AUDIT_TEMPLATE)
        audit["matches"][0]["prospective_valid"] = False

        stats = update_stats(stats, audit)

        assert stats["total_prospective_valid"] == 0
        assert stats["markets"]["result"]["n"] == 0
        assert len(stats["processed_match_ids"]) == 0


class TestStatsPersisted:
    def test_stats_persisted(self, tmp_path):
        """8. save_stats() + load_stats() → même contenu (hors updated_at)"""
        stats = _empty_stats()
        audit = deepcopy(AUDIT_TEMPLATE)
        stats = update_stats(stats, audit)

        save_stats(stats, str(tmp_path))
        reloaded = load_stats(str(tmp_path))

        assert reloaded["processed_match_ids"] == stats["processed_match_ids"]
        assert reloaded["total_prospective_valid"] == stats["total_prospective_valid"]
        assert reloaded["markets"]["result"]["n"] == stats["markets"]["result"]["n"]
        assert reloaded["markets"]["result"]["correct"] == stats["markets"]["result"]["correct"]
        assert reloaded["markets"]["result"]["accuracy"] == stats["markets"]["result"]["accuracy"]

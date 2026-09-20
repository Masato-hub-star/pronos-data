"""Tests for ratingbet_auditor.py — Phase 1B"""

import json
import os
import shutil
import tempfile
from copy import deepcopy

import pytest

from ratingbet_auditor import (
    audit_day,
    check_prospective_valid,
    compute_market_audit,
)

# ─── Fixtures de base ───

FREEZE_TEMPLATE = {
    "fetched_at": "2026-09-20T09:30:00+02:00",
    "date": "2026-09-20",
    "match_count": 1,
    "matches": [],
}

MERGED_TEMPLATE = {
    "match_date": "2026-09-20",
    "match_time_paris": "20:45",
    "home_team_rb": "Lyon",
    "away_team_rb": "Rennes",
    "home_team_fs": "Lyon",
    "away_team_fs": "Rennes",
    "competition_fs": "Ligue 1",
    "league_rb": "France: Ligue 1",
    "match_status": "MATCHED",
    "flashscore_mid": "TEST001",
    "ratingbet_slug": "lyon-vs-rennes",
    "flashscore_preview_available": True,
    "ratingbet_probs": {"W1_pct": 45, "X_pct": 25, "W2_pct": 30, "over_25_pct": 60, "btts_yes_pct": 55},
    "ratingbet_best_tip": {"market": "Result", "outcome": "W1", "odd": 1.65},
    "flashscore_preview_snippet": "...",
}

RESULT_TEMPLATE = {
    "sport": "football",
    "competition": "Ligue 1",
    "date": "2026-09-20",
    "time_paris": "20:45",
    "participants": ["Lyon", "Rennes"],
    "mid": "TEST001",
    "url": "https://www.flashscore.fr/match/...",
    "preview_available": True,
    "preview_full_text": "...",
    "result": {
        "score": "2-1",
        "winner": "home",
        "btts": True,
        "total_goals": 3,
        "retrieved_at": "2026-09-21T09:30:00+02:00",
    },
}

FREEZE_MATCH_TEMPLATE = {
    "match_id": "lyon-vs-rennes",
    "home_team": "Lyon",
    "away_team": "Rennes",
    "date": "2026-09-20",
    "time_paris": "20:45",
    "league": "France: Ligue 1",
    "markets": {
        "result": {
            "W1": {"odd": 1.65, "prob_pct": 45},
            "X": {"odd": 3.20, "prob_pct": 25},
            "W2": {"odd": 4.50, "prob_pct": 30},
        },
        "total_25": {
            "over": {"odd": 1.70, "prob_pct": 60},
            "under": {"odd": 2.10, "prob_pct": 40},
        },
        "btts": {
            "yes": {"odd": 1.80, "prob_pct": 55},
            "no": {"odd": 2.00, "prob_pct": 45},
        },
    },
    "best_tip": {"market": "Result", "outcome": "W1", "odd": 1.65},
}


def _make_day(tmpdir, date_str, merged, results, freeze):
    data_dir = os.path.join(tmpdir, "data", date_str)
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "merged_today.json"), "w") as f:
        json.dump(merged, f)
    with open(os.path.join(data_dir, "flashscore_results.json"), "w") as f:
        json.dump(results, f)
    with open(os.path.join(data_dir, "ratingbet_model_raw.json"), "w") as f:
        json.dump(freeze, f)
    return data_dir


def _build_scenario(prob_w1=45, prob_x=25, prob_w2=30, over_pct=60, btts_yes_pct=55,
                    score="2-1", btts_actual=True, total_goals=3):
    """Build a complete set of test fixtures with given parameters."""
    merged_entry = deepcopy(MERGED_TEMPLATE)
    merged_entry["ratingbet_probs"]["W1_pct"] = prob_w1
    merged_entry["ratingbet_probs"]["X_pct"] = prob_x
    merged_entry["ratingbet_probs"]["W2_pct"] = prob_w2
    merged_entry["ratingbet_probs"]["over_25_pct"] = over_pct
    merged_entry["ratingbet_probs"]["btts_yes_pct"] = btts_yes_pct

    result_entry = deepcopy(RESULT_TEMPLATE)
    result_entry["result"]["score"] = score
    result_entry["result"]["total_goals"] = total_goals
    result_entry["result"]["btts"] = btts_actual

    freeze_match = deepcopy(FREEZE_MATCH_TEMPLATE)
    freeze_match["markets"]["result"]["W1"]["prob_pct"] = prob_w1
    freeze_match["markets"]["result"]["X"]["prob_pct"] = prob_x
    freeze_match["markets"]["result"]["W2"]["prob_pct"] = prob_w2
    freeze_match["markets"]["total_25"]["over"]["prob_pct"] = over_pct
    freeze_match["markets"]["total_25"]["under"]["prob_pct"] = 100 - over_pct
    freeze_match["markets"]["btts"]["yes"]["prob_pct"] = btts_yes_pct
    freeze_match["markets"]["btts"]["no"]["prob_pct"] = 100 - btts_yes_pct

    freeze = deepcopy(FREEZE_TEMPLATE)
    freeze["matches"] = [freeze_match]

    return [merged_entry], [result_entry], freeze


# ─── Tests ───

class TestHomeWin:
    def test_home_win(self, tmp_path):
        """1. résultat HOME + W1 prédit à 67% → audit_result.correct = True"""
        merged, results, freeze = _build_scenario(prob_w1=67, prob_x=18, prob_w2=15, score="2-1")
        _make_day(str(tmp_path), "2026-09-20", merged, results, freeze)

        audit = audit_day("2026-09-20", base_dir=str(tmp_path))
        m = audit["matches"][0]
        assert m["actual_result"] == "HOME"
        assert m["audit_result"]["rb_prediction"] == "W1"
        assert m["audit_result"]["rb_prob_pct"] == 67
        assert m["audit_result"]["correct"] is True


class TestDraw:
    def test_draw(self, tmp_path):
        """2. résultat DRAW + X prédit à 55% → audit_result.correct = True"""
        merged, results, freeze = _build_scenario(prob_w1=20, prob_x=55, prob_w2=25, score="1-1", total_goals=2, btts_actual=True)
        _make_day(str(tmp_path), "2026-09-20", merged, results, freeze)

        audit = audit_day("2026-09-20", base_dir=str(tmp_path))
        m = audit["matches"][0]
        assert m["actual_result"] == "DRAW"
        assert m["audit_result"]["rb_prediction"] == "X"
        assert m["audit_result"]["rb_prob_pct"] == 55
        assert m["audit_result"]["correct"] is True


class TestAwayWin:
    def test_away_win(self, tmp_path):
        """3. résultat AWAY + W2 prédit à 60% → audit_result.correct = True"""
        merged, results, freeze = _build_scenario(prob_w1=15, prob_x=25, prob_w2=60, score="0-2", total_goals=2, btts_actual=False)
        _make_day(str(tmp_path), "2026-09-20", merged, results, freeze)

        audit = audit_day("2026-09-20", base_dir=str(tmp_path))
        m = audit["matches"][0]
        assert m["actual_result"] == "AWAY"
        assert m["audit_result"]["rb_prediction"] == "W2"
        assert m["audit_result"]["rb_prob_pct"] == 60
        assert m["audit_result"]["correct"] is True


class TestResultWrong:
    def test_result_wrong(self, tmp_path):
        """4. résultat HOME + W2 prédit à 60% → audit_result.correct = False"""
        merged, results, freeze = _build_scenario(prob_w1=15, prob_x=25, prob_w2=60, score="2-1", total_goals=3, btts_actual=True)
        _make_day(str(tmp_path), "2026-09-20", merged, results, freeze)

        audit = audit_day("2026-09-20", base_dir=str(tmp_path))
        m = audit["matches"][0]
        assert m["actual_result"] == "HOME"
        assert m["audit_result"]["rb_prediction"] == "W2"
        assert m["audit_result"]["correct"] is False


class TestOver25:
    def test_over_25(self, tmp_path):
        """5. total_goals=3 → actual_over_25=True ; over prédit à 65% → correct"""
        merged, results, freeze = _build_scenario(over_pct=65, score="2-1", total_goals=3)
        _make_day(str(tmp_path), "2026-09-20", merged, results, freeze)

        audit = audit_day("2026-09-20", base_dir=str(tmp_path))
        m = audit["matches"][0]
        assert m["actual_over_25"] is True
        assert m["audit_over25"]["rb_prediction"] == "over"
        assert m["audit_over25"]["rb_prob_pct"] == 65
        assert m["audit_over25"]["correct"] is True


class TestUnder25:
    def test_under_25(self, tmp_path):
        """6. total_goals=1 → actual_over_25=False ; over prédit à 40% (under) → correct"""
        merged, results, freeze = _build_scenario(over_pct=40, score="1-0", total_goals=1, btts_actual=False)
        _make_day(str(tmp_path), "2026-09-20", merged, results, freeze)

        audit = audit_day("2026-09-20", base_dir=str(tmp_path))
        m = audit["matches"][0]
        assert m["actual_over_25"] is False
        assert m["audit_over25"]["rb_prediction"] == "under"
        assert m["audit_over25"]["rb_prob_pct"] == 60  # 100 - 40
        assert m["audit_over25"]["correct"] is True


class TestBttsYes:
    def test_btts_yes(self, tmp_path):
        """7. btts=True + yes prédit à 60% → correct"""
        merged, results, freeze = _build_scenario(btts_yes_pct=60, score="2-1", btts_actual=True)
        _make_day(str(tmp_path), "2026-09-20", merged, results, freeze)

        audit = audit_day("2026-09-20", base_dir=str(tmp_path))
        m = audit["matches"][0]
        assert m["actual_btts"] is True
        assert m["audit_btts"]["rb_prediction"] == "yes"
        assert m["audit_btts"]["rb_prob_pct"] == 60
        assert m["audit_btts"]["correct"] is True


class TestBttsNo:
    def test_btts_no(self, tmp_path):
        """8. btts=False + no prédit (yes à 35%) → correct"""
        merged, results, freeze = _build_scenario(btts_yes_pct=35, score="2-0", btts_actual=False, total_goals=2)
        _make_day(str(tmp_path), "2026-09-20", merged, results, freeze)

        audit = audit_day("2026-09-20", base_dir=str(tmp_path))
        m = audit["matches"][0]
        assert m["actual_btts"] is False
        assert m["audit_btts"]["rb_prediction"] == "no"
        assert m["audit_btts"]["rb_prob_pct"] == 65  # 100 - 35
        assert m["audit_btts"]["correct"] is True


class TestProspectiveValid:
    def test_prospective_valid(self):
        """9. fetched_at 09:30 + match 20:45 → valid=True"""
        assert check_prospective_valid("2026-09-20T09:30:00+02:00", "2026-09-20", "20:45") is True

    def test_prospective_invalid_post_kickoff(self):
        """10. fetched_at 10:30 + match 08:00 → valid=False"""
        assert check_prospective_valid("2026-09-20T10:30:00+02:00", "2026-09-20", "08:00") is False


class TestNoResultSkip:
    def test_no_result_skip(self, tmp_path):
        """11. match result=null → exclu de l'audit (pas d'erreur)"""
        merged, results, freeze = _build_scenario()
        results[0]["result"] = None
        _make_day(str(tmp_path), "2026-09-20", merged, results, freeze)

        audit = audit_day("2026-09-20", base_dir=str(tmp_path))
        assert audit["total_with_results"] == 0
        assert len(audit["matches"]) == 0


class TestNoFreezeSkip:
    def test_no_freeze_skip(self, tmp_path):
        """12. flashscore_mid absent de merged → géré proprement"""
        merged_entry = deepcopy(MERGED_TEMPLATE)
        merged_entry["match_status"] = "UNMATCHED"
        merged_entry["flashscore_mid"] = None

        result_entry = deepcopy(RESULT_TEMPLATE)
        freeze = deepcopy(FREEZE_TEMPLATE)
        freeze["matches"] = [deepcopy(FREEZE_MATCH_TEMPLATE)]

        _make_day(str(tmp_path), "2026-09-20", [merged_entry], [result_entry], freeze)

        audit = audit_day("2026-09-20", base_dir=str(tmp_path))
        assert audit["total_matched"] == 0
        assert len(audit["matches"]) == 0


class TestAbsentMarketNull:
    def test_absent_market_null(self, tmp_path):
        """13. market avec toutes proba null → audit_result=null"""
        merged, results, freeze = _build_scenario()
        # Set all result market probas to null
        for key in ("W1", "X", "W2"):
            freeze["matches"][0]["markets"]["result"][key]["prob_pct"] = None
        # Set btts to null
        freeze["matches"][0]["markets"]["btts"]["yes"]["prob_pct"] = None
        freeze["matches"][0]["markets"]["btts"]["no"]["prob_pct"] = None

        _make_day(str(tmp_path), "2026-09-20", merged, results, freeze)

        audit = audit_day("2026-09-20", base_dir=str(tmp_path))
        m = audit["matches"][0]
        assert m["audit_result"] is None
        assert m["audit_btts"] is None


class TestFreezeNotModified:
    def test_freeze_not_modified(self, tmp_path):
        """14. après audit_day(), ratingbet_model_raw.json n'a pas changé"""
        merged, results, freeze = _build_scenario()
        data_dir = _make_day(str(tmp_path), "2026-09-20", merged, results, freeze)

        freeze_path = os.path.join(data_dir, "ratingbet_model_raw.json")
        with open(freeze_path) as f:
            before = f.read()

        audit_day("2026-09-20", base_dir=str(tmp_path))

        with open(freeze_path) as f:
            after = f.read()

        assert before == after

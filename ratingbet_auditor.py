#!/usr/bin/env python3
"""RatingBet Auditor — Phase 1B

Rattache chaque snapshot FREEZE aux résultats Flashscore,
calcule les hits RatingBet, et sauvegarde data/D/ratingbet_audit.json.
Idempotent par construction (inputs immuables → même output).
"""

import argparse
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

PARIS_TZ = ZoneInfo("Europe/Paris")


def check_prospective_valid(fetched_at_iso: str, match_date: str, match_time_paris: str) -> bool:
    """Vérifie que le FREEZE a été pris AVANT le coup d'envoi."""
    fetched_dt = datetime.fromisoformat(fetched_at_iso)
    hour, minute = map(int, match_time_paris.split(":"))
    match_start_dt = datetime(
        *map(int, match_date.split("-")),
        hour=hour,
        minute=minute,
        tzinfo=PARIS_TZ,
    )
    return fetched_dt < match_start_dt


def _derive_actual_result(score: str):
    """Dérive HOME/DRAW/AWAY depuis un score 'X-Y'."""
    parts = score.split("-")
    if len(parts) != 2:
        return None
    try:
        home_goals, away_goals = int(parts[0].strip()), int(parts[1].strip())
    except ValueError:
        return None
    if home_goals > away_goals:
        return "HOME"
    elif home_goals < away_goals:
        return "AWAY"
    return "DRAW"


def compute_market_audit(rb_market_data: dict, actual_value) -> dict | None:
    """Calcule l'audit d'un marché unique.

    Args:
        rb_market_data: dict keyed by outcome (W1/X/W2 or over/under or yes/no)
                       each value has 'prob_pct'
        actual_value: pour result → "HOME"/"DRAW"/"AWAY"
                     pour over25  → bool
                     pour btts    → bool
    """
    if rb_market_data is None:
        return None

    keys = set(rb_market_data.keys())

    if keys == {"W1", "X", "W2"} or keys <= {"W1", "X", "W2"}:
        return _audit_result(rb_market_data, actual_value)
    elif keys == {"over", "under"} or keys <= {"over", "under"}:
        return _audit_over25(rb_market_data, actual_value)
    elif keys == {"yes", "no"} or keys <= {"yes", "no"}:
        return _audit_btts(rb_market_data, actual_value)
    return None


def _audit_result(data: dict, actual_result: str) -> dict | None:
    """Audit du marché Result (1X2)."""
    OUTCOME_MAP = {"W1": "HOME", "X": "DRAW", "W2": "AWAY"}

    best_outcome = None
    best_prob = -1
    for key in ("W1", "X", "W2"):
        entry = data.get(key)
        if entry is None:
            continue
        prob = entry.get("prob_pct")
        if prob is not None and prob > best_prob:
            best_prob = prob
            best_outcome = key

    if best_outcome is None:
        return None

    return {
        "rb_prediction": best_outcome,
        "rb_prob_pct": best_prob,
        "correct": OUTCOME_MAP[best_outcome] == actual_result,
    }


def _audit_over25(data: dict, actual_over25: bool) -> dict | None:
    """Audit du marché Over/Under 2.5."""
    over_entry = data.get("over")
    if over_entry is None:
        return None
    over_prob = over_entry.get("prob_pct")
    if over_prob is None:
        return None

    rb_predicts_over = over_prob > 50
    return {
        "rb_prediction": "over" if rb_predicts_over else "under",
        "rb_prob_pct": over_prob if rb_predicts_over else (100 - over_prob),
        "correct": rb_predicts_over == actual_over25,
    }


def _audit_btts(data: dict, actual_btts: bool) -> dict | None:
    """Audit du marché BTTS."""
    yes_entry = data.get("yes")
    if yes_entry is None:
        return None
    yes_prob = yes_entry.get("prob_pct")
    if yes_prob is None:
        return None

    rb_predicts_yes = yes_prob > 50
    return {
        "rb_prediction": "yes" if rb_predicts_yes else "no",
        "rb_prob_pct": yes_prob if rb_predicts_yes else (100 - yes_prob),
        "correct": rb_predicts_yes == actual_btts,
    }


def audit_day(date_str: str, base_dir: str = ".") -> dict:
    """Produit l'audit complet d'une journée."""
    data_dir = os.path.join(base_dir, "data", date_str)

    merged_path = os.path.join(data_dir, "merged_today.json")
    results_path = os.path.join(data_dir, "flashscore_results.json")
    freeze_path = os.path.join(data_dir, "ratingbet_model_raw.json")

    for p, label in [(merged_path, "merged_today"), (results_path, "flashscore_results"), (freeze_path, "ratingbet_model_raw")]:
        if not os.path.isfile(p):
            print(f"[SKIP] {label} introuvable : {p}")
            return {}

    with open(merged_path) as f:
        merged = json.load(f)
    with open(results_path) as f:
        results_list = json.load(f)
    with open(freeze_path) as f:
        freeze = json.load(f)

    fetched_at = freeze.get("fetched_at", "")

    results_by_mid = {}
    for r in results_list:
        mid = r.get("mid")
        if mid:
            results_by_mid[mid] = r

    freeze_by_slug = {}
    for m in freeze.get("matches", []):
        slug = m.get("match_id")
        if slug:
            freeze_by_slug[slug] = m

    audit_matches = []
    total_matched = 0
    total_with_results = 0
    prospective_valid_count = 0

    for entry in merged:
        if entry.get("match_status") != "MATCHED":
            continue

        total_matched += 1
        fs_mid = entry.get("flashscore_mid")
        rb_slug = entry.get("ratingbet_slug")

        if not fs_mid:
            continue

        result_data = results_by_mid.get(fs_mid)
        if result_data is None:
            continue

        result_obj = result_data.get("result")
        if result_obj is None:
            continue

        score = result_obj.get("score")
        if not score:
            continue

        total_with_results += 1

        match_time = entry.get("match_time_paris", "00:00")
        match_date = entry.get("match_date", date_str)
        is_prospective = check_prospective_valid(fetched_at, match_date, match_time)
        if is_prospective:
            prospective_valid_count += 1

        actual_result = _derive_actual_result(score)
        total_goals = result_obj.get("total_goals")
        if total_goals is None:
            parts = score.split("-")
            try:
                total_goals = int(parts[0].strip()) + int(parts[1].strip())
            except (ValueError, IndexError):
                total_goals = 0

        actual_over_25 = total_goals > 2
        actual_btts = result_obj.get("btts")
        if actual_btts is None:
            parts = score.split("-")
            try:
                actual_btts = int(parts[0].strip()) > 0 and int(parts[1].strip()) > 0
            except (ValueError, IndexError):
                actual_btts = False

        audit_result = None
        audit_over25 = None
        audit_btts = None

        if is_prospective:
            rb_match = freeze_by_slug.get(rb_slug, {})
            markets = rb_match.get("markets", {})

            result_market = markets.get("result")
            if result_market and actual_result:
                audit_result = compute_market_audit(result_market, actual_result)

            over_market = markets.get("total_25")
            if over_market:
                audit_over25 = compute_market_audit(over_market, actual_over_25)

            btts_market = markets.get("btts")
            if btts_market:
                audit_btts = compute_market_audit(btts_market, actual_btts)

        home = entry.get("home_team_rb") or entry.get("home_team_fs", "")
        away = entry.get("away_team_rb") or entry.get("away_team_fs", "")
        league = entry.get("league_rb", "")

        audit_matches.append({
            "flashscore_mid": fs_mid,
            "ratingbet_slug": rb_slug,
            "match_date": match_date,
            "match_time_paris": match_time,
            "home_team": home,
            "away_team": away,
            "league": league,
            "prospective_valid": is_prospective,
            "actual_score": score,
            "actual_result": actual_result,
            "actual_total_goals": total_goals,
            "actual_over_25": actual_over_25,
            "actual_btts": actual_btts,
            "audit_result": audit_result,
            "audit_over25": audit_over25,
            "audit_btts": audit_btts,
        })

    audit = {
        "audit_date": date_str,
        "generated_at": datetime.now(PARIS_TZ).isoformat(),
        "ratingbet_fetched_at": fetched_at,
        "total_matched": total_matched,
        "total_with_results": total_with_results,
        "prospective_valid_count": prospective_valid_count,
        "matches": audit_matches,
    }

    audit_path = os.path.join(data_dir, "ratingbet_audit.json")
    with open(audit_path, "w") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)
    print(f"[OK] Audit sauvegardé : {audit_path}")

    return audit


def print_summary(audit: dict):
    if not audit:
        print("Aucune donnée à auditer.")
        return

    print(f"\n=== AUDIT RatingBet — {audit['audit_date']} ===")
    print(f"FREEZE pris à : {audit['ratingbet_fetched_at']}")
    print(f"Matchs MATCHED : {audit['total_matched']}")
    print(f"Avec résultats : {audit['total_with_results']}")
    print(f"Prospective valid : {audit['prospective_valid_count']}")

    if not audit.get("matches"):
        return

    valid = [m for m in audit["matches"] if m["prospective_valid"]]

    for label, key in [("Result", "audit_result"), ("Over 2.5", "audit_over25"), ("BTTS", "audit_btts")]:
        audited = [m for m in valid if m.get(key) is not None]
        correct = sum(1 for m in audited if m[key].get("correct"))
        n = len(audited)
        pct = f"{correct/n*100:.1f}%" if n else "N/A"
        print(f"  {label}: {correct}/{n} ({pct})")


def main():
    parser = argparse.ArgumentParser(description="Audit RatingBet predictions vs actual results")
    parser.add_argument("--date", required=True, help="Date au format YYYY-MM-DD")
    parser.add_argument("--base-dir", default=".", help="Répertoire de base contenant data/")
    args = parser.parse_args()

    audit = audit_day(args.date, base_dir=args.base_dir)
    print_summary(audit)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""RatingBet Performance — Phase 1B

Met à jour les statistiques cumulatives à partir d'un fichier ratingbet_audit.json.
Idempotent via la liste processed_match_ids.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

PARIS_TZ = ZoneInfo("Europe/Paris")
STATS_FILE = "ratingbet_stats.json"

BRACKETS = [
    ("50-54", 50, 54),
    ("55-59", 55, 59),
    ("60-64", 60, 64),
    ("65-69", 65, 69),
    ("70-74", 70, 74),
    ("75-79", 75, 79),
    ("80+", 80, 100),
]


def _get_bracket(prob_pct: int) -> str:
    for label, lo, hi in BRACKETS:
        if lo <= prob_pct <= hi:
            return label
    return "80+"


def _empty_market():
    return {
        "n": 0,
        "correct": 0,
        "accuracy": 0.0,
        "by_bracket": {},
    }


def _empty_stats():
    return {
        "updated_at": "",
        "processed_match_ids": [],
        "total_prospective_valid": 0,
        "markets": {
            "result": _empty_market(),
            "over_25": _empty_market(),
            "btts": _empty_market(),
        },
        "by_league": {},
    }


def load_stats(base_dir: str = ".") -> dict:
    stats_path = os.path.join(base_dir, STATS_FILE)
    if os.path.isfile(stats_path):
        with open(stats_path) as f:
            return json.load(f)
    return _empty_stats()


def _ensure_bracket(market_stats: dict, bracket: str):
    bb = market_stats.setdefault("by_bracket", {})
    if bracket not in bb:
        bb[bracket] = {"n": 0, "correct": 0, "accuracy": 0.0}


def _ensure_league(stats: dict, league: str):
    bl = stats.setdefault("by_league", {})
    if league not in bl:
        bl[league] = {}
    for mk in ("result", "over_25", "btts"):
        if mk not in bl[league]:
            bl[league][mk] = {"n": 0, "correct": 0, "accuracy": 0.0}


def _update_market(market_stats: dict, audit_entry: dict | None):
    if audit_entry is None:
        return False
    prob = audit_entry.get("rb_prob_pct")
    if prob is None:
        return False

    market_stats["n"] = market_stats.get("n", 0) + 1
    if audit_entry.get("correct"):
        market_stats["correct"] = market_stats.get("correct", 0) + 1

    bracket = _get_bracket(prob)
    _ensure_bracket(market_stats, bracket)
    market_stats["by_bracket"][bracket]["n"] += 1
    if audit_entry.get("correct"):
        market_stats["by_bracket"][bracket]["correct"] += 1

    return True


def _update_league_market(league_market: dict, audit_entry: dict | None):
    if audit_entry is None:
        return
    league_market["n"] = league_market.get("n", 0) + 1
    if audit_entry.get("correct"):
        league_market["correct"] = league_market.get("correct", 0) + 1


def _recalc_accuracy(d: dict):
    n = d.get("n", 0)
    d["accuracy"] = round(d["correct"] / n, 3) if n > 0 else 0.0


def _recalc_all_accuracy(stats: dict):
    for mk in ("result", "over_25", "btts"):
        market = stats["markets"].get(mk, {})
        _recalc_accuracy(market)
        for bracket_data in market.get("by_bracket", {}).values():
            _recalc_accuracy(bracket_data)

    for league_data in stats.get("by_league", {}).values():
        for mk in ("result", "over_25", "btts"):
            if mk in league_data:
                _recalc_accuracy(league_data[mk])


def update_stats(stats: dict, audit: dict) -> dict:
    if not audit or not audit.get("matches"):
        return stats

    if "processed_match_ids" not in stats:
        stats["processed_match_ids"] = []
    if "markets" not in stats:
        stats["markets"] = {k: _empty_market() for k in ("result", "over_25", "btts")}
    if "by_league" not in stats:
        stats["by_league"] = {}
    if "total_prospective_valid" not in stats:
        stats["total_prospective_valid"] = 0

    processed = set(stats["processed_match_ids"])

    for match in audit["matches"]:
        if not match.get("prospective_valid"):
            continue
        if match.get("actual_score") is None:
            continue

        mid = match.get("flashscore_mid")
        if not mid or mid in processed:
            continue

        processed.add(mid)
        stats["total_prospective_valid"] += 1

        league = match.get("league", "")

        _ensure_league(stats, league)

        _update_market(stats["markets"]["result"], match.get("audit_result"))
        _update_league_market(stats["by_league"][league]["result"], match.get("audit_result"))

        _update_market(stats["markets"]["over_25"], match.get("audit_over25"))
        _update_league_market(stats["by_league"][league]["over_25"], match.get("audit_over25"))

        _update_market(stats["markets"]["btts"], match.get("audit_btts"))
        _update_league_market(stats["by_league"][league]["btts"], match.get("audit_btts"))

    stats["processed_match_ids"] = sorted(processed)
    _recalc_all_accuracy(stats)

    return stats


def save_stats(stats: dict, base_dir: str = "."):
    stats["updated_at"] = datetime.now(PARIS_TZ).isoformat()
    stats_path = os.path.join(base_dir, STATS_FILE)
    tmp_path = stats_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, stats_path)
    print(f"[OK] Stats sauvegardées : {stats_path}")


def print_summary(stats: dict):
    print(f"\n=== PERFORMANCE RatingBet ===")
    print(f"Total prospective valid : {stats.get('total_prospective_valid', 0)}")
    print(f"Matchs traités : {len(stats.get('processed_match_ids', []))}")

    for mk_label, mk_key in [("Result", "result"), ("Over 2.5", "over_25"), ("BTTS", "btts")]:
        m = stats.get("markets", {}).get(mk_key, {})
        n = m.get("n", 0)
        c = m.get("correct", 0)
        acc = m.get("accuracy", 0)
        print(f"  {mk_label}: {c}/{n} ({acc*100:.1f}%)")
        for bk, bd in sorted(m.get("by_bracket", {}).items()):
            print(f"    [{bk}] {bd['correct']}/{bd['n']} ({bd['accuracy']*100:.1f}%)")

    leagues = stats.get("by_league", {})
    if leagues:
        print("\n  Par ligue :")
        for lg, lg_data in sorted(leagues.items()):
            parts = []
            for mk in ("result", "over_25", "btts"):
                d = lg_data.get(mk, {})
                if d.get("n", 0) > 0:
                    parts.append(f"{mk}={d['correct']}/{d['n']}")
            if parts:
                print(f"    {lg}: {', '.join(parts)}")


def main():
    parser = argparse.ArgumentParser(description="Update RatingBet cumulative performance stats")
    parser.add_argument("--date", required=True, help="Date au format YYYY-MM-DD")
    parser.add_argument("--base-dir", default=".", help="Répertoire de base")
    args = parser.parse_args()

    audit_path = os.path.join(args.base_dir, "data", args.date, "ratingbet_audit.json")
    if not os.path.isfile(audit_path):
        print(f"[SKIP] Pas d'audit pour {args.date} ({audit_path})")
        sys.exit(0)

    with open(audit_path) as f:
        audit = json.load(f)

    stats = load_stats(args.base_dir)
    stats = update_stats(stats, audit)
    save_stats(stats, args.base_dir)
    print_summary(stats)


if __name__ == "__main__":
    main()

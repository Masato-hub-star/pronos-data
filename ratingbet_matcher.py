"""Match RatingBet predictions with Flashscore events and build merged view."""

import argparse
import json
import os
import re
import sys

from ratingbet_normalizer import normalize_team, slug_to_teams


def load_flashscore(date: str) -> list[dict]:
    """Load Flashscore previews for a given date."""
    dated_path = os.path.join("data", date, "flashscore_previews.json")
    root_path = "flashscore_previews.json"
    path = dated_path if os.path.exists(dated_path) else root_path
    if not os.path.exists(path):
        print(f"[WARN] No Flashscore data found at {dated_path} or {root_path}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def load_ratingbet(date: str) -> dict:
    """Load RatingBet raw snapshot for a given date."""
    path = os.path.join("data", date, "ratingbet_model_raw.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No RatingBet data at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def match_events(rb_matches: list[dict], fs_events: list[dict]) -> list[dict]:
    """Match RatingBet matches to Flashscore events.
    Deterministic matching: normalize team names, require both teams to match.
    Supports cross-matching (home/away can be swapped between sources).
    """
    fs_index: list[dict] = []
    for ev in fs_events:
        if ev.get("sport", "").lower() != "football":
            continue
        participants = ev.get("participants", [])
        if len(participants) != 2:
            continue
        home_norm = normalize_team(participants[0])
        away_norm = normalize_team(participants[1])
        fs_index.append({"event": ev, "home_norm": home_norm, "away_norm": away_norm})

    results = []
    for rb in rb_matches:
        rb_home_norm = normalize_team(rb.get("home_team", ""))
        rb_away_norm = normalize_team(rb.get("away_team", ""))
        slug = rb.get("match_id", "")
        slug_home_norm, slug_away_norm = None, None
        if slug:
            try:
                sh, sa = slug_to_teams(slug)
                slug_home_norm = normalize_team(sh)
                slug_away_norm = normalize_team(sa)
            except ValueError:
                pass

        match_status = "UNMATCHED"
        matched_fs = None
        ambiguous_fs = None

        for fs_item in fs_index:
            fh = fs_item["home_norm"]
            fa = fs_item["away_norm"]
            direct_home = (rb_home_norm == fh)
            direct_away = (rb_away_norm == fa)
            cross_home = (rb_home_norm == fa)
            cross_away = (rb_away_norm == fh)
            slug_direct_home = (slug_home_norm == fh) if slug_home_norm else False
            slug_direct_away = (slug_away_norm == fa) if slug_away_norm else False
            slug_cross_home = (slug_home_norm == fa) if slug_home_norm else False
            slug_cross_away = (slug_away_norm == fh) if slug_away_norm else False

            both_direct = direct_home and direct_away
            both_cross = cross_home and cross_away
            both_slug_direct = slug_direct_home and slug_direct_away
            both_slug_cross = slug_cross_home and slug_cross_away

            if both_direct or both_cross or both_slug_direct or both_slug_cross:
                match_status = "MATCHED"
                matched_fs = fs_item["event"]
                break
            any_match = (
                direct_home or direct_away or cross_home or cross_away
                or slug_direct_home or slug_direct_away
                or slug_cross_home or slug_cross_away
            )
            if any_match and match_status != "MATCHED":
                match_status = "AMBIGUOUS"
                ambiguous_fs = fs_item["event"]

        result = {"rb_match": rb, "fs_event": matched_fs if match_status == "MATCHED" else None, "status": match_status}
        if match_status == "AMBIGUOUS":
            result["ambiguous_fs"] = ambiguous_fs
        results.append(result)
    return results


def _extract_probs(markets: dict) -> dict:
    probs = {"W1_pct": None, "X_pct": None, "W2_pct": None, "over_25_pct": None, "btts_yes_pct": None}
    result_mkt = markets.get("result", {})
    probs["W1_pct"] = result_mkt.get("W1", {}).get("prob_pct")
    probs["X_pct"] = result_mkt.get("X", {}).get("prob_pct")
    probs["W2_pct"] = result_mkt.get("W2", {}).get("prob_pct")
    total_mkt = markets.get("total_25", {})
    probs["over_25_pct"] = total_mkt.get("over", {}).get("prob_pct")
    btts_mkt = markets.get("btts", {})
    probs["btts_yes_pct"] = btts_mkt.get("yes", {}).get("prob_pct")
    return probs


def build_merged_view(matched: list[dict]) -> list[dict]:
    merged = []
    for item in matched:
        rb = item["rb_match"]
        fs = item.get("fs_event")
        status = item["status"]
        preview_text = ""
        if fs and fs.get("preview_full_text"):
            preview_text = fs["preview_full_text"][:200]
        entry = {
            "match_date": rb.get("date", ""),
            "match_time_paris": rb.get("time_paris", ""),
            "home_team_rb": rb.get("home_team", ""),
            "away_team_rb": rb.get("away_team", ""),
            "home_team_fs": fs["participants"][0] if fs and "participants" in fs else None,
            "away_team_fs": fs["participants"][1] if fs and "participants" in fs and len(fs["participants"]) > 1 else None,
            "competition_fs": fs.get("competition") if fs else None,
            "league_rb": rb.get("league", ""),
            "match_status": status,
            "flashscore_mid": fs.get("mid") if fs else None,
            "ratingbet_slug": rb.get("match_id", ""),
            "flashscore_preview_available": fs.get("preview_available", False) if fs else False,
            "ratingbet_probs": _extract_probs(rb.get("markets", {})),
            "ratingbet_best_tip": rb.get("best_tip", {}),
            "flashscore_preview_snippet": preview_text if preview_text else None,
        }
        merged.append(entry)
    return merged


def save_merged(data: list[dict], date: str) -> str:
    dir_path = os.path.join("data", date)
    os.makedirs(dir_path, exist_ok=True)
    filepath = os.path.join(dir_path, "merged_today.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[SAVED] {filepath}")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="RatingBet <-> Flashscore Matcher")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    args = parser.parse_args()
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    if not date_pattern.match(args.date):
        print(f"[ERROR] Invalid date format: {args.date}", file=sys.stderr)
        sys.exit(1)
    rb_data = load_ratingbet(args.date)
    fs_events = load_flashscore(args.date)
    rb_matches = rb_data.get("matches", [])
    print(f"RatingBet matches: {len(rb_matches)}")
    print(f"Flashscore events (football): {sum(1 for e in fs_events if e.get('sport', '').lower() == 'football')}")
    matched = match_events(rb_matches, fs_events)
    merged = build_merged_view(matched)
    save_merged(merged, args.date)
    n_matched = sum(1 for m in matched if m["status"] == "MATCHED")
    n_ambiguous = sum(1 for m in matched if m["status"] == "AMBIGUOUS")
    n_unmatched = sum(1 for m in matched if m["status"] == "UNMATCHED")
    print(f"\n=== Matching Summary ===")
    print(f"MATCHED:   {n_matched}")
    print(f"AMBIGUOUS: {n_ambiguous}")
    print(f"UNMATCHED: {n_unmatched}")
    print(f"Total:     {len(matched)}")


if __name__ == "__main__":
    main()

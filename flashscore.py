#!/usr/bin/env python3
"""
Flashscore Pre-Match Preview Scanner V2
=============================================

Canonical rules (DONOT MODIFY LOGIC BELOW):
- URL router uses /event/{mid}/#pre-match-preview path
- Betting analysis is extracted from pre-match preview section only
- mid is the canonical event identifier
- No Odds data is collected
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

PARIS_TZ = ZoneInfo("Europe/Paris")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SPORTS = {
    "soccer": "https://www.flashscore.com/football/",
    "basketball": "https://www.flashscore.com/basketball/",
    "tennis": "https://www.flashscore.com/tennis/",
    "hockey": "https://www.flashscore.com/hockey/",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

DELAY_BETWEEN_: float = 1.5  # seconds between requests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_today_date() -> str:
    return datetime.now(PARIS_TZ).strftime("%Y-%m-%d")


def get_data_dir(date_str: str) -> Path:
    return Path("data") / date_str


def safe_get(url: str, session: requests.Session, retries: int = 3) -> str | None:
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=15, headers=HEADERS)
            r.raise_for_status()
            return r.text
        except Exception as e:
            logger.warning(f"Retry {attempt+1}/{retries} for {url}: {e}")
            time.sleep(2 ** attempt)
    return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def extract_match_ids_from_html(html: str) -> list[str]:
    """Extract match IDs (`mid`) from Flashscore listing page."""
    # Canonical pattern: data-id=">" or data-matchid=">"
    patterns = [
        r'data-id="([A-Za-z0-9]{8})"',
        r'data-matchid="([A-Za-z0-9]{8})"',
        r'\/event\/([A-Za-z0-9]{8})\/',
    ]
    seen = set()
    ids = []
    for pat in patterns:
        for m in re.finditer(pat, html):
            mid = m.group(1)
            if mid not in seen:
                seen.add(mid)
                ids.append(mid)
    return ids


def extract_env_data(html: str) -> dict:
    """Extract event environment data from script tag."""
    m = re.search(r'window\.ENV\[['"]eventEnv['"]\]\s*=\s*(\{.+?\})', html, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return {}


def extract_preview_text(html: str) -> str:
    """Extract pre-match preview text from static HTML."""
    # Look for pre-match preview section
    patterns = [
        r'pre-match-preview([\s\S]*?)/div>',
        r'preview__text"(?:[^>]+)>([\s\S]*?)</div>',
        r'class="(?:preview__text|pre-match)(?:[^>]+)?>([\s\S]+?)</div>',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            text = re.sub(r'<[^\n>]+>', ' ', m.group(1))
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) > 50:
                return text
    return ""


def extract_betting_analysis(preview_text: str) -> str:
    """Extract betting-specific sentences from preview text."""
    keywords = [
        "bet", "winner", "predict", "favourite", "favorite", "odd",
        "probable", "expect", "anticipate", "likely", "tip", "pick",
        "advantage", "form", "streak", "injury", "injuries", "suspension",
    ]
    sentences = re.split(r'\.\s+', preview_text)
    relevant = []
    for s in sentences:
        s_lower = s.lower()
        if any(k in s_lower for k in keywords):
            relevant.append(s.strip())
    return ". ".join(relevant).strip()


def parse_match_preview(mid: str, html: str, sport: str) -> dict:
    """Parse a single match page into a structured dict."""
    env = extract_env_data(html)

    # Team names
    home_team = env.get("homeTeam", "")
    away_team = env.get("awayTeam", "")
    if not home_team:
        m = re.search(r'<h1[^>]*>(.+?)</h1>', html)
        if m:
            parts = m.group(1).split(" - ")
            if len(parts) >= 2:
                home_team, away_team = parts[0].strip(), parts[1].strip()

    # Match time
    time_paris = ""
    date_str = get_today_date()
    event_stage_time = env.get("eventStageStartTime")
    if event_stage_time:
        try:
            ts = int(event_stage_time)
            dt = datetime.fromtimestamp(ts, tz=PARIS_TZ)
            time_paris = dt.strftime("%H:%M")
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, OSError):
            pass

    # Competition
    competition = env.get("tournamentName", "") or env.get("tournament", "")

    # Preview
    preview_text = extract_preview_text(html)
    betting_analysis = extract_betting_analysis(preview_text) if preview_text else ""
    preview_available = bool(betting_analysis)

    return {
        "mid": mid,
        "sport": sport,
        "home_team": home_team,
        "away_team": away_team,
        "competition": competition,
        "time_paris": time_paris,
        "date": date_str,
        "preview_available": preview_available,
        "preview_full_text": preview_text,
        "betting_analysis": betting_analysis,
        "retrieved_at": datetime.now(PARIS_TZ).isoformat(),
    }


# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------


def crawl_sport(sport: str, session: requests.Session) -> list[dict]:
    url = SPORTS[sport]
    logger.info(f"Crawling {sport}: {url}")
    html = safe_get(url, session)
    if not html:
        logger.warning(f"Failed to fetch listing for {sport}")
        return []

    match_ids = extract_match_ids_from_html(html)
    logger.info(f"Found {len(match_ids)} match IDs for {sport}")

    results = []
    for mid in match_ids:
        preview_url = f"https://www.flashscore.com/event/{mid}/#pre-match-preview"
        match_html = safe_get(preview_url, session)
        if not match_html:
            logger.warning(f"Skipping {mid}: no HTML")
            continue

        data = parse_match_preview(mid, match_html, sport)
        results.append(data)
        logger.info(
            f"[{sport}] {mid} {data['home_team']} vs {data['away_team']} "
            f"preview={data['preview_available']}"
        )
        time.sleep(DELAY_BETWEEN_)

    return results


# ---------------------------------------------------------------------------
# Outputs --- V2 merge logic (mid-keyed)
# ---------------------------------------------------------------------------


def _write_picks_file(matches: list, path: Path) -> None:
    """Write human-readable picks.txt from a merged list."""
    previews = [sorted([m for m in matches if m.get("preview_available")],
                        key=lambda x: x.get("time_paris", ""))]
    # remove one level of nesting
    previews = previews[0] if previews else []
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Flashscore Picks -- {datetime.now(PARIS_TZ).strftime('%Y-%m-%d %H:%M')} Paris\n")
        f.write("=" * 60 + "\n\n")
        if not previews:
            f.write("No pre-match previews available yet.\n")
            return
        for match in previews:
            f.write(f"\{match['time_paris']}  {match['competition']}\n")
            f.write(f"  {match['home_team']} vs {match['away_team']}\n")
            f.write(f"  {match['betting_analysis']}\n")
            f.write("\n")


def write_outputs(results: list, date_str: str = None):
    """
    Write outputs with:
    - Merge by mid (no duplicates)
    - preview_first_seen_at (immutable, set on first pre-match scan)
    - Post-match integrity (post-start previews rejected)
    - audit.json accumulating per-scan stats
    """
    if date_str is None:
        date_str = get_today_date()

    now_paris = datetime.now(PARIS_TZ)
    scan_time_iso = now_paris.isoformat()

    data_dir = get_data_dir(date_str)
    data_dir.mkdir(parents=True, exist_ok=True)

    previews_path = data_dir / "previews.json"
    audit_path    = data_dir / "audit.json"

    # -- Load existing indexed by mid ---------------------------------------
    existing: dict = {}
    if previews_path.exists():
        try:
            with open(previews_path, encoding="utf-8") as f:
                for entry in json.load(f):
                    m = entry.get("mid", "")
                    if m:
                        existing[m] = entry
        except (json.JSONDecodeError, OSError):
            pass

    # -- Audit counters (this scan only) ------------------------------------
    events_seen               = len(results)
    previews_found            = 0
    new_previews_added        = 0
    duplicates_merged         = 0
    invalid_mid_excluded      = 0
    post_start_previews_rejected = 0

    for r in results:
        mid = r.get("mid", "")

        # -- Exclude empty mid ----------------------------------------------
        if not mid:
            invalid_mid_excluded += 1
            continue

        # -- Compute match start time (Paris) -------------------------------
        match_started = False
        try:
            dt_str = f"{r.get('date', date_str)} {r.get('time_paris', '')}"
            match_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=PARIS_TZ)
            match_started = now_paris >= match_dt
        except (ValueError, TypeError):
            pass

        has_preview = (
            r.get("preview_available", False)
            and bool(r.get("betting_analysis", "").strip())
        )
        if has_preview:
            previews_found += 1

        old = existing.get(mid)

        if old is None:
            # -- Brand-new entry ---------------------------------------------
            if has_preview and not match_started:
                r["preview_first_seen_at"] = scan_time_iso
                new_previews_added += 1
            elif has_preview and match_started:
                post_start_previews_rejected += 1
                r["preview_available"] = False
                r["preview_full_text"]  = ""
                r["betting_analysis"]   = ""
            existing[mid] = r

        else:
            # -- Merge with existing entry ----------------------------------
            duplicates_merged += 1
            merged = dict(r)

            # NEVER overwrite preview_first_seen_at
            if "preview_first_seen_at" in old:
                merged["preview_first_seen_at"] = old["preview_first_seen_at"]
            elif has_preview and not match_started:
                merged["preview_first_seen_at"] = scan_time_iso
                new_previews_added += 1

            # Count post-match rejection separately (independent of above)
            if has_preview and match_started:
                post_start_previews_rejected += 1

            # If new scan is less complete for preview, keep old
            old_has_preview = (
                old.get("preview_available", False)
                and bool(old.get("betting_analysis", "").strip())
            )
            if old_has_preview and (not has_preview or match_started):
                merged["preview_available"] = old["preview_available"]
                merged["preview_full_text"]  = old.get("preview_full_text", "")
                merged["betting_analysis"]   = old.get("betting_analysis", "")

            existing[mid] = merged

    # -- Build merged list ---------------------------------------------------
    merged_list = list(existing.values())

    # -- Write previews.json -------------------------------------------------
    with open(previews_path, "w", encoding="utf-8") as f:
        json.dump(merged_list, f, indent=2, ensure_ascii=False)
    print(f"Written: {previews_path} ({len(merged_list)} matches)")

    # -- Root-level latest copy (kept for backward-compat) ------------------
    root_json = Path("flashscore_previews.json")
    with open(root_json, "w", encoding="utf-8") as f:
        json.dump(merged_list, f, indent=2, ensure_ascii=False)
    print(f"Written: {root_json} (latest copy)")

    # -- Write picks ---------------------------------------------------------
    picks_path = data_dir / "flashscore_picks.txt"
    _write_picks_file(merged_list, picks_path)
    root_picks = Path("flashscore_picks.txt")
    _write_picks_file(merged_list, root_picks)
    print(f"Written: {picks_path} + root copy")

    # -- Append audit --------------------------------------------------------
    audit: dict = {}
    if audit_path.exists():
        try:
            with open(audit_path, encoding="utf-8") as f:
                audit = json.load(f)
        except (json.JSONDecodeError, OSError):
            audit = {}

    audit["scan_times"]                      = audit.get("scan_times", []) + [scan_time_iso]
    audit["last_scan"]                       = scan_time_iso
    audit["events_seen"]                     = audit.get("events_seen", 0)                 + events_seen
    audit["previews_found"]                  = audit.get("previews_found", 0)             + previews_found
    audit["new_previews_added"]              = audit.get("new_previews_added", 0)        + new_previews_added
    audit["duplicates_merged"]               = audit.get("duplicates_merged", 0)         + duplicates_merged
    audit["invalid_mid_excluded"]            = audit.get("invalid_mid_excluded", 0)      + invalid_mid_excluded
    audit[(post_start_previews_rejected"]    = audit.get("post_start_previews_rejected", 0) + post_start_previews_rejected
    audit["total_entries"]                   = len(merged_list)

    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)
    print(f"Written: {audit_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Flashscore pre-match preview scanner")
    parser.add_argument("--sport", default="all", help="all, soccer, basketball, tennis, hockey")
    args = parser.parse_args()

    sports_to_run = list(SPORTS.keys()) if args.sport == "all" else [args.sport]
    for s in sports_to_run:
        if s not in SPORTS:
            logger.error(f"Unknown sport: {s}")
            sys.exit(1)

    session = requests.Session()
    all_results = []
    for sport in sports_to_run:
        results = crawl_sport(sport, session)
        all_results.extend(results)

    logger.info(f"Total matches scanned: {len(all_results)}")
    write_outputs(all_results)


if __name__ == '__main__':
    main()

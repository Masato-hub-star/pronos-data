#!/usr/bin/env python3
"""
Flashscore Pre-Match Preview Crawler v2
========================================
Extracts match previews and odds from Flashscore by parsing the server-rendered
window.environment data embedded in match pages.

Features:
- Data archiving by date (data/YYYY-MM-DD/)
- Odds extraction from Flashscore API
- Results fetching for past matches
- Multi-sport support (tennis, football)

Usage:
    flashscore.py --url URL              # single match
    flashscore.py --sport tennis         # all today's tennis
    flashscore.py --sport football       # all today's football
    flashscore.py --sport all            # everything
    flashscore.py --debug                # verbose mode
    flashscore.py --results 2026-08-23   # fetch results for a past scan
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import requests

PARIS_TZ = ZoneInfo("Europe/Paris")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'DNT': '1',
}

ODDS_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0',
    'Accept': 'application/json',
    'Accept-Language': 'fr-FR,fr;q=0.9',
    'Referer': 'https://www.flashscore.fr/',
    'Origin': 'https://www.flashscore.fr',
    'X-Fsign': 'SW9D1eZo',
}

SPORT_URLS = {
    'tennis': 'https://www.flashscore.fr/tennis/',
    'football': 'https://www.flashscore.fr/',
    'basketball': 'https://www.flashscore.fr/basketball/',
    'hockey': 'https://www.flashscore.fr/hockey/',
}

ODDS_API_URL = "https://global.ds.lsapp.eu/odds/pq_graphql"

FOOTBALL_MARKETS = {
    "1x2": "1x2",
    "moneyline": "moneyline",
    "under-over": "under-over",
    "both-teams-to-score": "both-teams-to-score",
    "double-chance": "double-chance",
    "asian-handicap": "asian-handicap",
}

TENNIS_MARKETS = {
    "moneyline": "moneyline",
    "under-over": "under-over",
    "asian-handicap": "asian-handicap",
}

DEBUG_DIR = Path("debug")


def log(msg: str, debug: bool = False):
    if debug:
        print(f"[DEBUG] {msg}", file=sys.stderr)


def ensure_debug_dir():
    DEBUG_DIR.mkdir(exist_ok=True)


def get_today_date() -> str:
    return datetime.now(PARIS_TZ).strftime("%Y-%m-%d")


def get_data_dir(date_str: str = None) -> Path:
    if date_str is None:
        date_str = get_today_date()
    return Path("data") / date_str


def bbcode_to_text(s: str) -> str:
    s = re.sub(r'\[a href="[^"]*"\]', '', s)
    s = re.sub(r'\[/?(?:p|b|h2|h3|a|i|u|img[^\]]*)\]', '', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()


def extract_sections(content_parsed: str) -> dict:
    sections = {}
    parts = re.split(r'\[h2\](.*?)\[/h2\]', content_parsed)
    if parts[0].strip():
        sections['intro'] = bbcode_to_text(parts[0])
    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        content = parts[i + 1] if i + 1 < len(parts) else ""
        sections[header] = bbcode_to_text(content)
    return sections


def fetch_page(url: str, debug: bool = False) -> Optional[str]:
    log(f"Fetching: {url}", debug)
    try:
        session = requests.Session()
        resp = session.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        log(f"Got {len(resp.text)} bytes, status {resp.status_code}", debug)
        return resp.text
    except requests.RequestException as e:
        log(f"Fetch error: {e}", debug)
        return None


def extract_environment(html: str, debug: bool = False) -> Optional[dict]:
    marker = 'window.environment = '
    idx = html.find(marker)
    if idx < 0:
        return None
    json_start = html.find('{', idx)
    if json_start < 0:
        return None
    depth = 0
    i = json_start
    while i < len(html):
        if html[i] == '{':
            depth += 1
        elif html[i] == '}':
            depth -= 1
            if depth == 0:
                break
        i += 1
    json_str = html[json_start:i + 1]
    try:
        data = json.loads(json_str)
        return data
    except json.JSONDecodeError:
        return None


def extract_preview_from_environment(env: dict) -> Optional[dict]:
    preview = env.get('eventPreview')
    if not preview:
        return None
    return preview


def fetch_odds_from_api(event_id: str, sport: str, debug: bool = False) -> list:
    if not event_id:
        return []
    odds_list = []
    try:
        feed_url = "https://global.ds.lsapp.eu/odds/pq_graphql"
        query = {
            "query": "query OddsComparison($eventId: String!, $bettingType: String!, $scope: String!) { oddsComparison(eventId: $eventId, bettingType: $bettingType, scope: $scope) { bookmakers { bookmaker { id name } odds { value } } } }",
            "variables": {"eventId": event_id, "bettingType": "moneyline", "scope": "ft"}
        }
        resp = requests.post(feed_url, json=query, headers=ODDS_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            comparison = data.get('data', {}).get('oddsComparison', {})
            if comparison and comparison.get('bookmakers'):
                for bm in comparison['bookmakers']:
                    bm_name = bm.get('bookmaker', {}).get('name', 'unknown')
                    odds_values = bm.get('odds', [])
                    if odds_values:
                        ts = datetime.now(PARIS_TZ).isoformat()
                        if sport.lower() == 'tennis' and len(odds_values) >= 2:
                            odds_list.append({"bookmaker": bm_name, "market": "Match Winner", "selection": "1", "odd": float(odds_values[0].get('value', 0)), "timestamp": ts})
                            odds_list.append({"bookmaker": bm_name, "market": "Match Winner", "selection": "2", "odd": float(odds_values[1].get('value', 0)), "timestamp": ts})
                        elif len(odds_values) >= 3:
                            odds_list.append({"bookmaker": bm_name, "market": "1X2", "selection": "1", "odd": float(odds_values[0].get('value', 0)), "timestamp": ts})
                            odds_list.append({"bookmaker": bm_name, "market": "1X2", "selection": "N", "odd": float(odds_values[1].get('value', 0)), "timestamp": ts})
                            odds_list.append({"bookmaker": bm_name, "market": "1X2", "selection": "2", "odd": float(odds_values[2].get('value', 0)), "timestamp": ts})
    except Exception as e:
        log(f"Odds fetch error: {e}", debug)
    return odds_list


def extract_odds_from_html(html: str, event_id: str, sport: str, debug: bool = False) -> list:
    odds_list = []
    odds_values = re.findall(r'data-odds-value="(\d+\.\d{2})"', html)
    if odds_values:
        ts = datetime.now(PARIS_TZ).isoformat()
        if sport == "tennis" and len(odds_values) >= 2:
            odds_list.append({"bookmaker": "flashscore_embedded", "market": "Match Winner", "selection": "1", "odd": float(odds_values[0]), "timestamp": ts})
            odds_list.append({"bookmaker": "flashscore_embedded", "market": "Match Winner", "selection": "2", "odd": float(odds_values[1]), "timestamp": ts})
        elif len(odds_values) >= 3:
            odds_list.append({"bookmaker": "flashscore_embedded", "market": "1X2", "selection": "1", "odd": float(odds_values[0]), "timestamp": ts})
            odds_list.append({"bookmaker": "flashscore_embedded", "market": "1X2", "selection": "N", "odd": float(odds_values[1]), "timestamp": ts})
            odds_list.append({"bookmaker": "flashscore_embedded", "market": "1X2", "selection": "2", "odd": float(odds_values[2]), "timestamp": ts})
    return odds_list


def parse_match_preview(url: str, debug: bool = False) -> Optional[dict]:
    html = fetch_page(url, debug)
    if not html:
        return None
    env = extract_environment(html, debug)
    if not env:
        return None
    header = env.get('header', {})
    participants = env.get('participantsData', {})
    mid = env.get('event_id_c', '')
    sport_name = env.get('sport_name', '')
    competition = ""
    if header:
        tournament_data = header.get('tournament', {})
        if isinstance(tournament_data, dict):
            category = tournament_data.get('category', '')
            tournament_name = tournament_data.get('tournament', '')
            competition = f"{category} - {tournament_name}" if category else tournament_name
        else:
            competition = header.get('country_name', '')
    player_1 = ""
    player_2 = ""
    if participants:
        home = participants.get('home', [])
        away = participants.get('away', [])
        if isinstance(home, list) and home:
            player_1 = home[0].get('seo_name', '') or home[0].get('name', '')
        elif isinstance(home, dict):
            player_1 = home.get('seo_name', '') or home.get('name', '')
        if isinstance(away, list) and away:
            player_2 = away[0].get('seo_name', '') or away[0].get('name', '')
        elif isinstance(away, dict):
            player_2 = away.get('seo_name', '') or away.get('name', '')
    event_stage_time = env.get('eventStageStartTime')
    time_paris = ""
    date_str = ""
    if event_stage_time:
        try:
            ts = int(event_stage_time)
            dt = datetime.fromtimestamp(ts, tz=PARIS_TZ)
            time_paris = dt.strftime("%H:%M")
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError, OSError):
            pass
    preview_raw = extract_preview_from_environment(env)
    sport_lower = (sport_name or "").lower()
    if 'tennis' in sport_lower:
        sport_category = "tennis"
    elif 'foot' in sport_lower or 'soccer' in sport_lower:
        sport_category = "football"
    elif 'basket' in sport_lower:
        sport_category = "basketball"
    elif 'hock' in sport_lower:
        sport_category = "hockey"
    else:
        sport_category = sport_lower or "unknown"
    result = {
        "sport": sport_category,
        "competition": competition,
        "date": date_str or datetime.now(PARIS_TZ).strftime("%Y-%m-%d"),
        "time_paris": time_paris,
        "participants": [player_1, player_2],
        "mid": mid,
        "url": url,
        "preview_available": preview_raw is not None,
        "preview_full_text": "",
        "betting_analysis": "",
        "odds": [],
        "retrieved_at": datetime.now(PARIS_TZ).isoformat(),
    }
    if sport_category == "tennis":
        result["player_1"] = player_1
        result["player_2"] = player_2
    else:
        result["home_team"] = player_1
        result["away_team"] = player_2
    if preview_raw:
        content_parsed = preview_raw.get('contentParsed', '')
        result["preview_full_text"] = bbcode_to_text(content_parsed)
        sections = extract_sections(content_parsed)
        for key in sections:
            if 'paris sportifs' in key.lower() or 'betting' in key.lower():
                result["betting_analysis"] = sections[key]
                break
    html_odds = extract_odds_from_html(html, mid, sport_category, debug)
    if html_odds:
        result["odds"] = html_odds
    if not result["odds"]:
        api_odds = fetch_odds_from_api(mid, sport_category, debug)
        if api_odds:
            result["odds"] = api_odds
    return result


def extract_match_urls_from_sport_page(sport: str, debug: bool = False) -> list:
    base_url = SPORT_URLS.get(sport, SPORT_URLS['football'])
    html = fetch_page(base_url, debug)
    if not html:
        return []
    match_urls = []
    patterns = [
        r'href="(/match/[^"]+)"',
        r'href="(/tennis/[^"]+/[^"]+/)"',
        r'id="g_\d+_(\w+)"',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, html)
        for m in matches:
            if m.startswith('/'):
                full_url = f"https://www.flashscore.fr{m}"
                if full_url not in match_urls:
                    match_urls.append(full_url)
    return match_urls


def scan_sport_matches(sport: str, debug: bool = False) -> list:
    results = []
    match_urls = extract_match_urls_from_sport_page(sport, debug)
    if not match_urls:
        return results
    for i, url in enumerate(match_urls[:50]):
        if i > 0:
            time.sleep(1.5)
        result = parse_match_preview(url, debug)
        if result:
            results.append(result)
    return results


def write_outputs(results: list, date_str: str = None):
    """Write outputs with merge by mid, preview_first_seen_at, post-match integrity, audit.json."""
    if date_str is None:
        date_str = get_today_date()

    now_paris = datetime.now(PARIS_TZ)
    scan_time_iso = now_paris.isoformat()

    data_dir = get_data_dir(date_str)
    data_dir.mkdir(parents=True, exist_ok=True)

    json_path  = data_dir / "flashscore_previews.json"
    audit_path = data_dir / "audit.json"

    # -- Load existing indexed by mid ----------------------------------------
    existing: dict = {}
    if json_path.exists():
        try:
            with open(json_path, encoding='utf-8') as f:
                for entry in json.load(f):
                    m = entry.get('mid', '')
                    if m:
                        existing[m] = entry
        except (json.JSONDecodeError, OSError):
            pass

    # -- Audit counters (this scan only) -------------------------------------
    events_seen                  = len(results)
    previews_found               = 0
    new_previews_added           = 0
    duplicates_merged            = 0
    invalid_mid_excluded         = 0
    post_start_previews_rejected = 0

    for r in results:
        mid = r.get('mid', '')

        if not mid:
            invalid_mid_excluded += 1
            continue

        # Match start check
        match_started = False
        try:
            dt_str = f"{r.get('date', date_str)} {r.get('time_paris', '')}"
            match_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=PARIS_TZ)
            match_started = now_paris >= match_dt
        except (ValueError, TypeError):
            pass

        has_preview = (
            r.get('preview_available', False)
            and bool(r.get('betting_analysis', '').strip())
        )
        if has_preview:
            previews_found += 1

        old = existing.get(mid)

        if old is None:
            if has_preview and not match_started:
                r['preview_first_seen_at'] = scan_time_iso
                new_previews_added += 1
            elif has_preview and match_started:
                post_start_previews_rejected += 1
                r['preview_available'] = False
                r['preview_full_text']  = ''
                r['betting_analysis']   = ''
            existing[mid] = r
        else:
            duplicates_merged += 1
            merged = dict(r)

            # NEVER overwrite preview_first_seen_at
            if 'preview_first_seen_at' in old:
                merged['preview_first_seen_at'] = old['preview_first_seen_at']
            elif has_preview and not match_started:
                merged['preview_first_seen_at'] = scan_time_iso
                new_previews_added += 1

            # Count post-match rejection independently
            if has_preview and match_started:
                post_start_previews_rejected += 1

            # Keep old preview if new scan is less complete
            old_has_preview = (
                old.get('preview_available', False)
                and bool(old.get('betting_analysis', '').strip())
            )
            if old_has_preview and (not has_preview or match_started):
                merged['preview_available'] = old['preview_available']
                merged['preview_full_text']  = old.get('preview_full_text', '')
                merged['betting_analysis']   = old.get('betting_analysis', '')

            existing[mid] = merged

    merged_list = list(existing.values())

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(merged_list, f, indent=2, ensure_ascii=False)
    print(f"Written: {json_path} ({len(merged_list)} matches)")

    root_json = Path("flashscore_previews.json")
    with open(root_json, 'w', encoding='utf-8') as f:
        json.dump(merged_list, f, indent=2, ensure_ascii=False)
    print(f"Written: {root_json} (latest copy)")

    picks_path = data_dir / "flashscore_picks.txt"
    _write_picks_file(merged_list, picks_path)
    root_picks = Path("flashscore_picks.txt")
    _write_picks_file(merged_list, root_picks)
    print(f"Written: {picks_path} + root copy")

    # -- Audit ----------------------------------------------------------------
    audit: dict = {}
    if audit_path.exists():
        try:
            with open(audit_path, encoding='utf-8') as f:
                audit = json.load(f)
        except (json.JSONDecodeError, OSError):
            audit = {}

    audit['scan_times']                   = audit.get('scan_times', []) + [scan_time_iso]
    audit['last_scan']                    = scan_time_iso
    audit['events_seen']                  = audit.get('events_seen', 0)                  + events_seen
    audit['previews_found']               = audit.get('previews_found', 0)               + previews_found
    audit['new_previews_added']           = audit.get('new_previews_added', 0)           + new_previews_added
    audit['duplicates_merged']            = audit.get('duplicates_merged', 0)            + duplicates_merged
    audit['invalid_mid_excluded']         = audit.get('invalid_mid_excluded', 0)         + invalid_mid_excluded
    audit['post_start_previews_rejected'] = audit.get('post_start_previews_rejected', 0) + post_start_previews_rejected
    audit['total_entries']               = len(merged_list)

    with open(audit_path, 'w', encoding='utf-8') as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)
    print(f"Written: {audit_path}")

def _write_picks_file(results: list, picks_path: Path):
    with open(picks_path, 'w', encoding='utf-8') as f:
        for r in results:
            sport_label = r.get('sport', '').upper()
            time_str = r.get('time_paris', '??:??')
            participants = r.get('participants', ['?', '?'])
            p1 = participants[0] if len(participants) > 0 else '?'
            p2 = participants[1] if len(participants) > 1 else '?'
            f.write(f"{time_str} | {sport_label} | {p1} - {p2}\n")
            if r.get('preview_full_text'):
                conclusion = r.get('betting_analysis', '')
                if not conclusion:
                    paragraphs = [p.strip() for p in r['preview_full_text'].split('\n') if p.strip()]
                    if paragraphs:
                        conclusion = paragraphs[-1]
                if conclusion:
                    f.write(f"Flashscore conclusion:\n{conclusion}\n")
            f.write(f"URL: {r['url']}\n")
            f.write("---\n\n")


def fetch_match_result(url: str, debug: bool = False) -> Optional[dict]:
    html = fetch_page(url, debug)
    if not html:
        return None
    env = extract_environment(html, debug)
    if not env:
        return None
    stage_type = env.get('eventStageTypeId')
    if stage_type is not None and int(stage_type) < 3:
        return None
    score_home = None
    score_away = None
    score_patterns = [
        r'"home_score"\s*:\s*"?(\d+)"?[^}]*"away_score"\s*:\s*"?(\d+)"?',
        r'"homeScore"\s*:\s*"?(\d+)"?[^}]*"awayScore"\s*:\s*"?(\d+)"?',
        r'class="[^"]*detailScore[^"]*"[^>]*>\s*(\d+)\s*[-:]\s*(\d+)',
        r'"score"\s*:\s*"(\d+)\s*[-:]\s*(\d+)"',
    ]
    for pattern in score_patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            score_home = int(match.group(1))
            score_away = int(match.group(2))
            break
    if score_home is None or score_away is None:
        common_feed = env.get('common_feed', [])
        if isinstance(common_feed, list):
            da_val = db_val = None
            for item in common_feed:
                if isinstance(item, dict):
                    if 'DA' in item: da_val = item['DA']
                    if 'DB' in item: db_val = item['DB']
            if da_val is not None and db_val is not None and stage_type and int(stage_type) >= 3:
                score_home = int(da_val)
                score_away = int(db_val)
    if score_home is not None and score_away is not None:
        score_str = f"{score_home}-{score_away}"
        if score_home > score_away: winner = "home"
        elif score_away > score_home: winner = "away"
        else: winner = "draw"
        return {"score": score_str, "winner": winner, "btts": score_home > 0 and score_away > 0, "total_goals": score_home + score_away, "retrieved_at": datetime.now(PARIS_TZ).isoformat()}
    return None


def cmd_results(date_str: str, debug: bool = False):
    data_dir = get_data_dir(date_str)
    previews_path = data_dir / "flashscore_previews.json"
    if not previews_path.exists():
        print(f"Error: No previews file found at {previews_path}")
        sys.exit(1)
    with open(previews_path, 'r', encoding='utf-8') as f:
        previews = json.load(f)
    print(f"Loaded {len(previews)} matches from {previews_path}")
    results_data = []
    for i, match in enumerate(previews):
        url = match.get('url', '')
        if not url:
            results_data.append(match)
            continue
        if i > 0:
            time.sleep(1.5)
        result = fetch_match_result(url, debug)
        match_with_result = dict(match)
        match_with_result["result"] = result
        results_data.append(match_with_result)
    results_path = data_dir / "flashscore_results.json"
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)
    print(f"Written: {results_path} ({len(results_data)} matches)")


def main():
    parser = argparse.ArgumentParser(description="Flashscore Pre-Match Preview Crawler v2")
    parser.add_argument('--url', help='Single match URL to crawl')
    parser.add_argument('--sport', choices=['tennis', 'football', 'basketball', 'hockey', 'all'], help='Sport to scan')
    parser.add_argument('--debug', action='store_true', help='Enable verbose debug output')
    parser.add_argument('--output', default='.', help='Output directory')
    parser.add_argument('--results', metavar='DATE', help='Fetch results for a past scan (YYYY-MM-DD)')
    args = parser.parse_args()
    if not args.url and not args.sport and not args.results:
        parser.print_help()
        sys.exit(1)
    if args.results:
        cmd_results(args.results, args.debug)
        return
    results = []
    if args.url:
        result = parse_match_preview(args.url, args.debug)
        if result:
            results.append(result)
            if result['preview_available']:
                print(f"MATCH: {result['participants'][0]} vs {result['participants'][1]}")
                print(f"Sport: {result['sport']} | Competition: {result['competition']}")
                print(f"Date: {result['date']} {result['time_paris']} (Paris)")
            else:
                print(f"No preview available for this match.")
        else:
            print("Failed to fetch or parse the match page.")
            sys.exit(1)
    elif args.sport:
        sports = list(SPORT_URLS.keys()) if args.sport == 'all' else [args.sport]
        for sport in sports:
            print(f"Scanning {sport}...")
            sport_results = scan_sport_matches(sport, args.debug)
            results.extend(sport_results)
            print(f"  Found {len(sport_results)} matches with data")
    if results:
        write_outputs(results)
    else:
        print("No results to write.")
        date_str = get_today_date()
        data_dir = get_data_dir(date_str)
        data_dir.mkdir(parents=True, exist_ok=True)
        json_path = data_dir / "flashscore_previews.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump([], f)
        print(f"Written empty: {json_path}")


if __name__ == '__main__':
    main()

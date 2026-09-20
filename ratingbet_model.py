"""RatingBet Model scraper — fetches math predictions and saves raw snapshot."""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup


RATINGBET_BASE = "https://ratingbet.com/math-predictions"
PARIS_TZ = timezone(timedelta(hours=2))  # CEST (summer); adjust to +1 in winter if needed
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _parse_odd(text: str) -> float | None:
    text = text.strip()
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_pct(text: str) -> int | None:
    text = text.strip().rstrip("%")
    if not text or text == "-":
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _extract_slug(href: str) -> str:
    m = re.search(r"/match/([^/]+)/?", href)
    return m.group(1) if m else ""


def _map_market_title(title: str) -> tuple[str, str]:
    """Map a display market title to (market_key, outcome_key)."""
    title = title.strip()
    mapping = {
        "W1": ("result", "W1"),
        "X": ("result", "X"),
        "W2": ("result", "W2"),
        "O 2.5": ("total_25", "over"),
        "U 2.5": ("total_25", "under"),
        "Yes": ("btts", "yes"),
        "No": ("btts", "no"),
    }
    return mapping.get(title, ("other", title))


def _parse_best_tip(tip_div) -> dict:
    """Parse the best tip section of a match."""
    result = {"market": None, "outcome": None, "odd": None}
    if not tip_div:
        return result

    market_div = tip_div.select_one(".match-value-tip__market")
    if market_div:
        spans = market_div.find_all("span")
        texts = [s.get_text(strip=True) for s in spans if s.get_text(strip=True)]
        if len(texts) >= 2:
            result["market"] = texts[0]
            result["outcome"] = texts[1]
        elif len(texts) == 1:
            full = market_div.get_text(strip=True)
            if ":" in full:
                parts = full.split(":", 1)
                result["market"] = parts[0].strip()
                result["outcome"] = parts[1].strip()

    odd_span = tip_div.select_one(".match-value-tip__odd")
    if odd_span:
        result["odd"] = _parse_odd(odd_span.get_text())

    return result


def parse_ratingbet_html(html: str, date: str) -> dict:
    """Parse RatingBet HTML into structured data."""
    soup = BeautifulSoup(html, "html.parser")
    matches = []

    sections = soup.select("div.robobet-game-section")
    for section in sections:
        league_el = section.select_one("span.section-title")
        league = league_el.get_text(strip=True) if league_el else "Unknown"

        match_items = section.select("div.match-item.match-item_predictions")
        for item in match_items:
            link = item.select_one("a.match-item__link")
            href = link.get("href", "") if link else ""
            slug = _extract_slug(href)

            time_el = item.select_one("span.match-item__time")
            time_str = time_el.get_text(strip=True) if time_el else ""

            host_el = item.select_one("div.match-item__team.host .team-name")
            guest_el = item.select_one("div.match-item__team.guest .team-name")
            home_team = host_el.get_text(strip=True) if host_el else ""
            away_team = guest_el.get_text(strip=True) if guest_el else ""

            if not slug and not home_team:
                continue

            markets_raw = {
                "result": {
                    "W1": {"odd": None, "prob_pct": None},
                    "X": {"odd": None, "prob_pct": None},
                    "W2": {"odd": None, "prob_pct": None},
                },
                "total_25": {
                    "over": {"odd": None, "prob_pct": None},
                    "under": {"odd": None, "prob_pct": None},
                },
                "btts": {
                    "yes": {"odd": None, "prob_pct": None},
                    "no": {"odd": None, "prob_pct": None},
                },
            }

            market_divs = item.select("div.match-item-market")
            for md in market_divs:
                title_el = md.select_one(".match-item-market__title")
                odd_el = md.select_one(".match-item-market__odd")
                pct_el = md.select_one(".match-item-market__percent")

                if not title_el:
                    continue

                market_key, outcome_key = _map_market_title(title_el.get_text())
                if market_key in markets_raw and outcome_key in markets_raw[market_key]:
                    markets_raw[market_key][outcome_key] = {
                        "odd": _parse_odd(odd_el.get_text()) if odd_el else None,
                        "prob_pct": _parse_pct(pct_el.get_text()) if pct_el else None,
                    }

            tip_div = item.select_one("div.match-value-tip")
            best_tip = _parse_best_tip(tip_div)

            match_data = {
                "match_id": slug,
                "home_team": home_team,
                "away_team": away_team,
                "date": date,
                "time_utc": "",
                "time_paris": time_str,
                "league": league,
                "markets": markets_raw,
                "best_tip": best_tip,
            }
            matches.append(match_data)

    return {
        "fetched_at": datetime.now(PARIS_TZ).isoformat(),
        "date": date,
        "source_url": f"{RATINGBET_BASE}/{date}/",
        "match_count": len(matches),
        "matches": matches,
    }


def _fetch_html(url: str) -> str:
    """Fetch HTML with fallback to cloudscraper if requests is blocked by Cloudflare."""
    # Attempt 1: plain requests
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        if "match-item" in resp.text:
            return resp.text
    except Exception:
        pass

    # Attempt 2: cloudscraper (bypasses some CF challenges)
    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "linux", "desktop": True}
        )
        resp = scraper.get(url, timeout=30)
        resp.raise_for_status()
        if "match-item" in resp.text:
            return resp.text
    except ImportError:
        pass
    except Exception:
        pass

    raise RuntimeError(
        f"Could not fetch {url} -- Cloudflare challenge detected. "
        "Options: (a) install cloudscraper, (b) pre-fetch HTML to a file and use --html-file, "
        "(c) use a headless browser fetcher."
    )


def fetch_ratingbet_model(date: str) -> dict:
    """Fetch and parse RatingBet data for a given date."""
    url = f"{RATINGBET_BASE}/{date}/"
    html = _fetch_html(url)
    return parse_ratingbet_html(html, date)


def fetch_ratingbet_model_from_html(html: str, date: str) -> dict:
    """Parse pre-fetched HTML (for testing or alternative fetch methods)."""
    return parse_ratingbet_html(html, date)


def save_snapshot(data: dict, date: str) -> str:
    """Save raw snapshot -- only if file doesn't already exist (anti-leakage)."""
    dir_path = os.path.join("data", date)
    os.makedirs(dir_path, exist_ok=True)
    filepath = os.path.join(dir_path, "ratingbet_model_raw.json")

    if os.path.exists(filepath):
        print(f"[SKIP] Snapshot already exists: {filepath}")
        return filepath

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[SAVED] {filepath}")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="RatingBet Model scraper")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    parser.add_argument("--html-file", help="Use local HTML file instead of fetching")
    args = parser.parse_args()

    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    if not date_pattern.match(args.date):
        print(f"[ERROR] Invalid date format: {args.date}. Expected YYYY-MM-DD.", file=sys.stderr)
        sys.exit(1)

    if args.html_file:
        with open(args.html_file, "r", encoding="utf-8") as f:
            html = f.read()
        data = fetch_ratingbet_model_from_html(html, args.date)
    else:
        data = fetch_ratingbet_model(args.date)

    path = save_snapshot(data, args.date)
    print(f"\n=== RatingBet Model Summary ===")
    print(f"Date: {data['date']}")
    print(f"Matches parsed: {data['match_count']}")
    print(f"Snapshot: {path}")

    if data["matches"]:
        leagues = set(m["league"] for m in data["matches"])
        print(f"Leagues: {len(leagues)}")
        for league in sorted(leagues):
            count = sum(1 for m in data["matches"] if m["league"] == league)
            print(f"  - {league}: {count} matches")


if __name__ == "__main__":
    main()

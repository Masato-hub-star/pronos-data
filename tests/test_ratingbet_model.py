"""Tests for ratingbet_model.py."""

import json
import os
import tempfile

import pytest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ratingbet_model import parse_ratingbet_html, save_snapshot


SAMPLE_HTML_2_MATCHES = """
<html><body>
<div class="robobet-page__games js-games-container">
<div class="robobet-game-section js-sticky-section by-league block_white mb-8 math">
  <div class="robobet-game-section__head-wrapper">
    <div class="robobet-game-section__head-sticky">
      <div class="robobet-game-section__head-sticky-wrapper">
        <div class="robobet-game-section__title mb-16">
          <a class="robobet-game-section__tournament-link" href="/football/england-premier-league/">
            <span class="section-title">England: English Premier League</span>
          </a>
        </div>
      </div>
    </div>
  </div>
  <div class="robobet-game-section__wrapper">
    <div class="match-item match-item_predictions planned-match">
      <a href="/football/match/manchester-city-vs-sunderland/" class="match-item__link">
        <div class="match-item__left fl_c">
          <span class="match-item__time">15:00</span>
        </div>
        <div class="match-item__main">
          <div class="match-item__team host fl_c_sb mb-4">
            <div class="team-header team-left fl_c">
              <span class="team-header__team-title team-name one-row">Manchester City</span>
            </div>
          </div>
          <div class="match-item__team guest fl_c_sb">
            <div class="team-header team-left fl_c">
              <span class="team-header__team-title team-name one-row">Sunderland</span>
            </div>
          </div>
        </div>
      </a>
      <div class="match-item__markets fl_c">
        <div class="match-item-market math fl_col">
          <span class="match-item-market__title">W1</span>
          <span class="match-item-market__odd block_yellow">1.37</span>
          <span class="match-item-market__percent">67%</span>
        </div>
        <div class="match-item-market math fl_col">
          <span class="match-item-market__title">O 2.5</span>
          <span class="match-item-market__odd block_white-border">1.53</span>
          <span class="match-item-market__percent">50%</span>
        </div>
        <div class="match-item-market math fl_col">
          <span class="match-item-market__title">No</span>
          <span class="match-item-market__odd block_white-border">1.87</span>
          <span class="match-item-market__percent">57%</span>
        </div>
      </div>
      <div class="match-value-tip fl_c_sb">
        <div class="match-value-tip__left fl_col">
          <div class="match-value-tip__market overflow-elipsis">
            <span>Result</span>:<span>W1</span>
          </div>
        </div>
        <div class="match-value-tip__right fl_c">
          <span class="match-value-tip__odd mr-4">1.37</span>
        </div>
      </div>
    </div>
    <div class="match-item match-item_predictions planned-match">
      <a href="/football/match/arsenal-vs-everton/" class="match-item__link">
        <div class="match-item__left fl_c">
          <span class="match-item__time">17:30</span>
        </div>
        <div class="match-item__main">
          <div class="match-item__team host fl_c_sb mb-4">
            <div class="team-header team-left fl_c">
              <span class="team-header__team-title team-name one-row">Arsenal</span>
            </div>
          </div>
          <div class="match-item__team guest fl_c_sb">
            <div class="team-header team-left fl_c">
              <span class="team-header__team-title team-name one-row">Everton</span>
            </div>
          </div>
        </div>
      </a>
      <div class="match-item__markets fl_c">
        <div class="match-item-market math fl_col">
          <span class="match-item-market__title">W1</span>
          <span class="match-item-market__odd block_yellow">1.22</span>
          <span class="match-item-market__percent">75%</span>
        </div>
        <div class="match-item-market math fl_col">
          <span class="match-item-market__title">O 2.5</span>
          <span class="match-item-market__odd block_white-border">1.65</span>
          <span class="match-item-market__percent">55%</span>
        </div>
        <div class="match-item-market math fl_col">
          <span class="match-item-market__title">Yes</span>
          <span class="match-item-market__odd block_white-border">1.90</span>
          <span class="match-item-market__percent">48%</span>
        </div>
      </div>
      <div class="match-value-tip fl_c_sb">
        <div class="match-value-tip__left fl_col">
          <div class="match-value-tip__market overflow-elipsis">
            <span>Result</span>:<span>W1</span>
          </div>
        </div>
        <div class="match-value-tip__right fl_c">
          <span class="match-value-tip__odd mr-4">1.22</span>
        </div>
      </div>
    </div>
  </div>
</div>
</div>
</body></html>
"""


class TestParseHtml:
    def test_parse_two_matches(self):
        result = parse_ratingbet_html(SAMPLE_HTML_2_MATCHES, "2026-09-20")
        assert result["date"] == "2026-09-20"
        assert result["match_count"] == 2
        assert len(result["matches"]) == 2

    def test_parse_teams(self):
        result = parse_ratingbet_html(SAMPLE_HTML_2_MATCHES, "2026-09-20")
        m0 = result["matches"][0]
        assert m0["home_team"] == "Manchester City"
        assert m0["away_team"] == "Sunderland"
        m1 = result["matches"][1]
        assert m1["home_team"] == "Arsenal"
        assert m1["away_team"] == "Everton"

    def test_parse_slug(self):
        result = parse_ratingbet_html(SAMPLE_HTML_2_MATCHES, "2026-09-20")
        assert result["matches"][0]["match_id"] == "manchester-city-vs-sunderland"
        assert result["matches"][1]["match_id"] == "arsenal-vs-everton"

    def test_parse_markets(self):
        result = parse_ratingbet_html(SAMPLE_HTML_2_MATCHES, "2026-09-20")
        m0 = result["matches"][0]
        assert m0["markets"]["result"]["W1"]["odd"] == 1.37
        assert m0["markets"]["result"]["W1"]["prob_pct"] == 67
        assert m0["markets"]["total_25"]["over"]["odd"] == 1.53
        assert m0["markets"]["btts"]["no"]["odd"] == 1.87
        assert m0["markets"]["result"]["X"]["odd"] is None
        assert m0["markets"]["result"]["W2"]["odd"] is None

    def test_parse_best_tip(self):
        result = parse_ratingbet_html(SAMPLE_HTML_2_MATCHES, "2026-09-20")
        tip = result["matches"][0]["best_tip"]
        assert tip["market"] == "Result"
        assert tip["outcome"] == "W1"
        assert tip["odd"] == 1.37

    def test_parse_time(self):
        result = parse_ratingbet_html(SAMPLE_HTML_2_MATCHES, "2026-09-20")
        assert result["matches"][0]["time_paris"] == "15:00"
        assert result["matches"][1]["time_paris"] == "17:30"

    def test_parse_league(self):
        result = parse_ratingbet_html(SAMPLE_HTML_2_MATCHES, "2026-09-20")
        assert result["matches"][0]["league"] == "England: English Premier League"

    def test_empty_html(self):
        result = parse_ratingbet_html("<html><body></body></html>", "2026-09-20")
        assert result["match_count"] == 0
        assert result["matches"] == []


class TestSaveSnapshot:
    def test_save_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                data = {"date": "2026-09-20", "matches": [], "match_count": 0}
                path = save_snapshot(data, "2026-09-20")
                assert os.path.exists(path)
                with open(path) as f:
                    loaded = json.load(f)
                assert loaded["date"] == "2026-09-20"
            finally:
                os.chdir(old_cwd)

    def test_anti_leakage_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                data1 = {"date": "2026-09-20", "version": 1, "matches": [], "match_count": 0}
                save_snapshot(data1, "2026-09-20")
                data2 = {"date": "2026-09-20", "version": 2, "matches": [], "match_count": 0}
                save_snapshot(data2, "2026-09-20")
                path = os.path.join("data", "2026-09-20", "ratingbet_model_raw.json")
                with open(path) as f:
                    loaded = json.load(f)
                assert loaded["version"] == 1
            finally:
                os.chdir(old_cwd)


class TestInvalidDate:
    def test_parse_with_any_date_string(self):
        result = parse_ratingbet_html(SAMPLE_HTML_2_MATCHES, "invalid-date")
        assert result["date"] == "invalid-date"
        assert result["match_count"] == 2

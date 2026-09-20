"""Tests for ratingbet_normalizer.py."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ratingbet_normalizer import normalize_team, slug_to_teams, participants_to_normalized


class TestNormalizeTeam:
    def test_olympique_lyonnais(self):
        assert normalize_team("Olympique Lyonnais") == "lyon"

    def test_psg_matches_paris(self):
        assert normalize_team("PSG") == normalize_team("Paris Saint-Germain")

    def test_man_city_variants(self):
        assert normalize_team("Man City") == normalize_team("Manchester City")
        assert normalize_team("Man City") == "manchester city"

    def test_man_utd_variants(self):
        r1 = normalize_team("Man Utd")
        r2 = normalize_team("Man United")
        r3 = normalize_team("Manchester United")
        assert r1 == r2 == r3 == "manchester united"

    def test_atletico_variants(self):
        r1 = normalize_team("Atletico de Madrid")
        r2 = normalize_team("Atletico")
        assert r1 == r2 == "atletico madrid"

    def test_stade_rennais(self):
        assert normalize_team("Stade Rennais") == "rennes"

    def test_bayern_variants(self):
        assert normalize_team("Bayern Munich") == normalize_team("FC Bayern Munich")
        assert normalize_team("Bayern Munich") == "bayern"

    def test_inter_variants(self):
        assert normalize_team("Inter Milan") == normalize_team("Internazionale")
        assert normalize_team("Inter Milan") == "inter"

    def test_unknown_team_passthrough(self):
        result = normalize_team("Some Random FC")
        assert result == "some random fc"

    def test_accent_stripping(self):
        result = normalize_team("Sao Paulo")
        assert result == "sao paulo"

    def test_case_insensitive(self):
        assert normalize_team("ARSENAL") == normalize_team("arsenal")

    def test_tottenham_spurs(self):
        assert normalize_team("Spurs") == normalize_team("Tottenham Hotspur")
        assert normalize_team("Spurs") == "tottenham"

    def test_wolves(self):
        assert normalize_team("Wolves") == normalize_team("Wolverhampton Wanderers")

    def test_brighton(self):
        assert normalize_team("Brighton & Hove Albion") == "brighton"
        assert normalize_team("Brighton and Hove Albion") == "brighton"


class TestSlugToTeams:
    def test_basic_slug(self):
        home, away = slug_to_teams("manchester-city-vs-sunderland")
        assert home == "manchester city"
        assert away == "sunderland"

    def test_slug_with_path(self):
        home, away = slug_to_teams("/football/match/arsenal-vs-everton/")
        assert home == "arsenal"
        assert away == "everton"

    def test_slug_with_hyphenated_names(self):
        home, away = slug_to_teams("crystal-palace-vs-west-ham")
        assert home == "crystal palace"
        assert away == "west ham"

    def test_invalid_slug_no_vs(self):
        with pytest.raises(ValueError, match="Invalid slug"):
            slug_to_teams("manchester-city-sunderland")


class TestParticipantsToNormalized:
    def test_basic_pair(self):
        h, a = participants_to_normalized(["Olympique Lyonnais", "Stade Rennais"])
        assert h == "lyon"
        assert a == "rennes"

    def test_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 2"):
            participants_to_normalized(["Only One"])

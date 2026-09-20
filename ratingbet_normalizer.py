"""Team name normalizer for RatingBet <-> Flashscore matching."""

import re
import unicodedata


ALIASES: dict[str, str] = {
    # France
    "olympique lyonnais": "lyon",
    "olympique de marseille": "marseille",
    "ol": "lyon",
    "om": "marseille",
    "psg": "paris saint-germain",
    "paris sg": "paris saint-germain",
    "paris saint germain": "paris saint-germain",
    "as monaco": "monaco",
    "ogc nice": "nice",
    "stade rennais": "rennes",
    "stade rennais fc": "rennes",
    "rc lens": "lens",
    "rc strasbourg": "strasbourg",
    "fc nantes": "nantes",
    "losc lille": "lille",
    "losc": "lille",
    "montpellier hsc": "montpellier",
    "as saint-etienne": "saint-etienne",
    "as saint etienne": "saint-etienne",
    "toulouse fc": "toulouse",
    "stade brestois": "brest",
    "stade brestois 29": "brest",
    "fc metz": "metz",
    "aj auxerre": "auxerre",
    "le havre ac": "le havre",
    "angers sco": "angers",
    "stade de reims": "reims",
    # England
    "man city": "manchester city",
    "man utd": "manchester united",
    "man united": "manchester united",
    "manchester utd": "manchester united",
    "spurs": "tottenham",
    "tottenham hotspur": "tottenham",
    "wolves": "wolverhampton",
    "wolverhampton wanderers": "wolverhampton",
    "newcastle united": "newcastle",
    "newcastle utd": "newcastle",
    "west ham united": "west ham",
    "leicester city": "leicester",
    "leeds united": "leeds",
    "nottingham forest": "nottingham",
    "nottm forest": "nottingham",
    "nott'm forest": "nottingham",
    "aston villa fc": "aston villa",
    "sheffield united": "sheffield utd",
    "brighton & hove albion": "brighton",
    "brighton and hove albion": "brighton",
    "brighton hove albion": "brighton",
    "arsenal fc": "arsenal",
    "chelsea fc": "chelsea",
    "liverpool fc": "liverpool",
    "everton fc": "everton",
    "fulham fc": "fulham",
    "bournemouth": "bournemouth",
    "afc bournemouth": "bournemouth",
    "ipswich town": "ipswich",
    "crystal palace fc": "crystal palace",
    "sunderland afc": "sunderland",
    "burnley fc": "burnley",
    "luton town": "luton",
    "southampton fc": "southampton",
    # Spain
    "atletico de madrid": "atletico madrid",
    "atletico": "atletico madrid",
    "atletico madrid": "atletico madrid",
    "real madrid cf": "real madrid",
    "fc barcelona": "barcelona",
    "barca": "barcelona",
    "real sociedad": "real sociedad",
    "athletic bilbao": "athletic bilbao",
    "athletic club": "athletic bilbao",
    "real betis": "real betis",
    "real betis balompie": "real betis",
    "villarreal cf": "villarreal",
    "sevilla fc": "sevilla",
    "valencia cf": "valencia",
    "celta de vigo": "celta vigo",
    "celta": "celta vigo",
    "rcd mallorca": "mallorca",
    "rayo vallecano": "rayo vallecano",
    "deportivo alaves": "alaves",
    "ud las palmas": "las palmas",
    "getafe cf": "getafe",
    "girona fc": "girona",
    "ca osasuna": "osasuna",
    "real valladolid": "valladolid",
    "cd leganes": "leganes",
    "rcd espanyol": "espanyol",
    "deportivo de a coruna": "deportivo",
    "deportivo la coruna": "deportivo",
    "rc deportivo": "deportivo",
    # Germany
    "bayern munich": "bayern",
    "fc bayern munich": "bayern",
    "bayern munchen": "bayern",
    "bayern muenchen": "bayern",
    "fc bayern": "bayern",
    "borussia dortmund": "dortmund",
    "bvb": "dortmund",
    "bayer leverkusen": "leverkusen",
    "bayer 04 leverkusen": "leverkusen",
    "rb leipzig": "leipzig",
    "rasenballsport leipzig": "leipzig",
    "eintracht frankfurt": "frankfurt",
    "vfb stuttgart": "stuttgart",
    "vfl wolfsburg": "wolfsburg",
    "sc freiburg": "freiburg",
    "tsg hoffenheim": "hoffenheim",
    "1899 hoffenheim": "hoffenheim",
    "borussia monchengladbach": "gladbach",
    "borussia mgladbach": "gladbach",
    "b. monchengladbach": "gladbach",
    "fc augsburg": "augsburg",
    "1. fc union berlin": "union berlin",
    "union berlin": "union berlin",
    "1. fc heidenheim": "heidenheim",
    "fc st. pauli": "st. pauli",
    "sv werder bremen": "werder bremen",
    "werder bremen": "werder bremen",
    "1. fsv mainz 05": "mainz",
    "mainz 05": "mainz",
    "vfl bochum": "bochum",
    "holstein kiel": "kiel",
    "schalke 04": "schalke",
    "fc schalke 04": "schalke",
    "sv elversberg": "elversberg",
    "sc paderborn": "paderborn",
    "sc paderborn 07": "paderborn",
    # Italy
    "inter milan": "inter",
    "internazionale": "inter",
    "fc internazionale": "inter",
    "ac milan": "milan",
    "juventus fc": "juventus",
    "ssc napoli": "napoli",
    "as roma": "roma",
    "ss lazio": "lazio",
    "atalanta bc": "atalanta",
    "acf fiorentina": "fiorentina",
    "torino fc": "torino",
    "us lecce": "lecce",
    "genoa cfc": "genoa",
    "hellas verona": "verona",
    "udinese calcio": "udinese",
    "us sassuolo": "sassuolo",
    "cagliari calcio": "cagliari",
    "empoli fc": "empoli",
    "bologna fc": "bologna",
    "parma calcio": "parma",
    "parma calcio 1913": "parma",
    "como 1907": "como",
    "venezia fc": "venezia",
    "us salernitana": "salernitana",
    "monza": "monza",
    "frosinone calcio": "frosinone",
    # Portugal
    "sl benfica": "benfica",
    "fc porto": "porto",
    "sporting cp": "sporting",
    "sporting lisbon": "sporting",
    "sc braga": "braga",
    "vitoria guimaraes": "guimaraes",
    "vitoria de guimaraes": "guimaraes",
    "moreirense fc": "moreirense",
    "santa clara": "santa clara",
    "casa pia ac": "casa pia",
    "estoril praia": "estoril",
    "estrela da amadora": "estrela amadora",
    "academico viseu": "academico viseu",
    "gd estoril praia": "estoril",
    # Netherlands
    "ajax amsterdam": "ajax",
    "psv eindhoven": "psv",
    "feyenoord rotterdam": "feyenoord",
    "az alkmaar": "az",
    "fc twente": "twente",
    "fc utrecht": "utrecht",
    "nec nijmegen": "nec",
    "go ahead eagles": "go ahead eagles",
    # Belgium
    "club brugge": "club brugge",
    "club bruges": "club brugge",
    "rsc anderlecht": "anderlecht",
    "standard liege": "standard",
    "krc genk": "genk",
    "racing genk": "genk",
    "royal antwerp": "antwerp",
    "royal antwerp fc": "antwerp",
    "union saint-gilloise": "union sg",
    "union st-gilloise": "union sg",
    "union st. gilloise": "union sg",
    "union st gilloise": "union sg",
    "sint-truiden": "sint-truiden",
    "st truiden": "sint-truiden",
    "kv kortrijk": "kortrijk",
    "waasland-beveren": "waasland-beveren",
    "kv westerlo": "westerlo",
    # Turkey
    "galatasaray sk": "galatasaray",
    "fenerbahce sk": "fenerbahce",
    "besiktas jk": "besiktas",
    # Greece
    "olympiacos piraeus": "olympiacos",
    "olympiacos cfp": "olympiacos",
    "panathinaikos fc": "panathinaikos",
    "aek athens fc": "aek athens",
    "aek athens": "aek athens",
    "paok thessaloniki": "paok",
    "paok thessaloniki fc": "paok",
    "paok fc": "paok",
    "ofi crete": "ofi crete",
    "asteras tripolis": "asteras tripolis",
    # Denmark
    "fc copenhagen": "copenhagen",
    "fc kobenhavn": "copenhagen",
    "brondby if": "brondby",
    "fc nordsjaelland": "nordsjaelland",
    "randers fc": "randers",
    "ac horsens": "horsens",
    "agf aarhus": "agf",
    "viborg ff": "viborg",
    # Brazil
    "se palmeiras": "palmeiras",
    "gremio fbpa": "gremio",
    "cruzeiro ec": "cruzeiro",
    "ec vitoria": "vitoria",
    "sc corinthians": "corinthians",
    "fluminense fc": "fluminense",
    "cr flamengo": "flamengo",
    "red bull bragantino": "bragantino",
    "athletico paranaense": "athletico-pr",
    "ec bahia": "bahia",
    # South Africa
    "orlando pirates": "orlando pirates",
    "kaizer chiefs": "kaizer chiefs",
}


def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _clean(s: str) -> str:
    s = _strip_accents(s.lower().strip())
    s = re.sub(r"[''`]", "", s)
    s = re.sub(r"[^\w\s-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_team(name: str) -> str:
    cleaned = _clean(name)
    if cleaned in ALIASES:
        return ALIASES[cleaned]
    return cleaned


def slug_to_teams(slug: str) -> tuple[str, str]:
    slug = slug.strip("/").split("/")[-1]
    parts = slug.split("-vs-")
    if len(parts) != 2:
        raise ValueError(f"Invalid slug format (expected '-vs-'): {slug}")
    home = parts[0].replace("-", " ").strip()
    away = parts[1].replace("-", " ").strip()
    home = re.sub(r"\s+\d+$", "", home)
    away = re.sub(r"\s+\d+$", "", away)
    return home, away


def participants_to_normalized(participants: list[str]) -> tuple[str, str]:
    if len(participants) != 2:
        raise ValueError(f"Expected 2 participants, got {len(participants)}")
    return normalize_team(participants[0]), normalize_team(participants[1])

from datetime import datetime
from difflib import get_close_matches
from functools import wraps
import json
import os
import hashlib
import pickle
from pathlib import Path
from urllib.parse import quote_plus
import threading
import time
import unicodedata

import requests
from flask import (
    Flask,
    g,
    has_request_context,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_caching import Cache
from nba_api.stats.static import players, teams as nba_teams
from nba_api.stats.endpoints import (
    commonteamroster,
    leaguedashplayerstats,
    playerawards,
    playercareerstats,
    playerprofilev2,
    teamdashboardbygeneralsplits,
)

app = Flask(__name__)

PLAYER_CACHE_TTL_SECONDS = 12 * 60 * 60
SIMILAR_CACHE_TTL_SECONDS = 12 * 60 * 60
LEADERS_CACHE_TTL_SECONDS = 60 * 60
TEAM_CACHE_TTL_SECONDS = 6 * 60 * 60
TRENDING_CACHE_TTL_SECONDS = 60 * 60
AWARDS_CACHE_TTL_SECONDS = 12 * 60 * 60
STALE_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
CACHE_NOTICE = "Live NBA data is temporarily unavailable. Showing cached data."
NBA_API_TIMEOUT_SECONDS = 15
CAREER_API_TIMEOUT_SECONDS = 15
DATA_PROVIDER = os.environ.get("DATA_PROVIDER", "nba_api").strip().lower()
BALLDONTLIE_API_BASE_URL = "https://api.balldontlie.io/v1"
BALLDONTLIE_API_TIMEOUT_SECONDS = 6
ADVANCED_STATS_UNAVAILABLE_MESSAGE = (
    "Advanced statistics are temporarily unavailable while the data provider "
    "is being upgraded."
)
STAT_SNAPSHOT_PATH = Path(__file__).resolve().parent / "data" / "stat_snapshot.json"

redis_url = os.environ.get("REDIS_URL")

if redis_url:
    app.config.update(
        CACHE_TYPE="RedisCache",
        CACHE_REDIS_URL=redis_url,
        CACHE_DEFAULT_TIMEOUT=PLAYER_CACHE_TTL_SECONDS,
    )
else:
    app.config.update(
        CACHE_TYPE="SimpleCache",
        CACHE_DEFAULT_TIMEOUT=PLAYER_CACHE_TTL_SECONDS,
        CACHE_THRESHOLD=500,
    )

cache = Cache(app)
_cache_locks = {}
_cache_locks_lock = threading.Lock()


def make_cache_key(function, args, kwargs):
    payload = pickle.dumps(
        (function.__module__, function.__name__, args, tuple(sorted(kwargs.items()))),
        protocol=pickle.HIGHEST_PROTOCOL,
    )
    return f"{DATA_PROVIDER}:{function.__name__}:{hashlib.sha256(payload).hexdigest()}"


def using_balldontlie():
    return DATA_PROVIDER == "balldontlie"


def mark_cached_data_notice():
    if has_request_context():
        g.cached_data_notice = CACHE_NOTICE


def get_cached_data_notice():
    if has_request_context():
        return getattr(g, "cached_data_notice", None)
    return None


def get_cached_function_value(function, *args, include_stale=True, **kwargs):
    cache_key = make_cache_key(function, args, kwargs)
    cached_value = cache.get(cache_key)

    if cached_value is not None:
        return cached_value

    if include_stale:
        stale_value = cache.get(f"{cache_key}:stale")
        if stale_value is not None:
            mark_cached_data_notice()
            return stale_value

    return None


def ttl_cache(
    ttl_seconds=PLAYER_CACHE_TTL_SECONDS,
    stale_seconds=STALE_CACHE_TTL_SECONDS,
):
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            cache_key = make_cache_key(function, args, kwargs)
            stale_cache_key = f"{cache_key}:stale"
            cached_value = cache.get(cache_key)

            if cached_value is not None:
                return cached_value

            with _cache_locks_lock:
                key_lock = _cache_locks.setdefault(cache_key, threading.Lock())

            try:
                with key_lock:
                    cached_value = cache.get(cache_key)
                    if cached_value is not None:
                        return cached_value

                    try:
                        value = function(*args, **kwargs)
                    except Exception:
                        stale_value = cache.get(stale_cache_key)
                        if stale_value is not None:
                            app.logger.warning(
                                "Using stale cached data for %s after NBA API failure",
                                function.__name__,
                            )
                            mark_cached_data_notice()
                            return stale_value
                        raise

                    if value is not None:
                        cache.set(cache_key, value, timeout=ttl_seconds)
                        cache.set(stale_cache_key, value, timeout=stale_seconds)

                    return value
            finally:
                with _cache_locks_lock:
                    _cache_locks.pop(cache_key, None)

        wrapper.cache_clear = cache.clear
        return wrapper

    return decorator


team_names = {
    "ATL": "Atlanta Hawks",
    "BOS": "Boston Celtics",
    "BKN": "Brooklyn Nets",
    "CHA": "Charlotte Hornets",
    "CHI": "Chicago Bulls",
    "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks",
    "DEN": "Denver Nuggets",
    "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors",
    "HOU": "Houston Rockets",
    "IND": "Indiana Pacers",
    "LAC": "LA Clippers",
    "LAL": "Los Angeles Lakers",
    "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks",
    "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans",
    "NYK": "New York Knicks",
    "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic",
    "PHI": "Philadelphia 76ers",
    "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers",
    "SAC": "Sacramento Kings",
    "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors",
    "UTA": "Utah Jazz",
    "WAS": "Washington Wizards",
}
team_logos = {
    "ATL": "https://cdn.nba.com/logos/nba/1610612737/primary/L/logo.svg",
    "BOS": "https://cdn.nba.com/logos/nba/1610612738/primary/L/logo.svg",
    "BKN": "https://cdn.nba.com/logos/nba/1610612751/primary/L/logo.svg",
    "CHA": "https://cdn.nba.com/logos/nba/1610612766/primary/L/logo.svg",
    "CHI": "https://cdn.nba.com/logos/nba/1610612741/primary/L/logo.svg",
    "CLE": "https://cdn.nba.com/logos/nba/1610612739/primary/L/logo.svg",
    "DAL": "https://cdn.nba.com/logos/nba/1610612742/primary/L/logo.svg",
    "DEN": "https://cdn.nba.com/logos/nba/1610612743/primary/L/logo.svg",
    "DET": "https://cdn.nba.com/logos/nba/1610612765/primary/L/logo.svg",
    "GSW": "https://cdn.nba.com/logos/nba/1610612744/primary/L/logo.svg",
    "HOU": "https://cdn.nba.com/logos/nba/1610612745/primary/L/logo.svg",
    "IND": "https://cdn.nba.com/logos/nba/1610612754/primary/L/logo.svg",
    "LAC": "https://cdn.nba.com/logos/nba/1610612746/primary/L/logo.svg",
    "LAL": "https://cdn.nba.com/logos/nba/1610612747/primary/L/logo.svg",
    "MEM": "https://cdn.nba.com/logos/nba/1610612763/primary/L/logo.svg",
    "MIA": "https://cdn.nba.com/logos/nba/1610612748/primary/L/logo.svg",
    "MIL": "https://cdn.nba.com/logos/nba/1610612749/primary/L/logo.svg",
    "MIN": "https://cdn.nba.com/logos/nba/1610612750/primary/L/logo.svg",
    "NOP": "https://cdn.nba.com/logos/nba/1610612740/primary/L/logo.svg",
    "NYK": "https://cdn.nba.com/logos/nba/1610612752/primary/L/logo.svg",
    "OKC": "https://cdn.nba.com/logos/nba/1610612760/primary/L/logo.svg",
    "ORL": "https://cdn.nba.com/logos/nba/1610612753/primary/L/logo.svg",
    "PHI": "https://cdn.nba.com/logos/nba/1610612755/primary/L/logo.svg",
    "PHX": "https://cdn.nba.com/logos/nba/1610612756/primary/L/logo.svg",
    "POR": "https://cdn.nba.com/logos/nba/1610612757/primary/L/logo.svg",
    "SAC": "https://cdn.nba.com/logos/nba/1610612758/primary/L/logo.svg",
    "SAS": "https://cdn.nba.com/logos/nba/1610612759/primary/L/logo.svg",
    "TOR": "https://cdn.nba.com/logos/nba/1610612761/primary/L/logo.svg",
    "UTA": "https://cdn.nba.com/logos/nba/1610612762/primary/L/logo.svg",
    "WAS": "https://cdn.nba.com/logos/nba/1610612764/primary/L/logo.svg",
}


COMMON_PREWARM_PLAYERS = [
    "Stephen Curry",
    "LeBron James",
    "Michael Jordan",
    "Kevin Durant",
    "Nikola Jokic",
    "Giannis Antetokounmpo",
]


similar_player_pool = [
    "Stephen Curry",
    "Damian Lillard",
    "Klay Thompson",
    "Trae Young",
    "Luka Doncic",
    "LeBron James",
    "Kevin Durant",
    "Giannis Antetokounmpo",
    "Jayson Tatum",
    "Nikola Jokic",
    "Joel Embiid",
    "Anthony Davis",
    "Victor Wembanyama",
    "Shai Gilgeous-Alexander",
    "Anthony Edwards",
    "Devin Booker",
    "Donovan Mitchell",
    "Ja Morant",
    "Jalen Brunson",
    "Tyrese Haliburton",
    "Paolo Banchero",
    "Zion Williamson",
    "Bam Adebayo",
    "Karl-Anthony Towns",
    "Domantas Sabonis",
    "Jimmy Butler",
    "Paul George",
    "Kawhi Leonard",
    "Jaylen Brown",
    "LaMelo Ball",
]

emergency_search_player_names = sorted(
    set(
        similar_player_pool
        + COMMON_PREWARM_PLAYERS
        + [
            "Michael Jordan",
            "Larry Bird",
            "Magic Johnson",
            "Wilt Chamberlain",
            "Kareem Abdul-Jabbar",
            "Shaquille O'Neal",
            "Kobe Bryant",
            "Tim Duncan",
            "Dirk Nowitzki",
            "Dwyane Wade",
            "Allen Iverson",
            "James Harden",
            "Russell Westbrook",
            "Chris Paul",
            "Seth Curry",
            "Austin Reaves",
            "Rui Hachimura",
            "Jaxson Hayes",
            "Jarred Vanderbilt",
            "Marcus Smart",
            "Deandre Ayton",
            "Cooper Flagg",
        ]
    )
)


class BalldontlieProviderError(RuntimeError):
    pass


def get_balldontlie_headers():
    api_key = os.environ.get("BALLDONTLIE_API_KEY")

    if not api_key:
        raise BalldontlieProviderError("BALLDONTLIE_API_KEY is not configured.")

    return {"Authorization": api_key}


def balldontlie_request(path, params=None):
    try:
        response = requests.get(
            f"{BALLDONTLIE_API_BASE_URL}{path}",
            headers=get_balldontlie_headers(),
            params=params,
            timeout=BALLDONTLIE_API_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.Timeout as error:
        raise BalldontlieProviderError("BALLDONTLIE request timed out.") from error
    except requests.RequestException as error:
        raise BalldontlieProviderError("BALLDONTLIE request failed.") from error

    return response.json()


def balldontlie_player_name(player):
    return f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()


def normalize_balldontlie_player(player):
    team = player.get("team") or {}
    team_abbr = safe_text(team.get("abbreviation"), "NBA")
    full_name = balldontlie_player_name(player)

    return {
        "id": player.get("id"),
        "full_name": full_name,
        "first_name": player.get("first_name"),
        "last_name": player.get("last_name"),
        "team": team,
        "team_abbr": team_abbr,
    }


@ttl_cache(PLAYER_CACHE_TTL_SECONDS)
def get_balldontlie_players(search=None, team_id=None, limit=25):
    params = {"per_page": min(limit, 100)}

    if search:
        params["search"] = search

    if team_id:
        params["team_ids[]"] = team_id

    payload = balldontlie_request("/players", params=params)
    return [
        normalize_balldontlie_player(player)
        for player in payload.get("data", [])
        if balldontlie_player_name(player)
    ]


@ttl_cache(PLAYER_CACHE_TTL_SECONDS)
def get_balldontlie_player_by_id(player_id):
    payload = balldontlie_request(f"/players/{player_id}")
    return normalize_balldontlie_player(payload.get("data", {}))


@ttl_cache(TEAM_CACHE_TTL_SECONDS)
def get_balldontlie_teams():
    payload = balldontlie_request("/teams", params={"per_page": 100})
    return payload.get("data", [])


def get_balldontlie_team_by_abbr(team_abbr):
    for team in get_balldontlie_teams():
        if safe_text(team.get("abbreviation")).upper() == team_abbr.upper():
            return team
    return None


def load_stat_snapshot():
    if not STAT_SNAPSHOT_PATH.exists():
        return {"players": {}, "teams": {}, "trending_players": []}

    try:
        with STAT_SNAPSHOT_PATH.open("r", encoding="utf-8") as snapshot_file:
            snapshot = json.load(snapshot_file)
    except (OSError, json.JSONDecodeError):
        app.logger.warning("Unable to load local stat snapshot")
        return {"players": {}, "teams": {}, "trending_players": []}

    snapshot.setdefault("players", {})
    snapshot.setdefault("teams", {})
    snapshot.setdefault("trending_players", [])
    return snapshot


def get_snapshot_players():
    return load_stat_snapshot().get("players", {})


def get_snapshot_player(player_name):
    normalized_query = normalize_player_name(player_name)
    snapshot_players = get_snapshot_players()

    if normalized_query in snapshot_players:
        return snapshot_players[normalized_query]

    for normalized_name, player in snapshot_players.items():
        if normalized_query and normalized_query in normalized_name:
            return player

    return None


def get_snapshot_team(team_abbr):
    return load_stat_snapshot().get("teams", {}).get(team_abbr.upper(), {})


def get_snapshot_team_for_key(team_key):
    team_key = str(team_key).upper()

    if team_key in team_names:
        return team_key, get_snapshot_team(team_key)

    for abbr, team in load_stat_snapshot().get("teams", {}).items():
        if str(team.get("id")) == str(team_key):
            return abbr, team

    return team_key, {}


def add_player_identity_defaults(player):
    player = player.copy()
    team_abbr = safe_text(player.get("team_abbr") or player.get("team"), "NBA")

    player.setdefault("team_name", team_names.get(team_abbr, team_abbr))
    player.setdefault("team_logo", team_logos.get(team_abbr))
    player.setdefault(
        "image_url",
        (
            "https://ui-avatars.com/api/?background=111827&color=ffffff"
            f"&bold=true&name={quote_plus(player.get('name', 'NBA Player'))}"
        ),
    )
    player.setdefault("advanced_stats_unavailable", False)
    player.setdefault("advanced_stats_message", None)
    player.setdefault("career_table", [])
    player.setdefault("games", 0)
    player.setdefault("ppg", 0)
    player.setdefault("rpg", 0)
    player.setdefault("apg", 0)
    player.setdefault("spg", 0)
    player.setdefault("bpg", 0)
    player.setdefault("fg_pct", 0)
    player.setdefault("fg3_pct", 0)
    player.setdefault("ft_pct", 0)
    player.setdefault("career_points", 0)
    player.setdefault("career_rebounds", 0)
    player.setdefault("career_assists", 0)
    return player


def get_searchable_players(player_name):
    if not using_balldontlie():
        return players.get_players()

    player_name = player_name.strip()
    api_players = []

    if player_name:
        try:
            api_players = get_balldontlie_players(player_name, limit=25)
        except Exception:
            app.logger.warning("BALLDONTLIE player search failed")

    known_players = [
        {"id": f"name:{name}", "full_name": name}
        for name in emergency_search_player_names
    ]
    known_players.extend(
        {
            "id": f"snapshot:{player.get('id', normalized_name)}",
            "full_name": player.get("name", normalized_name),
        }
        for normalized_name, player in get_snapshot_players().items()
    )
    merged = {normalize_player_name(player["full_name"]): player for player in known_players}

    for player in api_players:
        merged[normalize_player_name(player["full_name"])] = player

    return list(merged.values())


def build_balldontlie_profile(player):
    full_name = player["full_name"]
    team_abbr = safe_text(player.get("team_abbr"), "NBA")
    player_id = player.get("id")
    snapshot_player = get_snapshot_player(full_name)

    if snapshot_player:
        profile = add_player_identity_defaults(snapshot_player)
        profile["id"] = profile.get("id") or player_id
        profile["name"] = profile.get("name") or full_name
        profile["team_name"] = profile.get("team_name") or team_names.get(
            team_abbr,
            team_abbr,
        )
        profile["team_logo"] = profile.get("team_logo") or team_logos.get(team_abbr)
        return profile

    return {
        "id": player_id,
        "name": full_name,
        "team_name": team_names.get(team_abbr, team_abbr),
        "team_logo": team_logos.get(team_abbr),
        "season": "Provider Upgrade",
        "games": 0,
        "ppg": 0,
        "rpg": 0,
        "apg": 0,
        "spg": 0,
        "bpg": 0,
        "fg_pct": 0,
        "fg3_pct": 0,
        "ft_pct": 0,
        "career_points": 0,
        "career_rebounds": 0,
        "career_assists": 0,
        "career_table": [],
        "image_url": (
            "https://ui-avatars.com/api/?background=111827&color=ffffff"
            f"&bold=true&name={quote_plus(full_name)}"
        ),
        "advanced_stats_unavailable": True,
        "advanced_stats_message": ADVANCED_STATS_UNAVAILABLE_MESSAGE,
    }


def normalize_player_name(player_name):
    normalized = unicodedata.normalize("NFKD", player_name)
    return (
        "".join(
            character
            for character in normalized
            if not unicodedata.combining(character)
        )
        .casefold()
        .strip()
    )


def find_matching_players(player_name, player_list):
    normalized_query = normalize_player_name(player_name)
    exact_matches = [
        player
        for player in player_list
        if normalize_player_name(player["full_name"]) == normalized_query
    ]

    if exact_matches:
        return exact_matches

    return [
        player
        for player in player_list
        if normalized_query in normalize_player_name(player["full_name"])
    ]


def get_player_suggestions(player_name, player_list, limit=3):
    normalized_players = {
        normalize_player_name(player["full_name"]): player for player in player_list
    }
    closest_names = get_close_matches(
        normalize_player_name(player_name),
        normalized_players.keys(),
        n=limit,
        cutoff=0.6,
    )
    return [normalized_players[name] for name in closest_names]


def safe_float(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    return default if number != number else number


def safe_text(value, default="NBA"):
    if value is None or value != value or not str(value).strip():
        return default
    return str(value)


@ttl_cache(PLAYER_CACHE_TTL_SECONDS)
def get_regular_season_career(player_id):
    required_columns = {
        "SEASON_ID",
        "TEAM_ABBREVIATION",
        "GP",
        "PTS",
        "REB",
        "AST",
    }
    endpoints = [
        (
            "PlayerProfileV2",
            lambda: playerprofilev2.PlayerProfileV2(
                player_id=player_id,
                league_id_nullable="00",
                per_mode36="Totals",
                timeout=NBA_API_TIMEOUT_SECONDS,
            ),
        ),
        (
            "PlayerCareerStats",
            lambda: playercareerstats.PlayerCareerStats(
                player_id=player_id,
                league_id_nullable="00",
                timeout=CAREER_API_TIMEOUT_SECONDS,
            ),
        ),
    ]
    endpoint_errors = []

    for endpoint_name, create_endpoint in endpoints:
        try:
            endpoint = create_endpoint()
            frames = []
            regular_season_data = getattr(
                endpoint,
                "season_totals_regular_season",
                None,
            )

            if regular_season_data is not None:
                frames.append(regular_season_data.get_data_frame())

            frames.extend(endpoint.get_data_frames())

            for frame in frames:
                if not frame.empty and required_columns.issubset(frame.columns):
                    return frame
        except Exception as error:
            endpoint_errors.append(f"{endpoint_name}: {error}")
            app.logger.warning(
                "Unable to load %s for player %s: %s",
                endpoint_name,
                player_id,
                error,
            )
            continue

    if endpoint_errors:
        raise RuntimeError("; ".join(endpoint_errors))

    return None


@ttl_cache(PLAYER_CACHE_TTL_SECONDS)
def get_player_stats(player_name):
    if using_balldontlie():
        player_name = player_name.strip()

        if player_name.startswith("bdl:"):
            player = get_balldontlie_player_by_id(player_name.split(":", 1)[1])
            return build_balldontlie_profile(player) if player else None

        matches = find_matching_players(player_name, get_searchable_players(player_name))

        if not matches:
            return None

        selected_player = matches[0]

        if str(selected_player.get("id", "")).startswith("name:"):
            try:
                api_matches = get_balldontlie_players(selected_player["full_name"], limit=10)
            except Exception:
                api_matches = []
            exact_api_matches = find_matching_players(
                selected_player["full_name"],
                api_matches,
            )
            selected_player = exact_api_matches[0] if exact_api_matches else selected_player

        if str(selected_player.get("id", "")).startswith("name:"):
            return build_balldontlie_profile(selected_player)

        return build_balldontlie_profile(selected_player)

    all_players = players.get_players()

    matching_players = find_matching_players(player_name, all_players)

    if not matching_players:
        return None

    player_info = matching_players[0]
    player_id = player_info["id"]

    df = get_regular_season_career(player_id)

    if df is None or df.empty:
        return None

    df = df[df["GP"].apply(safe_float) > 0]

    if df.empty:
        return None

    career_points = int(sum(safe_float(value) for value in df["PTS"]))
    career_rebounds = int(sum(safe_float(value) for value in df["REB"]))
    career_assists = int(sum(safe_float(value) for value in df["AST"]))

    latest_season = df.iloc[-1]
    games = safe_float(latest_season.get("GP"))
    team_abbr = safe_text(latest_season.get("TEAM_ABBREVIATION"))

    career_table = []

    for _, row in df.iterrows():
        gp = safe_float(row.get("GP"))

        career_table.append(
            {
                "season": safe_text(row.get("SEASON_ID"), "--"),
                "team": safe_text(row.get("TEAM_ABBREVIATION")),
                "games": int(gp),
                "ppg": round(safe_float(row.get("PTS")) / gp, 1),
                "rpg": round(safe_float(row.get("REB")) / gp, 1),
                "apg": round(safe_float(row.get("AST")) / gp, 1),
                "fg_pct": round(safe_float(row.get("FG_PCT")) * 100, 1),
                "fg3_pct": round(safe_float(row.get("FG3_PCT")) * 100, 1),
                "ft_pct": round(safe_float(row.get("FT_PCT")) * 100, 1),
            }
        )

    return {
        "id": player_id,
        "name": player_info["full_name"],
        "team_name": team_names.get(team_abbr, team_abbr),
        "team_logo": team_logos.get(team_abbr),
        "season": safe_text(latest_season.get("SEASON_ID"), "--"),
        "games": int(games),
        "ppg": round(safe_float(latest_season.get("PTS")) / games, 1),
        "rpg": round(safe_float(latest_season.get("REB")) / games, 1),
        "apg": round(safe_float(latest_season.get("AST")) / games, 1),
        "spg": round(safe_float(latest_season.get("STL")) / games, 1),
        "bpg": round(safe_float(latest_season.get("BLK")) / games, 1),
        "fg_pct": round(safe_float(latest_season.get("FG_PCT")) * 100, 1),
        "fg3_pct": round(safe_float(latest_season.get("FG3_PCT")) * 100, 1),
        "ft_pct": round(safe_float(latest_season.get("FT_PCT")) * 100, 1),
        "career_points": career_points,
        "career_rebounds": career_rebounds,
        "career_assists": career_assists,
        "career_table": career_table,
        "image_url": f"https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png",
    }


@ttl_cache(AWARDS_CACHE_TTL_SECONDS)
def get_player_awards(player_id):
    if using_balldontlie():
        return []

    awards_data = playerawards.PlayerAwards(
        player_id=player_id,
        timeout=NBA_API_TIMEOUT_SECONDS,
    ).get_data_frames()[0]

    categories = {
        "championships": {
            "label": "NBA Championships",
            "short_label": "Titles",
            "matches": lambda description: "nba champion" in description,
        },
        "mvps": {
            "label": "Most Valuable Player",
            "short_label": "MVPs",
            "matches": lambda description: description == "nba most valuable player",
        },
        "all_stars": {
            "label": "NBA All-Star",
            "short_label": "All-Star",
            "matches": lambda description: description == "nba all-star",
        },
        "all_nba": {
            "label": "All-NBA Teams",
            "short_label": "All-NBA",
            "matches": lambda description: "all-nba" in description,
        },
    }
    accomplishments = []

    for key, category in categories.items():
        matching_rows = []

        for _, award in awards_data.iterrows():
            description = str(award.get("DESCRIPTION") or "").casefold().strip()
            if category["matches"](description):
                matching_rows.append(award)

        seasons = sorted(
            {
                str(award.get("SEASON"))
                for award in matching_rows
                if award.get("SEASON") is not None
                and str(award.get("SEASON")).lower() != "nan"
            },
            reverse=True,
        )
        accomplishments.append(
            {
                "key": key,
                "label": category["label"],
                "short_label": category["short_label"],
                "count": len(matching_rows),
                "seasons": seasons,
            }
        )

    return accomplishments


def get_similarity_score(player, candidate):
    stat_weights = {
        "ppg": (30, 3.0),
        "rpg": (12, 2.2),
        "apg": (10, 2.2),
        "fg_pct": (20, 1.0),
        "fg3_pct": (20, 1.0),
        "ft_pct": (20, 0.8),
        "career_points": (30000, 0.5),
        "career_rebounds": (12000, 0.4),
        "career_assists": (12000, 0.4),
    }

    score = 0

    for stat, (scale, weight) in stat_weights.items():
        difference = abs(player[stat] - candidate[stat]) / scale
        score += difference * weight

    return score


def get_similarity_tags(player, candidate):
    differences = [
        ("Scoring", abs(player["ppg"] - candidate["ppg"])),
        ("Rebounding", abs(player["rpg"] - candidate["rpg"])),
        ("Playmaking", abs(player["apg"] - candidate["apg"])),
        ("Shooting", abs(player["fg3_pct"] - candidate["fg3_pct"])),
    ]

    return [label for label, _ in sorted(differences, key=lambda item: item[1])[:2]]


@ttl_cache(SIMILAR_CACHE_TTL_SECONDS)
def get_similar_players(player_name, limit=4):
    if using_balldontlie():
        player = get_snapshot_player(player_name)

        if not player:
            return []

        player = add_player_identity_defaults(player)
        matches = []

        for candidate in get_snapshot_players().values():
            candidate = add_player_identity_defaults(candidate)

            if normalize_player_name(candidate["name"]) == normalize_player_name(player["name"]):
                continue

            score = get_similarity_score(player, candidate)
            candidate["similarity_score"] = max(0, round(100 - (score * 12), 0))
            candidate["similarity_tags"] = get_similarity_tags(player, candidate)
            matches.append(candidate)

        return sorted(matches, key=lambda match: match["similarity_score"], reverse=True)[
            :limit
        ]

    player = get_cached_function_value(get_player_stats, player_name)

    if not player:
        player = get_player_stats(player_name)

    if not player:
        return []

    matches = []
    request_failed = False

    for candidate_name in similar_player_pool:
        if candidate_name.lower() == player["name"].lower():
            continue

        try:
            candidate = get_player_stats(candidate_name)
        except Exception:
            request_failed = True
            continue

        if not candidate:
            continue

        score = get_similarity_score(player, candidate)
        candidate = candidate.copy()
        candidate["similarity_score"] = max(0, round(100 - (score * 12), 0))
        candidate["similarity_tags"] = get_similarity_tags(player, candidate)
        matches.append(candidate)

    if not matches and request_failed:
        raise RuntimeError("Unable to load similar player data")

    return sorted(matches, key=lambda match: match["similarity_score"], reverse=True)[
        :limit
    ]


@ttl_cache(LEADERS_CACHE_TTL_SECONDS)
def get_league_leaders(limit=5):
    leader_categories = {
        "ppg": {"title": "Points Per Game", "label": "PPG", "format": "number"},
        "rpg": {"title": "Rebounds Per Game", "label": "RPG", "format": "number"},
        "apg": {"title": "Assists Per Game", "label": "APG", "format": "number"},
        "spg": {"title": "Steals Per Game", "label": "SPG", "format": "number"},
        "bpg": {"title": "Blocks Per Game", "label": "BPG", "format": "number"},
        "fg_pct": {
            "title": "Field Goal Percentage",
            "label": "FG%",
            "format": "percent",
        },
        "fg3_pct": {
            "title": "Three-Point Percentage",
            "label": "3PT%",
            "format": "percent",
        },
        "ft_pct": {
            "title": "Free Throw Percentage",
            "label": "FT%",
            "format": "percent",
        },
    }

    if using_balldontlie():
        player_pool = [
            add_player_identity_defaults(player)
            for player in get_snapshot_players().values()
        ]

        return [
            {
                "key": stat,
                "title": category["title"],
                "label": category["label"],
                "format": category["format"],
                "players": sorted(
                    player_pool,
                    key=lambda player: player.get(stat, 0),
                    reverse=True,
                )[:limit],
            }
            for stat, category in leader_categories.items()
        ]

    player_pool = []

    for player_name in similar_player_pool:
        try:
            player = get_player_stats(player_name)
        except Exception:
            continue

        if player:
            player_pool.append(player)

    leaders = []

    for stat, category in leader_categories.items():
        ranked_players = sorted(
            player_pool, key=lambda player: player.get(stat, 0), reverse=True
        )[:limit]
        leaders.append(
            {
                "key": stat,
                "title": category["title"],
                "label": category["label"],
                "format": category["format"],
                "players": ranked_players,
            }
        )

    return leaders


@ttl_cache(TRENDING_CACHE_TTL_SECONDS)
def get_trending_players(season, limit=6):
    if using_balldontlie():
        snapshot = load_stat_snapshot()
        trending_players = snapshot.get("trending_players") or []

        if not trending_players:
            trending_players = sorted(
                get_snapshot_players().values(),
                key=lambda player: player.get("ppg", 0),
                reverse=True,
            )[:limit]

        return [
            {
                "id": player.get("id"),
                "name": player.get("name"),
                "team": player.get("team_abbr") or player.get("team", "NBA"),
                "ppg": player.get("ppg", 0),
                "rpg": player.get("rpg", 0),
                "apg": player.get("apg", 0),
                "image_url": add_player_identity_defaults(player)["image_url"],
            }
            for player in trending_players[:limit]
        ]

    recent_stats = leaguedashplayerstats.LeagueDashPlayerStats(
        last_n_games=5,
        league_id_nullable="00",
        per_mode_detailed="PerGame",
        season=season,
        season_type_all_star="Regular Season",
        timeout=NBA_API_TIMEOUT_SECONDS,
    ).get_data_frames()[0]

    if recent_stats.empty:
        return []

    recent_stats = recent_stats[recent_stats["GP"] >= 2]
    recent_stats = recent_stats.sort_values(
        by=["PTS", "PLUS_MINUS"],
        ascending=False,
    ).head(limit)

    return [
        {
            "id": int(player["PLAYER_ID"]),
            "name": player["PLAYER_NAME"],
            "team": player["TEAM_ABBREVIATION"],
            "ppg": round(float(player["PTS"]), 1),
            "rpg": round(float(player["REB"]), 1),
            "apg": round(float(player["AST"]), 1),
            "image_url": (
                "https://cdn.nba.com/headshots/nba/latest/260x190/"
                f"{int(player['PLAYER_ID'])}.png"
            ),
        }
        for _, player in recent_stats.iterrows()
    ]


def record_prewarm_result(results, name, callback):
    try:
        value = callback()
        results[name] = {
            "ok": True,
            "items": len(value) if isinstance(value, list) else int(value is not None),
        }
    except Exception as error:
        results[name] = {
            "ok": False,
            "error": f"{type(error).__name__}: {error}",
        }


def prewarm_cache():
    results = {}
    season = get_current_nba_season()

    if using_balldontlie():
        record_prewarm_result(
            results,
            "balldontlie_teams",
            get_balldontlie_teams,
        )
        for player_name in COMMON_PREWARM_PLAYERS:
            record_prewarm_result(
                results,
                f"player_profile:{player_name}",
                lambda player_name=player_name: get_player_stats(player_name),
            )
        return results

    record_prewarm_result(
        results,
        "trending_players",
        lambda: get_trending_players(season),
    )
    record_prewarm_result(results, "league_leaders", get_league_leaders)

    for player_name in COMMON_PREWARM_PLAYERS:
        record_prewarm_result(
            results,
            f"player_profile:{player_name}",
            lambda player_name=player_name: get_player_stats(player_name),
        )
        record_prewarm_result(
            results,
            f"similar_players:{player_name}",
            lambda player_name=player_name: get_similar_players(player_name),
        )

    current_season = get_current_nba_season()
    for team_abbr in team_names:
        nba_team = nba_teams.find_team_by_abbreviation(team_abbr)
        if not nba_team:
            results[f"team_stats:{team_abbr}"] = {
                "ok": False,
                "error": "Team id not found",
            }
            results[f"team_roster:{team_abbr}"] = {
                "ok": False,
                "error": "Team id not found",
            }
            continue

        team_id = nba_team["id"]
        record_prewarm_result(
            results,
            f"team_stats:{team_abbr}",
            lambda team_id=team_id: get_team_stats(team_id, current_season),
        )
        record_prewarm_result(
            results,
            f"team_roster:{team_abbr}",
            lambda team_id=team_id: get_team_roster(team_id, current_season),
        )

    return results


@app.cli.command("prewarm-cache")
def prewarm_cache_command():
    results = prewarm_cache()
    click_output = json.dumps(results, indent=2, sort_keys=True)
    print(click_output)


@app.route("/admin/prewarm-cache", methods=["POST"])
def admin_prewarm_cache():
    expected_token = os.environ.get("CACHE_PREWARM_TOKEN")
    provided_token = request.headers.get("X-Prewarm-Token")

    if not expected_token or provided_token != expected_token:
        return {"error": "Unauthorized"}, 401

    results = prewarm_cache()
    ok_count = sum(1 for result in results.values() if result["ok"])

    return {
        "ok": ok_count == len(results),
        "succeeded": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
    }


@app.route("/health")
def health_check():
    return {"status": "ok"}, 200


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "HEAD":
        return "", 200

    error = None
    search_results = []
    suggested_players = []
    trending_players = []
    trending_error = None

    season = get_current_nba_season()
    trending_players = get_cached_function_value(get_trending_players, season)

    if get_cached_data_notice():
        trending_error = get_cached_data_notice()
    elif not trending_players:
        trending_error = "Recent player trends are temporarily unavailable."

    if request.method == "POST":
        player_name = request.form.get("player_name", "").strip()
        selected_player_id = request.form.get("player_id")

        if selected_player_id:
            if (
                using_balldontlie()
                and not selected_player_id.startswith("name:")
                and not selected_player_id.startswith("snapshot:")
            ):
                selected_id = selected_player_id.split(":", 1)[-1]
                try:
                    selected = get_balldontlie_player_by_id(selected_id)
                except Exception:
                    selected = None
                matching_players = [selected] if selected else []
            else:
                all_players = get_searchable_players(player_name)
                matching_players = [
                    player
                    for player in all_players
                    if str(player["id"]) == selected_player_id
                ]
        else:
            all_players = get_searchable_players(player_name)
            matching_players = find_matching_players(player_name, all_players)

        if len(matching_players) > 1 and not selected_player_id:
            search_results = matching_players[:10]
        elif len(matching_players) == 1:
            return redirect(
                url_for(
                    "player_profile",
                    player_name=matching_players[0]["full_name"],
                )
            )
        elif not selected_player_id:
            suggested_players = get_player_suggestions(player_name, all_players)
            if not suggested_players:
                error = "Player not found. Try another name."
        else:
            error = "Player not found. Try another name."

    return render_template(
        "index.html",
        error=error,
        search_results=search_results,
        suggested_players=suggested_players,
        trending_players=trending_players,
        trending_error=trending_error,
    )


@app.route("/compare", methods=["GET", "POST"])
def compare():
    player1 = None
    player2 = None
    error = None

    if request.method == "POST":
        player1_name = request.form.get("player1", "").strip()
        player2_name = request.form.get("player2", "").strip()

        try:
            player1 = get_player_stats(player1_name)
            player2 = get_player_stats(player2_name)
        except Exception:
            app.logger.exception("Unable to load player comparison")
            error = "Player stats are temporarily unavailable. Please try again."
        else:
            if not player1 or not player2:
                error = "One or both players could not be found."
            elif player1.get("advanced_stats_unavailable") or player2.get(
                "advanced_stats_unavailable"
            ):
                player1 = None
                player2 = None
                error = ADVANCED_STATS_UNAVAILABLE_MESSAGE

    return render_template(
        "compare.html",
        player1=player1,
        player2=player2,
        error=error,
        cached_data_notice=get_cached_data_notice(),
    )


@app.route("/leaders")
def league_leaders():
    error = None

    try:
        leaders = get_league_leaders()
    except Exception:
        app.logger.exception("Unable to load league leaders")
        leaders = []
        error = "League leaders are temporarily unavailable. Please try again."
    else:
        if using_balldontlie() and not any(category["players"] for category in leaders):
            error = ADVANCED_STATS_UNAVAILABLE_MESSAGE

    return render_template(
        "leaders.html",
        leaders=leaders,
        error=error,
        cached_data_notice=get_cached_data_notice(),
    )


def get_current_nba_season():
    today = datetime.now()
    start_year = today.year if today.month >= 10 else today.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


@ttl_cache(TEAM_CACHE_TTL_SECONDS)
def get_team_stats(team_id, season):
    if using_balldontlie():
        _, team = get_snapshot_team_for_key(team_id)
        stats = team.get("stats")
        return stats if stats else None

    dashboard = teamdashboardbygeneralsplits.TeamDashboardByGeneralSplits(
        team_id=team_id,
        season=season,
        per_mode_detailed="PerGame",
        timeout=NBA_API_TIMEOUT_SECONDS,
    )
    overall = dashboard.get_data_frames()[0]

    if overall.empty:
        return None

    stats = overall.iloc[0]

    return {
        "season": season,
        "games": int(stats["GP"]),
        "wins": int(stats["W"]),
        "losses": int(stats["L"]),
        "win_pct": round(float(stats["W_PCT"]) * 100, 1),
        "ppg": round(float(stats["PTS"]), 1),
        "rpg": round(float(stats["REB"]), 1),
        "apg": round(float(stats["AST"]), 1),
        "fg_pct": round(float(stats["FG_PCT"]) * 100, 1),
        "fg3_pct": round(float(stats["FG3_PCT"]) * 100, 1),
        "ft_pct": round(float(stats["FT_PCT"]) * 100, 1),
    }


@ttl_cache(TEAM_CACHE_TTL_SECONDS)
def get_team_roster(team_id, season):
    if using_balldontlie():
        _, team = get_snapshot_team_for_key(team_id)
        if team.get("roster"):
            return team["roster"]

        roster = []

        for player in get_balldontlie_players(team_id=team_id, limit=100):
            roster.append(
                {
                    "id": player["id"],
                    "name": player["full_name"],
                    "number": "--",
                    "position": "--",
                    "height": "--",
                    "weight": "--",
                    "age": "--",
                    "experience": "--",
                    "image_url": (
                        "https://ui-avatars.com/api/?background=111827&color=ffffff"
                        f"&bold=true&name={quote_plus(player['full_name'])}"
                    ),
                }
            )

        return roster

    response = commonteamroster.CommonTeamRoster(
        team_id=team_id,
        season=season,
        league_id_nullable="00",
        timeout=NBA_API_TIMEOUT_SECONDS,
    )
    roster_data = response.get_data_frames()[0]
    roster = []

    def clean_value(value):
        if value is None or value != value or not str(value).strip():
            return "--"
        return str(value)

    for _, player in roster_data.iterrows():
        age = clean_value(player.get("AGE"))
        age = str(int(float(age))) if age != "--" else age

        roster.append(
            {
                "id": int(player["PLAYER_ID"]),
                "name": player["PLAYER"],
                "number": clean_value(player.get("NUM")),
                "position": clean_value(player.get("POSITION")),
                "height": clean_value(player.get("HEIGHT")),
                "weight": clean_value(player.get("WEIGHT")),
                "age": age,
                "experience": clean_value(player.get("EXP")),
                "image_url": (
                    "https://cdn.nba.com/headshots/nba/latest/260x190/"
                    f"{int(player['PLAYER_ID'])}.png"
                ),
            }
        )

    return roster


@app.route("/favorites")
def favorites():
    return render_template("favorites.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/teams")
def teams():
    team_list = [
        {
            "abbr": abbr,
            "name": name,
            "logo": team_logos.get(abbr),
        }
        for abbr, name in team_names.items()
    ]

    return render_template("teams.html", teams=team_list)


@app.route("/team/<team_abbr>")
def team_profile(team_abbr):
    team_abbr = team_abbr.upper()

    if team_abbr not in team_names:
        return render_template("team.html", team=None, error="Team not found.")

    if using_balldontlie():
        try:
            provider_team = get_balldontlie_team_by_abbr(team_abbr)
        except Exception:
            provider_team = None
        team_id = provider_team.get("id") if provider_team else None
    else:
        nba_team = nba_teams.find_team_by_abbreviation(team_abbr)
        team_id = nba_team["id"] if nba_team else None

    team = {
        "id": team_id,
        "abbr": team_abbr,
        "name": team_names[team_abbr],
        "logo": team_logos.get(team_abbr),
    }
    stats = None
    stats_error = None
    roster = []
    roster_error = None

    season = get_current_nba_season()

    if team["id"]:
        if using_balldontlie():
            try:
                stats = get_team_stats(team_abbr, season)
            except Exception:
                stats = None

            if not stats:
                stats_error = ADVANCED_STATS_UNAVAILABLE_MESSAGE
        else:
            try:
                stats = get_team_stats(team["id"], season)
            except Exception:
                stats_error = "Team statistics are temporarily unavailable."

        try:
            roster = get_team_roster(team["id"], season)
        except Exception:
            roster_error = "Team roster is temporarily unavailable."
    else:
        stats_error = "Team statistics are temporarily unavailable."
        roster_error = "Team roster is temporarily unavailable."

    return render_template(
        "team.html",
        team=team,
        stats=stats,
        stats_error=stats_error,
        roster=roster,
        roster_error=roster_error,
        cached_data_notice=get_cached_data_notice(),
        error=None,
    )


@app.route("/player/<player_name>")
def player_profile(player_name):
    try:
        player = get_player_stats(player_name)
    except Exception:
        app.logger.exception("Unable to load stats for player %s", player_name)
        return render_template(
            "player.html",
            player=None,
            cached_data_notice=None,
            error=(
                "Player stats are temporarily unavailable. "
                "Please try again in a moment."
            ),
        )

    if not player:
        return (
            render_template(
                "player.html",
                player=None,
                cached_data_notice=None,
                error="Player not found.",
            ),
            404,
        )

    awards = []
    awards_error = None

    if player.get("advanced_stats_unavailable"):
        awards_error = ADVANCED_STATS_UNAVAILABLE_MESSAGE
    elif get_cached_data_notice():
        awards_error = "Player accomplishments are temporarily unavailable."
    else:
        try:
            awards = get_player_awards(player["id"])
        except Exception:
            app.logger.exception("Unable to load awards for player %s", player["id"])
            awards_error = "Player accomplishments are temporarily unavailable."

    similar_error = None

    if player.get("advanced_stats_unavailable"):
        similar_players = []
        similar_error = ADVANCED_STATS_UNAVAILABLE_MESSAGE
    else:
        try:
            similar_players = get_similar_players(player["name"])
        except Exception:
            app.logger.exception("Unable to load similar players for %s", player["id"])
            similar_players = []
            similar_error = "Similar players are temporarily unavailable."

    return render_template(
        "player.html",
        player=player,
        awards=awards,
        awards_error=awards_error,
        similar_players=similar_players,
        similar_error=similar_error,
        cached_data_notice=get_cached_data_notice(),
        error=None,
    )


@app.errorhandler(404)
def page_not_found(error):
    return (
        render_template(
            "error.html",
            title="Page Not Found",
            message="The page you are looking for does not exist.",
        ),
        404,
    )


@app.errorhandler(500)
def server_error(error):
    return (
        render_template(
            "error.html",
            title="Something Went Wrong",
            message="NBA data may be temporarily unavailable. Please try again later.",
        ),
        500,
    )


if __name__ == "__main__":
    app.run(debug=True)

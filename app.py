from datetime import datetime
from difflib import get_close_matches
from functools import wraps
import threading
import time
import unicodedata

from flask import Flask, redirect, render_template, request, url_for
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

CACHE_TTL_SECONDS = 15 * 60
NBA_API_TIMEOUT_SECONDS = 5
CAREER_API_TIMEOUT_SECONDS = 10


def ttl_cache(ttl_seconds=CACHE_TTL_SECONDS):
    def decorator(function):
        cache = {}
        key_locks = {}
        cache_lock = threading.Lock()

        @wraps(function)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.monotonic()
            stale_value = None

            with cache_lock:
                cached = cache.get(key)
                if cached and cached["expires_at"] > now:
                    return cached["value"]
                if cached:
                    stale_value = cached["value"]
                key_lock = key_locks.setdefault(key, threading.Lock())

            try:
                with key_lock:
                    now = time.monotonic()

                    with cache_lock:
                        cached = cache.get(key)
                        if cached and cached["expires_at"] > now:
                            return cached["value"]

                    try:
                        value = function(*args, **kwargs)
                    except Exception:
                        if stale_value is not None:
                            app.logger.warning(
                                "Using stale cached data for %s after NBA API failure",
                                function.__name__,
                            )
                            return stale_value
                        raise

                    if value is not None:
                        with cache_lock:
                            expired_keys = [
                                cached_key
                                for cached_key, entry in cache.items()
                                if entry["expires_at"] <= now
                            ]
                            for expired_key in expired_keys:
                                cache.pop(expired_key, None)

                            cache[key] = {
                                "expires_at": now + ttl_seconds,
                                "value": value,
                            }

                    return value
            finally:
                with cache_lock:
                    key_locks.pop(key, None)

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
        normalize_player_name(player["full_name"]): player
        for player in player_list
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


@ttl_cache()
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
        lambda: playercareerstats.PlayerCareerStats(
            player_id=player_id,
            league_id_nullable="00",
            timeout=CAREER_API_TIMEOUT_SECONDS,
        ),
        lambda: playerprofilev2.PlayerProfileV2(
            player_id=player_id,
            league_id_nullable="00",
            per_mode36="Totals",
            timeout=NBA_API_TIMEOUT_SECONDS,
        ),
    ]
    for endpoint_index, create_endpoint in enumerate(endpoints):
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
        except Exception:
            if endpoint_index == 0:
                raise
            continue

    return None


@ttl_cache()
def get_player_stats(player_name):
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


@ttl_cache()
def get_player_awards(player_id):
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
            "matches": lambda description: description
            == "nba most valuable player",
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


@ttl_cache()
def get_similar_players(player_name, limit=4):
    player = get_player_stats(player_name)

    if not player:
        return []

    matches = []
    request_failed = False
    deadline = time.monotonic() + 8

    for candidate_name in similar_player_pool:
        if time.monotonic() >= deadline:
            request_failed = True
            break
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


@ttl_cache()
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


@ttl_cache()
def get_trending_players(season, limit=6):
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


@app.route("/", methods=["GET", "POST"])
def home():
    error = None
    search_results = []
    suggested_players = []
    trending_players = []
    trending_error = None

    try:
        trending_players = get_trending_players(get_current_nba_season())
        if not trending_players:
            trending_error = "No recent player trends are available."
    except Exception:
        trending_error = "Recent player trends are temporarily unavailable."

    if request.method == "POST":
        player_name = request.form.get("player_name", "").strip()
        selected_player_id = request.form.get("player_id")
        all_players = players.get_players()

        if selected_player_id:
            matching_players = [
                player
                for player in all_players
                if str(player["id"]) == selected_player_id
            ]
        else:
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

    return render_template(
        "compare.html", player1=player1, player2=player2, error=error
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

    return render_template("leaders.html", leaders=leaders, error=error)


def get_current_nba_season():
    today = datetime.now()
    start_year = today.year if today.month >= 10 else today.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


@ttl_cache()
def get_team_stats(team_id, season):
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


@ttl_cache()
def get_team_roster(team_id, season):
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

    nba_team = nba_teams.find_team_by_abbreviation(team_abbr)
    team = {
        "id": nba_team["id"] if nba_team else None,
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
            error="Player stats are temporarily unavailable. Please try again.",
        )

    if not player:
        return (
            render_template("player.html", player=None, error="Player not found."),
            404,
        )

    awards = []
    awards_error = None

    try:
        awards = get_player_awards(player["id"])
    except Exception:
        app.logger.exception("Unable to load awards for player %s", player["id"])
        awards_error = "Player accomplishments are temporarily unavailable."

    similar_error = None

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

from flask import Flask, render_template, request
from nba_api.stats.static import players
from nba_api.stats.endpoints import playercareerstats

app = Flask(__name__)

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


def get_player_stats(player_name):
    all_players = players.get_players()

    matching_players = [
        player
        for player in all_players
        if player_name.lower() in player["full_name"].lower()
    ]

    if not matching_players:
        return None

    player_info = matching_players[0]
    player_id = player_info["id"]

    career = playercareerstats.PlayerCareerStats(player_id=player_id)
    df = career.get_data_frames()[0]

    if df.empty:
        return None

    df = df[df["GP"] > 0]
    career_points = int(df["PTS"].sum())
    career_rebounds = int(df["REB"].sum())
    career_assists = int(df["AST"].sum())

    if df.empty:
        return None

    latest_season = df.iloc[-1]
    games = latest_season["GP"]
    team_abbr = latest_season["TEAM_ABBREVIATION"]

    career_table = []

    for _, row in df.iterrows():
        gp = row["GP"]

        career_table.append(
            {
                "season": row["SEASON_ID"],
                "team": row["TEAM_ABBREVIATION"],
                "games": gp,
                "ppg": round(row["PTS"] / gp, 1),
                "rpg": round(row["REB"] / gp, 1),
                "apg": round(row["AST"] / gp, 1),
            }
        )

    return {
        "name": player_info["full_name"],
        "team_name": team_names.get(team_abbr, team_abbr),
        "team_logo": team_logos.get(team_abbr),
        "season": latest_season["SEASON_ID"],
        "games": games,
        "ppg": round(latest_season["PTS"] / games, 1),
        "rpg": round(latest_season["REB"] / games, 1),
        "apg": round(latest_season["AST"] / games, 1),
        "fg_pct": round(latest_season["FG_PCT"] * 100, 1),
        "fg3_pct": round(latest_season["FG3_PCT"] * 100, 1),
        "ft_pct": round(latest_season["FT_PCT"] * 100, 1),
        "career_points": career_points,
        "career_rebounds": career_rebounds,
        "career_assists": career_assists,
        "career_table": career_table,
        "image_url": f"https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png",
    }


@app.route("/", methods=["GET", "POST"])
def home():
    player_info = None
    stats = None
    error = None
    search_results = []
    career_table = []

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
            matching_players = [
                player
                for player in all_players
                if player_name.lower() in player["full_name"].lower()
            ]

        if len(matching_players) > 1 and not selected_player_id:
            search_results = matching_players[:10]

        elif len(matching_players) == 1:
            player_info = matching_players[0]
            player_id = player_info["id"]

            career = playercareerstats.PlayerCareerStats(player_id=player_id)
            df = career.get_data_frames()[0]

            if not df.empty:
                df = df[df["GP"] > 0]
                career_points = int(df["PTS"].sum())
                career_rebounds = int(df["REB"].sum())
                career_assists = int(df["AST"].sum())

                if not df.empty:
                    latest_season = df.iloc[-1]
                    games = latest_season["GP"]
                    team_abbr = latest_season["TEAM_ABBREVIATION"]

                    stats = {
                        "season": latest_season["SEASON_ID"],
                        "team_name": team_names.get(team_abbr, team_abbr),
                        "team_logo": team_logos.get(team_abbr),
                        "games": games,
                        "ppg": round(latest_season["PTS"] / games, 1),
                        "rpg": round(latest_season["REB"] / games, 1),
                        "apg": round(latest_season["AST"] / games, 1),
                        "fg_pct": round(latest_season["FG_PCT"] * 100, 1),
                        "fg3_pct": round(latest_season["FG3_PCT"] * 100, 1),
                        "ft_pct": round(latest_season["FT_PCT"] * 100, 1),
                        "image_url": f"https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png",
                        "career_points": career_points,
                        "career_rebounds": career_rebounds,
                        "career_assists": career_assists,
                    }
                    for _, row in df.iterrows():
                        gp = row["GP"]

                        career_table.append(
                            {
                                "season": row["SEASON_ID"],
                                "team": row["TEAM_ABBREVIATION"],
                                "games": gp,
                                "ppg": round(row["PTS"] / gp, 1),
                                "rpg": round(row["REB"] / gp, 1),
                                "apg": round(row["AST"] / gp, 1),
                            }
                        )
                else:
                    error = "Stats not available for this player."
            else:
                error = "Stats not available for this player."
        else:
            error = "Player not found. Try another name."

    return render_template(
        "index.html",
        player=player_info,
        stats=stats,
        error=error,
        search_results=search_results,
        career_table=career_table,
    )


@app.route("/compare", methods=["GET", "POST"])
def compare():
    player1 = None
    player2 = None
    error = None

    if request.method == "POST":
        player1_name = request.form.get("player1", "").strip()
        player2_name = request.form.get("player2", "").strip()

        player1 = get_player_stats(player1_name)
        player2 = get_player_stats(player2_name)

        if not player1 or not player2:
            error = "One or both players could not be found."

    return render_template(
        "compare.html", player1=player1, player2=player2, error=error
    )


@app.route("/player/<player_name>")
def player_profile(player_name):
    player = get_player_stats(player_name)

    if not player:
        return render_template("player.html", player=None, error="Player not found.")

    return render_template("player.html", player=player, error=None)


if __name__ == "__main__":
    app.run(debug=True)

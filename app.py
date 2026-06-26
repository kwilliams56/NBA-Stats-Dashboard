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

                if not df.empty:
                    latest_season = df.iloc[-1]
                    games = latest_season["GP"]
                    team_abbr = latest_season["TEAM_ABBREVIATION"]

                    stats = {
                        "season": latest_season["SEASON_ID"],
                        "team_name": team_names.get(team_abbr, team_abbr),
                        "games": games,
                        "ppg": round(latest_season["PTS"] / games, 1),
                        "rpg": round(latest_season["REB"] / games, 1),
                        "apg": round(latest_season["AST"] / games, 1),
                        "image_url": f"https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png",
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


@app.route("/compare")
def compare():
    return render_template("compare.html")


if __name__ == "__main__":
    app.run(debug=True)

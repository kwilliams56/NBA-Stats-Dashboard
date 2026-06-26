from flask import Flask, render_template, request
from nba_api.stats.static import players
from nba_api.stats.endpoints import playercareerstats

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def home():
    player_info = None
    stats = None
    error = None

    if request.method == "POST":
        player_name = request.form.get("player_name")
        matching_players = players.find_players_by_full_name(player_name)

        if matching_players:
            player_info = matching_players[0]
            player_id = player_info["id"]

            career = playercareerstats.PlayerCareerStats(player_id=player_id)
            df = career.get_data_frames()[0]

            if not df.empty:
                latest_season = df.iloc[-1]
                games = latest_season["GP"]

                stats = {
                    "season": latest_season["SEASON_ID"],
                    "team": latest_season["TEAM_ABBREVIATION"],
                    "games": games,
                    "ppg": round(latest_season["PTS"] / games, 1),
                    "rpg": round(latest_season["REB"] / games, 1),
                    "apg": round(latest_season["AST"] / games, 1),
                }
        else:
            error = "Player not found. Try another name."

    return render_template("index.html", player=player_info, stats=stats, error=error)

if __name__ == "__main__":
    app.run(debug=True)
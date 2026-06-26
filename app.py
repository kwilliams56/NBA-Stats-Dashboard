from flask import Flask, render_template, request
from nba_api.stats.static import players

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def home():
    player_info = None
    error = None

    if request.method == "POST":
        player_name = request.form.get("player_name")

        matching_players = players.find_players_by_full_name(player_name)

        if matching_players:
            player_info = matching_players[0]
        else:
            error = "Player not found. Try another name."

    return render_template("index.html", player=player_info, error=error)

if __name__ == "__main__":
    app.run(debug=True)
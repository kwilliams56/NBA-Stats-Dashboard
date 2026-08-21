"""Build a local stat snapshot from nba_api for production fallback data.

Run this from a machine that can reach stats.nba.com, then commit the generated
data/stat_snapshot.json file so Render can serve real stats without calling
stats.nba.com during page requests.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path


DEFAULT_EXTRA_PLAYERS = [
    "AJ Green",
    "Aaron Gordon",
    "Al Horford",
    "Amen Thompson",
    "Andrew Nembhard",
    "Andrew Wiggins",
    "Anfernee Simons",
    "Anthony Black",
    "Austin Reaves",
    "Bennedict Mathurin",
    "Bilal Coulibaly",
    "Bogdan Bogdanovic",
    "Bradley Beal",
    "Brandon Ingram",
    "Brandin Podziemski",
    "Brook Lopez",
    "Cade Cunningham",
    "Cameron Johnson",
    "Chet Holmgren",
    "CJ McCollum",
    "Clint Capela",
    "Coby White",
    "Collin Sexton",
    "Cooper Flagg",
    "Darius Garland",
    "Deandre Ayton",
    "Dejounte Murray",
    "Dennis Schroder",
    "Derrick White",
    "Desmond Bane",
    "Devin Vassell",
    "Donte DiVincenzo",
    "Draymond Green",
    "Duncan Robinson",
    "Dylan Harper",
    "Evan Mobley",
    "Fred VanVleet",
    "Franz Wagner",
    "Herbert Jones",
    "Immanuel Quickley",
    "Isaiah Hartenstein",
    "Ivica Zubac",
    "Jabari Smith Jr.",
    "Jaden Ivey",
    "Jaden McDaniels",
    "Jalen Duren",
    "Jalen Green",
    "Jalen Johnson",
    "Jalen Suggs",
    "Jamal Murray",
    "Jarrett Allen",
    "Jaxson Hayes",
    "Jerami Grant",
    "Jeremy Sochan",
    "Jrue Holiday",
    "Julius Randle",
    "Keegan Murray",
    "Kentavious Caldwell-Pope",
    "Khris Middleton",
    "Kristaps Porzingis",
    "Kyle Kuzma",
    "Lauri Markkanen",
    "Lonzo Ball",
    "Malik Monk",
    "Marcus Smart",
    "Mark Williams",
    "Mikal Bridges",
    "Miles Bridges",
    "Myles Turner",
    "Naz Reid",
    "Norman Powell",
    "OG Anunoby",
    "Pascal Siakam",
    "Payton Pritchard",
    "RJ Barrett",
    "Reed Sheppard",
    "Rui Hachimura",
    "Scoot Henderson",
    "Scottie Barnes",
    "Tobias Harris",
    "Tyler Herro",
    "Tyrese Maxey",
    "Walker Kessler",
    "Zach LaVine",
    "Zaccharie Risacher",
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
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Seed data/stat_snapshot.json with locally fetched NBA stats."
    )
    parser.add_argument(
        "--players",
        nargs="*",
        help="Optional player names to seed instead of the default player list.",
    )
    parser.add_argument(
        "--active-players",
        action="store_true",
        help="Seed every active player from nba_api's local player directory.",
    )
    parser.add_argument(
        "--all-players",
        action="store_true",
        help="Seed every player from nba_api's local player directory.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit how many player names are seeded after the list is built.",
    )
    parser.add_argument(
        "--skip-teams",
        action="store_true",
        help="Skip team stats and roster fetching.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and summarize data without writing the snapshot file.",
    )
    return parser.parse_args()


def load_dashboard():
    os.environ["DATA_PROVIDER"] = "nba_api"

    import app as dashboard

    return dashboard


def snapshot_player(dashboard, player_name):
    player = dashboard.get_player_stats(player_name)

    if not player:
        return None

    normalized_name = dashboard.normalize_player_name(player["name"])
    return normalized_name, player


def snapshot_team(dashboard, team_abbr):
    season = dashboard.get_current_nba_season()
    nba_team = dashboard.nba_teams.find_team_by_abbreviation(team_abbr)

    if not nba_team:
        return None

    team_id = nba_team["id"]
    stats = dashboard.get_team_stats(team_id, season)
    roster = dashboard.get_team_roster(team_id, season)

    return {
        "id": team_id,
        "abbr": team_abbr,
        "name": dashboard.team_names[team_abbr],
        "stats": stats,
        "roster": roster,
    }


def build_trending_players(players, limit=6):
    return sorted(
        players.values(),
        key=lambda player: player.get("ppg", 0),
        reverse=True,
    )[:limit]


def build_player_name_list(dashboard, args):
    if args.players:
        player_names = args.players
    elif args.all_players:
        player_names = [player["full_name"] for player in dashboard.players.get_players()]
    elif args.active_players:
        player_names = [
            player["full_name"] for player in dashboard.players.get_active_players()
        ]
    else:
        player_names = (
            dashboard.COMMON_PREWARM_PLAYERS
            + dashboard.similar_player_pool
            + DEFAULT_EXTRA_PLAYERS
        )

    unique_names = sorted(set(player_names))

    if args.limit:
        return unique_names[: args.limit]

    return unique_names


def print_result(label, ok, detail):
    status = "OK" if ok else "FAIL"
    print(f"{status} {label} - {detail}")


def main():
    args = parse_args()
    dashboard = load_dashboard()
    player_names = build_player_name_list(dashboard, args)
    players = {}
    teams = {}

    for player_name in player_names:
        try:
            result = snapshot_player(dashboard, player_name)
        except Exception as error:
            print_result(player_name, False, f"{type(error).__name__}: {error}")
            continue

        if not result:
            print_result(player_name, False, "not found")
            continue

        normalized_name, player = result
        players[normalized_name] = player
        print_result(player["name"], True, "player stats")

    if not args.skip_teams:
        for team_abbr in dashboard.team_names:
            try:
                team = snapshot_team(dashboard, team_abbr)
            except Exception as error:
                print_result(f"team:{team_abbr}", False, f"{type(error).__name__}: {error}")
                continue

            if not team:
                print_result(f"team:{team_abbr}", False, "not found")
                continue

            teams[team_abbr] = team
            print_result(f"team:{team_abbr}", True, "team stats and roster")

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "local nba_api snapshot",
        "players": players,
        "teams": teams,
        "trending_players": build_trending_players(players),
    }

    output_path = Path(__file__).resolve().parent / "data" / "stat_snapshot.json"

    print("")
    print(f"Players seeded: {len(players)}")
    print(f"Teams seeded: {len(teams)}")

    if args.dry_run:
        print("Dry run complete. No file written.")
        return 0

    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

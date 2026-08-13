"""Seed Render Redis cache with NBA API data from a local machine.

This script is intentionally local-first: it uses REDIS_EXTERNAL_URL so the
public/external Render Key Value URL never needs to be configured in the web app.
"""

import argparse
import os
import sys


def parse_args():
    parser = argparse.ArgumentParser(
        description="Seed Render Redis cache with locally fetched NBA API data."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data and report results without writing to Redis.",
    )
    return parser.parse_args()


def load_app_cache(external_url, dry_run):
    if dry_run:
        os.environ.pop("REDIS_URL", None)
    else:
        os.environ["REDIS_URL"] = external_url

    import app as dashboard

    return dashboard


def cache_keys(dashboard, function, args, kwargs):
    cache_key = dashboard.make_cache_key(function, args, kwargs)
    return cache_key, f"{cache_key}:stale"


def write_cache_value(dashboard, function, args, kwargs, value, ttl_seconds, dry_run):
    if dry_run or value is None:
        return

    cache_key, stale_cache_key = cache_keys(dashboard, function, args, kwargs)
    dashboard.cache.set(cache_key, value, timeout=ttl_seconds)
    dashboard.cache.set(
        stale_cache_key,
        value,
        timeout=dashboard.STALE_CACHE_TTL_SECONDS,
    )


def item_count(value):
    if value is None:
        return 0
    if isinstance(value, list):
        return len(value)
    if hasattr(value, "empty"):
        return 0 if value.empty else len(value)
    return 1


def record_result(results, name, callback):
    try:
        value = callback()
        results.append(
            {
                "name": name,
                "ok": True,
                "items": item_count(value),
            }
        )
    except Exception as error:
        results.append(
            {
                "name": name,
                "ok": False,
                "error": f"{type(error).__name__}: {error}",
            }
        )


def seed_function(
    dashboard,
    results,
    name,
    function,
    args,
    kwargs,
    ttl_seconds,
    dry_run,
):
    def fetch_and_write():
        fetch_function = getattr(function, "__wrapped__", function)
        value = fetch_function(*args, **kwargs)
        write_cache_value(
            dashboard,
            function,
            args,
            kwargs,
            value,
            ttl_seconds,
            dry_run,
        )
        return value

    record_result(results, name, fetch_and_write)


def seed_player(dashboard, results, player_name, dry_run):
    all_players = dashboard.players.get_players()
    matches = dashboard.find_matching_players(player_name, all_players)

    if not matches:
        results.append(
            {
                "name": f"player_lookup:{player_name}",
                "ok": False,
                "error": "Player not found",
            }
        )
        return

    player_id = matches[0]["id"]

    seed_function(
        dashboard,
        results,
        f"career:{player_name}",
        dashboard.get_regular_season_career,
        (player_id,),
        {},
        dashboard.PLAYER_CACHE_TTL_SECONDS,
        dry_run,
    )
    seed_function(
        dashboard,
        results,
        f"player_profile:{player_name}",
        dashboard.get_player_stats,
        (player_name,),
        {},
        dashboard.PLAYER_CACHE_TTL_SECONDS,
        dry_run,
    )
    seed_function(
        dashboard,
        results,
        f"awards:{player_name}",
        dashboard.get_player_awards,
        (player_id,),
        {},
        dashboard.AWARDS_CACHE_TTL_SECONDS,
        dry_run,
    )
    seed_function(
        dashboard,
        results,
        f"similar_players:{player_name}",
        dashboard.get_similar_players,
        (player_name,),
        {},
        dashboard.SIMILAR_CACHE_TTL_SECONDS,
        dry_run,
    )


def seed_teams(dashboard, results, dry_run):
    season = dashboard.get_current_nba_season()

    for team_abbr in dashboard.team_names:
        nba_team = dashboard.nba_teams.find_team_by_abbreviation(team_abbr)
        if not nba_team:
            results.append(
                {
                    "name": f"team:{team_abbr}",
                    "ok": False,
                    "error": "Team id not found",
                }
            )
            continue

        team_id = nba_team["id"]
        seed_function(
            dashboard,
            results,
            f"team_stats:{team_abbr}",
            dashboard.get_team_stats,
            (team_id, season),
            {},
            dashboard.TEAM_CACHE_TTL_SECONDS,
            dry_run,
        )
        seed_function(
            dashboard,
            results,
            f"team_roster:{team_abbr}",
            dashboard.get_team_roster,
            (team_id, season),
            {},
            dashboard.TEAM_CACHE_TTL_SECONDS,
            dry_run,
        )


def print_summary(results, dry_run):
    succeeded = sum(1 for result in results if result["ok"])
    failed = len(results) - succeeded
    mode = "DRY RUN" if dry_run else "WRITE"

    print(f"Mode: {mode}")
    print(f"Succeeded: {succeeded}")
    print(f"Failed: {failed}")
    print("")

    for result in results:
        if result["ok"]:
            print(f"OK   {result['name']} ({result['items']} items)")
        else:
            print(f"FAIL {result['name']} - {result['error']}")


def main():
    args = parse_args()
    external_url = os.environ.get("REDIS_EXTERNAL_URL")

    if not external_url:
        print("REDIS_EXTERNAL_URL is required.", file=sys.stderr)
        return 1

    dashboard = load_app_cache(external_url, args.dry_run)
    results = []
    season = dashboard.get_current_nba_season()

    for player_name in dashboard.COMMON_PREWARM_PLAYERS:
        seed_player(dashboard, results, player_name, args.dry_run)

    seed_function(
        dashboard,
        results,
        "trending_players",
        dashboard.get_trending_players,
        (season,),
        {},
        dashboard.TRENDING_CACHE_TTL_SECONDS,
        args.dry_run,
    )
    seed_function(
        dashboard,
        results,
        "league_leaders",
        dashboard.get_league_leaders,
        (),
        {},
        dashboard.LEADERS_CACHE_TTL_SECONDS,
        args.dry_run,
    )
    seed_teams(dashboard, results, args.dry_run)
    print_summary(results, args.dry_run)

    return 0 if all(result["ok"] for result in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())

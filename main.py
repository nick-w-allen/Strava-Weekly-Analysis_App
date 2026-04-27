import argparse
import sys
from auth import run_oauth_flow, get_valid_token
from db import get_connection, init_db
from sync import sync_to_db


def main():
    parser = argparse.ArgumentParser(description="Strava data pipeline")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--auth", action="store_true", help="Run OAuth flow and save tokens")
    group.add_argument("--full", action="store_true", help="Full history sync (all activities)")
    group.add_argument("--sync", action="store_true", help="Incremental sync (new activities only, default)")
    args = parser.parse_args()

    if args.auth:
        run_oauth_flow()
        return

    try:
        access_token = get_valid_token()
    except FileNotFoundError:
        print("No tokens found. Run: python main.py --auth")
        sys.exit(1)

    conn = get_connection()
    init_db(conn)
    sync_to_db(conn, access_token, full=args.full)
    conn.close()


if __name__ == "__main__":
    main()

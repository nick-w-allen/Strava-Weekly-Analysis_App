import time
import requests
from db import upsert_activity, get_latest_timestamp

API_BASE = "https://www.strava.com/api/v3"
PAGE_SIZE = 200


def fetch_all_activities(access_token, after=None):
    headers = {"Authorization": f"Bearer {access_token}"}
    activities = []
    page = 1

    while True:
        params = {"per_page": PAGE_SIZE, "page": page}
        if after:
            params["after"] = after

        resp = requests.get(f"{API_BASE}/athlete/activities", headers=headers, params=params)

        if resp.status_code == 429:
            print("Rate limit hit — waiting 60s...")
            time.sleep(60)
            resp = requests.get(f"{API_BASE}/athlete/activities", headers=headers, params=params)

        resp.raise_for_status()
        batch = resp.json()

        if not batch:
            break

        activities.extend(batch)
        print(f"  Fetched page {page} ({len(batch)} activities)")
        page += 1

    return activities


def sync_to_db(conn, access_token, full=False):
    after = None if full else get_latest_timestamp(conn)

    if after:
        print(f"Incremental sync — fetching activities after timestamp {after}")
    else:
        print("Full sync — fetching all activities")

    activities = fetch_all_activities(access_token, after=after)

    if not activities:
        print("No new activities found.")
        return 0

    for activity in activities:
        upsert_activity(conn, activity)

    dates = [a["start_date"][:10] for a in activities]
    print(f"\nSynced {len(activities)} activities ({min(dates)} → {max(dates)})")
    return len(activities)

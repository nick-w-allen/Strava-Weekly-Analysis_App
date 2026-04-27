import sqlite3
import csv
import argparse
from datetime import datetime, timedelta, timezone
from db import get_connection

MARATHON_PB_DATE = "2022-01-23"
PB_BUILD_WEEKS = 20


def pace_str(avg_speed_ms):
    if not avg_speed_ms or avg_speed_ms == 0:
        return "--:--"
    sec_per_km = 1000 / avg_speed_ms
    m, s = divmod(int(sec_per_km), 60)
    return f"{m}:{s:02d}"


def hms(seconds):
    if not seconds:
        return "0:00:00"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def fetch_weekly_runs(conn, start_date, end_date):
    rows = conn.execute("""
        SELECT
            strftime('%Y-%W', start_date) AS week,
            MIN(date(start_date))          AS week_start,
            COUNT(*)                       AS runs,
            SUM(distance)                  AS total_distance,
            SUM(moving_time)               AS total_moving_time,
            MAX(distance)                  AS long_run,
            SUM(total_elevation_gain)      AS total_elevation,
            AVG(CASE WHEN average_heartrate > 0 THEN average_heartrate END) AS avg_hr,
            AVG(average_speed)             AS avg_speed,
            SUM(COALESCE(CAST(json_extract(raw_json, '$.suffer_score') AS INTEGER), 0)) AS suffer_score
        FROM activities
        WHERE type IN ('Run', 'VirtualRun')
          AND date(start_date) >= ?
          AND date(start_date) <= ?
        GROUP BY week
        ORDER BY week
    """, (start_date, end_date)).fetchall()
    return rows


def print_table(rows, title):
    print(f"\n{'=' * 90}")
    print(f"  {title}")
    print(f"{'=' * 90}")
    header = f"{'Week':10} {'Runs':5} {'km':7} {'Time':9} {'Long run':9} {'Elev(m)':8} {'Avg pace':9} {'Avg HR':7} {'Suffer':7}"
    print(header)
    print("-" * 90)
    for r in rows:
        week_start, runs, dist_m, time_s, long_m, elev, hr, speed, suffer = (
            r[1], r[2], r[3] or 0, r[4] or 0, r[5] or 0, r[6] or 0,
            r[7], r[8], r[9] or 0
        )
        print(
            f"{week_start:10} {runs:5} {dist_m/1000:7.1f} {hms(time_s):9} "
            f"{long_m/1000:8.1f}k {elev:8.0f} {pace_str(speed):9} "
            f"{hr:7.0f} {suffer:7.0f}"
        )
    print("-" * 90)
    total_km = sum((r[3] or 0) for r in rows) / 1000
    total_time = sum((r[4] or 0) for r in rows)
    print(f"{'TOTAL':10} {sum(r[2] for r in rows):5} {total_km:7.1f} {hms(total_time):9}")
    print()


def save_csv(rows, filename, title):
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([title])
        writer.writerow([
            "week_start", "runs", "km", "moving_time",
            "long_run_km", "elevation_m", "avg_pace_min_km",
            "avg_hr", "suffer_score"
        ])
        for r in rows:
            week_start, runs, dist_m, time_s, long_m, elev, hr, speed, suffer = (
                r[1], r[2], r[3] or 0, r[4] or 0, r[5] or 0, r[6] or 0,
                r[7], r[8], r[9] or 0
            )
            writer.writerow([
                week_start, runs,
                round(dist_m / 1000, 2),
                hms(time_s),
                round(long_m / 1000, 2),
                round(elev, 0),
                pace_str(speed),
                round(hr, 1) if hr else "",
                int(suffer),
            ])
    print(f"CSV saved to {filename}")


def cmd_pb_build(conn):
    end = datetime.strptime(MARATHON_PB_DATE, "%Y-%m-%d")
    start = end - timedelta(weeks=PB_BUILD_WEEKS)
    rows = fetch_weekly_runs(conn, start.strftime("%Y-%m-%d"), MARATHON_PB_DATE)
    title = f"{PB_BUILD_WEEKS}-week build-up to marathon PB ({MARATHON_PB_DATE})"
    print_table(rows, title)
    save_csv(rows, "pb_build.csv", title)


def cmd_weekly(conn, weeks):
    end = datetime.now(timezone.utc)
    start = end - timedelta(weeks=weeks)
    rows = fetch_weekly_runs(conn, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    title = f"Last {weeks} weeks of running (sub-3 training tracker)"
    print_table(rows, title)
    save_csv(rows, "weekly_training.csv", title)


def main():
    parser = argparse.ArgumentParser(description="Strava running analysis")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--pb-build", action="store_true",
                       help=f"Show {PB_BUILD_WEEKS}-week build into marathon PB ({MARATHON_PB_DATE})")
    group.add_argument("--weekly", type=int, metavar="N", default=None,
                       help="Show last N weeks of training (default 16)")
    args = parser.parse_args()

    conn = get_connection()

    if args.pb_build:
        cmd_pb_build(conn)
    else:
        cmd_weekly(conn, args.weekly or 16)

    conn.close()


if __name__ == "__main__":
    main()

"""
report.py - Weekly training compliance report.

Reads your plan from plan_config.py. Edit that file to customise
session targets, pace bands, and weekly structure.
"""

import csv
from datetime import datetime, timedelta
from db import get_connection
import plan_config as cfg


def pace_str(pace_s):
    if not pace_s:
        return "--:--"
    m, s = divmod(int(pace_s), 60)
    return f"{m}:{s:02d}"


def pace_from_speed(avg_speed_ms):
    if not avg_speed_ms or avg_speed_ms == 0:
        return None
    return 1000 / avg_speed_ms


def local_dow(start_date_local):
    dt = datetime.fromisoformat(start_date_local.replace("Z", ""))
    return dt.weekday()  # Mon=0 ... Sun=6


def fetch_runs(conn, week_start, week_end):
    return conn.execute("""
        SELECT
            json_extract(raw_json, '$.start_date_local') AS local_dt,
            name, distance / 1000.0 AS km, average_speed, average_heartrate,
            json_extract(raw_json, '$.suffer_score') AS suffer
        FROM activities
        WHERE type IN ('Run', 'VirtualRun')
          AND date(json_extract(raw_json, '$.start_date_local')) >= ?
          AND date(json_extract(raw_json, '$.start_date_local')) <= ?
          AND distance >= ?
        ORDER BY local_dt
    """, (week_start, week_end, cfg.MIN_RUN_KM * 1000)).fetchall()


def fetch_cross(conn, week_start, week_end):
    rows = conn.execute("""
        SELECT
            json_extract(raw_json, '$.start_date_local') AS local_dt,
            type, name, moving_time / 60.0 AS mins
        FROM activities
        WHERE type IN ('VirtualRide', 'Ride', 'WeightTraining', 'Workout')
          AND date(json_extract(raw_json, '$.start_date_local')) >= ?
          AND date(json_extract(raw_json, '$.start_date_local')) <= ?
        ORDER BY local_dt
    """, (week_start, week_end)).fetchall()

    by_dow = {}
    for local_dt, typ, name, mins in rows:
        dow = local_dow(local_dt)
        entry = by_dow.setdefault(dow, {"bike_mins": 0, "strength_mins": 0, "sessions": []})
        entry["sessions"].append({"type": typ, "name": name, "mins": mins})
        if typ in ("VirtualRide", "Ride"):
            entry["bike_mins"] += mins
        elif typ in ("WeightTraining", "Workout"):
            entry["strength_mins"] += mins
    return by_dow


def detect_week_type(conn):
    if cfg.FORCE_WEEK_TYPE:
        return cfg.FORCE_WEEK_TYPE

    row = conn.execute("""
        SELECT average_speed, name FROM activities
        WHERE type IN ('Run', 'VirtualRun')
          AND strftime('%w', json_extract(raw_json, '$.start_date_local')) = '6'
          AND date(json_extract(raw_json, '$.start_date_local')) >= date('now', '-14 days')
          AND distance >= ?
        ORDER BY json_extract(raw_json, '$.start_date_local') DESC
        LIMIT 1
    """, (cfg.MIN_RUN_KM * 1000,)).fetchone()

    if not row:
        return "A"
    speed, name = row
    pace = pace_from_speed(speed)
    is_tempo = (pace and pace < cfg.PARKRUN_PACE_MAX + 10) or \
               ("park" in (name or "").lower())
    return "A" if is_tempo else "B"


def check_run(label, actual_pace_s, pace_min, pace_max):
    if actual_pace_s is None:
        return f"  {label:22} - no session recorded"
    p = pace_str(actual_pace_s)
    if actual_pace_s < pace_min:
        flag = f"[FAST] ({p}/km - target {pace_str(pace_min)}-{pace_str(pace_max)})"
    elif actual_pace_s > pace_max:
        flag = f"[SLOW] ({p}/km - target {pace_str(pace_min)}-{pace_str(pace_max)})"
    else:
        flag = f"[OK]   ({p}/km)"
    return f"  {label:22} {flag}"


def check_duration(label, actual_mins, target_mins):
    if actual_mins == 0:
        return f"  {label:22} - no session recorded"
    flag = "[OK]  " if actual_mins >= target_mins else f"[SHORT] ({actual_mins:.0f}min / target {target_mins}min)"
    return f"  {label:22} {flag}  ({actual_mins:.0f}min)"


def run_report():
    conn = get_connection()

    today = datetime.now() + timedelta(hours=12)  # NZ local approx
    days_since_sunday = (today.weekday() + 1) % 7
    week_end = (today - timedelta(days=days_since_sunday)).date()
    week_start = week_end - timedelta(days=6)

    week_type = detect_week_type(conn)
    next_week_type = "B" if week_type == "A" else "A"

    runs = fetch_runs(conn, str(week_start), str(week_end))
    cross = fetch_cross(conn, str(week_start), str(week_end))

    # Index runs by day-of-week
    runs_by_dow = {}
    for row in runs:
        local_dt, name, km, speed, hr, suffer = row
        dow = local_dow(local_dt)
        runs_by_dow.setdefault(dow, []).append({
            "name": name, "km": km, "pace": pace_from_speed(speed), "hr": hr,
        })

    def best_pace(dow):
        paces = [r["pace"] for r in runs_by_dow.get(dow, []) if r["pace"]]
        return min(paces) if paces else None

    def day_km(dow):
        return sum(r["km"] for r in runs_by_dow.get(dow, []))

    weekly_km = sum(r[2] for r in runs)
    long_run_km = max((r[2] for r in runs), default=0)

    # --- Header ---
    print(f"\n{'=' * 65}")
    print(f"  WEEKLY TRAINING REPORT - w/e {week_end}")
    print(f"  Goal: {cfg.GOAL_DESCRIPTION}")
    print(f"  Week type: {week_type}  |  Next week: {next_week_type}")
    print(f"{'=' * 65}")

    # --- Session compliance ---
    print(f"\n-- SESSION COMPLIANCE")

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    current_day = None

    for session in cfg.SESSIONS:
        dow = session["day"]
        label = session["label"]
        stype = session["type"]
        is_alt = session.get("alternating", False)
        week_for_session = session.get("week")

        # Skip the half of an alternating pair that doesn't apply this week
        if is_alt and week_for_session and week_for_session != week_type:
            continue

        if dow != current_day:
            print(f"  {day_names[dow]}")
            current_day = dow

        cx = cross.get(dow, {"bike_mins": 0, "strength_mins": 0})

        if stype == "run_easy":
            print(check_run(f"  {label}", best_pace(dow), cfg.EASY_PACE_MIN, cfg.EASY_PACE_MAX))
        elif stype == "run_workout":
            pace = best_pace(dow)
            if pace:
                flag = "[OK]   quality session" if pace < cfg.WORKOUT_PACE_MAX else f"[SLOW] {pace_str(pace)}/km - push harder"
                print(f"  {'  ' + label:22} {flag}  ({day_km(dow):.1f}km)")
            else:
                print(f"  {'  ' + label:22} - no session recorded")
        elif stype == "run_parkrun":
            print(check_run(f"  {label}", best_pace(dow), cfg.PARKRUN_PACE_MIN, cfg.PARKRUN_PACE_MAX))
        elif stype == "run_long_A":
            print(check_run(f"  {label}", best_pace(dow), cfg.LONG_RUN_A_MIN, cfg.LONG_RUN_A_MAX))
        elif stype == "run_long_B":
            print(check_run(f"  {label}", best_pace(dow), cfg.LONG_RUN_B_MIN, cfg.LONG_RUN_B_MAX))
        elif stype == "bike":
            print(check_duration(f"  {label}", cx["bike_mins"], cfg.BIKE_TARGET_MINS))
        elif stype == "strength":
            print(check_duration(f"  {label}", cx["strength_mins"], cfg.STRENGTH_TARGET_MINS))

    # --- Volume ---
    km_diff = weekly_km - cfg.BENCHMARK_WEEKLY_KM
    km_flag = "[OK]" if 60 <= weekly_km <= 120 else "[LOW]"
    lr_flag = "[OK]" if long_run_km >= cfg.BENCHMARK_LONG_RUN_KM else f"[SHORT - aim for {cfg.BENCHMARK_LONG_RUN_KM:.0f}km+]"

    print(f"\n-- VOLUME vs BENCHMARK")
    print(f"  {'Weekly km:':22} {weekly_km:6.1f}km  (target ~{cfg.BENCHMARK_WEEKLY_KM}km  {km_diff:+.1f}km)  {km_flag}")
    print(f"  {'Long run:':22} {long_run_km:6.1f}km  (target {cfg.BENCHMARK_LONG_RUN_KM:.0f}km)  {lr_flag}")

    # --- All sessions ---
    print(f"\n-- ALL SESSIONS THIS WEEK")
    all_rows = []
    for r in runs:
        local_dt, name, km, speed, hr, _ = r
        dow = local_dow(local_dt)
        pace = pace_from_speed(speed)
        all_rows.append((local_dt, day_names[dow], "RUN", f"{km:.1f}km", pace_str(pace), f"HR:{hr or '--'}", name))
    for dow, entry in sorted(cross.items()):
        for s in entry["sessions"]:
            all_rows.append(("", day_names[dow], s["type"][:7], f"{s['mins']:.0f}min", "", "", s["name"]))
    all_rows.sort(key=lambda x: x[0])
    for row in all_rows:
        _, day, typ, dur, pace, hr, name = row
        print(f"  {day}  {typ:7}  {dur:8}  {pace:9}  {hr:10}  {name}")

    # --- Next week ---
    nw = next_week_type
    print(f"\n-- NEXT WEEK FOCUS (Week {nw})")
    for session in cfg.SESSIONS:
        is_alt = session.get("alternating", False)
        week_for_session = session.get("week")
        if is_alt and week_for_session and week_for_session != nw:
            continue
        dow = session["day"]
        stype = session["type"]
        targets = {
            "run_easy":    f"easy run ({pace_str(cfg.EASY_PACE_MIN)}-{pace_str(cfg.EASY_PACE_MAX)}/km)",
            "run_workout": f"quality run (faster than {pace_str(cfg.WORKOUT_PACE_MAX)}/km)",
            "run_parkrun": f"parkrun at tempo ({pace_str(cfg.PARKRUN_PACE_MIN)}-{pace_str(cfg.PARKRUN_PACE_MAX)}/km)",
            "run_long_A":  f"long run easy ({pace_str(cfg.LONG_RUN_A_MIN)}-{pace_str(cfg.LONG_RUN_A_MAX)}/km)",
            "run_long_B":  f"long run at marathon pace ({pace_str(cfg.LONG_RUN_B_MIN)}-{pace_str(cfg.LONG_RUN_B_MAX)}/km)",
            "bike":        f"bike ({cfg.BIKE_TARGET_MINS}min+)",
            "strength":    f"strength ({cfg.STRENGTH_TARGET_MINS}min+)",
        }
        print(f"  {day_names[dow]:3}  {session['label']:28}  {targets.get(stype, '')}")

    print()

    # --- CSV ---
    filename = f"weekly_report_{week_end}.csv"
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "day", "type", "km_or_mins", "pace", "hr", "name"])
        for row in all_rows:
            writer.writerow(row)
    print(f"CSV saved: {filename}")

    conn.close()


if __name__ == "__main__":
    run_report()

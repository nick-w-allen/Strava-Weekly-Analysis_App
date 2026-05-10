"""
report.py - Weekly training compliance report.

Reads your plan from plan_config.py. Edit that file to customise
session targets, pace bands, and weekly structure.

Outputs to terminal AND writes compliance.md (open in any markdown viewer).
"""

import csv
import os
from datetime import datetime, timedelta
from db import get_connection
import plan_config as cfg

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

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
    is_tempo = (pace and pace < cfg.PARKRUN_PACE_MAX + 10) or ("park" in (name or "").lower())
    return "A" if is_tempo else "B"


# ---------------------------------------------------------------------------
# Build report data
# ---------------------------------------------------------------------------

def build_report(conn, week_start, week_end, week_type):
    next_week_type = "B" if week_type == "A" else "A"
    runs  = fetch_runs(conn, str(week_start), str(week_end))
    cross = fetch_cross(conn, str(week_start), str(week_end))

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

    weekly_km    = sum(r[2] for r in runs)
    long_run_km  = max((r[2] for r in runs), default=0)

    # Build compliance rows
    compliance = []
    for session in cfg.SESSIONS:
        dow            = session["day"]
        label          = session["label"]
        stype          = session["type"]
        is_alt         = session.get("alternating", False)
        week_for_sess  = session.get("week")

        if is_alt and week_for_sess and week_for_sess != week_type:
            continue

        cx = cross.get(dow, {"bike_mins": 0, "strength_mins": 0})

        if stype == "run_easy":
            p = best_pace(dow)
            status, detail = _run_status(p, cfg.EASY_PACE_MIN, cfg.EASY_PACE_MAX)
        elif stype == "run_workout":
            p = best_pace(dow)
            if p is None:
                status, detail = "MISS", "no session recorded"
            elif p < cfg.WORKOUT_PACE_MAX:
                status, detail = "OK", f"{pace_str(p)}/km  ({day_km(dow):.1f}km)"
            else:
                status, detail = "SLOW", f"{pace_str(p)}/km - push harder  ({day_km(dow):.1f}km)"
        elif stype == "run_parkrun":
            p = best_pace(dow)
            status, detail = _run_status(p, cfg.PARKRUN_PACE_MIN, cfg.PARKRUN_PACE_MAX)
        elif stype == "run_long_A":
            p = best_pace(dow)
            status, detail = _run_status(p, cfg.LONG_RUN_A_MIN, cfg.LONG_RUN_A_MAX)
        elif stype == "run_long_B":
            p = best_pace(dow)
            status, detail = _run_status(p, cfg.LONG_RUN_B_MIN, cfg.LONG_RUN_B_MAX)
        elif stype == "bike":
            status, detail = _dur_status(cx["bike_mins"], cfg.BIKE_TARGET_MINS)
        elif stype == "strength":
            status, detail = _dur_status(cx["strength_mins"], cfg.STRENGTH_TARGET_MINS)
        else:
            status, detail = "MISS", ""

        compliance.append({
            "day": DAY_NAMES[dow], "label": label,
            "status": status, "detail": detail,
        })

    # All sessions (runs + cross) sorted by time
    all_sessions = []
    for r in runs:
        local_dt, name, km, speed, hr, _ = r
        dow = local_dow(local_dt)
        all_sessions.append({
            "dt": local_dt, "day": DAY_NAMES[dow], "type": "Run",
            "value": f"{km:.1f}km", "pace": pace_str(pace_from_speed(speed)),
            "hr": f"{hr:.0f}" if hr else "--", "name": name,
        })
    for dow, entry in sorted(cross.items()):
        for s in entry["sessions"]:
            all_sessions.append({
                "dt": "", "day": DAY_NAMES[dow], "type": s["type"][:10],
                "value": f"{s['mins']:.0f}min", "pace": "--", "hr": "--", "name": s["name"],
            })
    all_sessions.sort(key=lambda x: (x["dt"] or "9"))

    # Next week sessions
    next_sessions = []
    for session in cfg.SESSIONS:
        is_alt        = session.get("alternating", False)
        week_for_sess = session.get("week")
        if is_alt and week_for_sess and week_for_sess != next_week_type:
            continue
        stype = session["type"]
        desc  = {
            "run_easy":    f"Easy run: {pace_str(cfg.EASY_PACE_MIN)} to {pace_str(cfg.EASY_PACE_MAX)}/km",
            "run_workout": f"Quality run: faster than {pace_str(cfg.WORKOUT_PACE_MAX)}/km",
            "run_parkrun": f"Parkrun at tempo: {pace_str(cfg.PARKRUN_PACE_MIN)} to {pace_str(cfg.PARKRUN_PACE_MAX)}/km",
            "run_long_A":  f"Long run easy: {pace_str(cfg.LONG_RUN_A_MIN)} to {pace_str(cfg.LONG_RUN_A_MAX)}/km",
            "run_long_B":  f"Long run at marathon pace: {pace_str(cfg.LONG_RUN_B_MIN)} to {pace_str(cfg.LONG_RUN_B_MAX)}/km",
            "bike":        f"Bike: {cfg.BIKE_TARGET_MINS}min+",
            "strength":    f"Strength: {cfg.STRENGTH_TARGET_MINS}min+",
        }.get(stype, stype)
        next_sessions.append({"day": DAY_NAMES[session["day"]], "label": session["label"], "desc": desc})

    return {
        "week_start":      week_start,
        "week_end":        week_end,
        "week_type":       week_type,
        "next_week_type":  next_week_type,
        "weekly_km":       weekly_km,
        "long_run_km":     long_run_km,
        "compliance":      compliance,
        "all_sessions":    all_sessions,
        "next_sessions":   next_sessions,
    }


def _run_status(pace_s, pace_min, pace_max):
    if pace_s is None:
        return "MISS", "no session recorded"
    p = pace_str(pace_s)
    if pace_s < pace_min:
        return "FAST", f"{p}/km (target {pace_str(pace_min)}-{pace_str(pace_max)})"
    elif pace_s > pace_max:
        return "SLOW", f"{p}/km (target {pace_str(pace_min)}-{pace_str(pace_max)})"
    return "OK", f"{p}/km"


def _dur_status(actual_mins, target_mins):
    if actual_mins == 0:
        return "MISS", "no session recorded"
    if actual_mins >= target_mins:
        return "OK", f"{actual_mins:.0f}min"
    return "SHORT", f"{actual_mins:.0f}min (target {target_mins}min)"


# ---------------------------------------------------------------------------
# Terminal renderer  (ASCII-safe for Windows cmd)
# ---------------------------------------------------------------------------

STATUS_LABEL = {"OK": "[OK]   ", "FAST": "[FAST] ", "SLOW": "[SLOW] ",
                "SHORT": "[SHORT]", "MISS": "[MISS] "}

def _safe(text):
    """Strip characters the Windows console can't render."""
    return str(text).encode("cp1252", errors="replace").decode("cp1252")


def render_terminal(data):
    w = data
    print(f"\n{'=' * 65}")
    print(f"  WEEKLY TRAINING REPORT - w/e {w['week_end']}")
    print(f"  Goal: {cfg.GOAL_DESCRIPTION}  |  Week {w['week_type']}  ->  Next: Week {w['next_week_type']}")
    print(f"{'=' * 65}")

    print("\n-- SESSION COMPLIANCE")
    current_day = None
    for row in w["compliance"]:
        if row["day"] != current_day:
            print(f"  {row['day']}")
            current_day = row["day"]
        lbl = STATUS_LABEL.get(row["status"], "       ")
        print(f"    {lbl}  {row['label']:28}  {row['detail']}")

    km_diff = w["weekly_km"] - cfg.BENCHMARK_WEEKLY_KM
    km_flag = "[OK]" if 60 <= w["weekly_km"] <= 120 else "[LOW]"
    lr_flag = "[OK]" if w["long_run_km"] >= cfg.BENCHMARK_LONG_RUN_KM else f"[SHORT - aim {cfg.BENCHMARK_LONG_RUN_KM:.0f}km+]"
    print(f"\n-- VOLUME vs BENCHMARK")
    print(f"  Weekly km : {w['weekly_km']:6.1f}km  (target ~{cfg.BENCHMARK_WEEKLY_KM}km  {km_diff:+.1f}km)  {km_flag}")
    print(f"  Long run  : {w['long_run_km']:6.1f}km  (target {cfg.BENCHMARK_LONG_RUN_KM:.0f}km)  {lr_flag}")

    print(f"\n-- ALL SESSIONS")
    for s in w["all_sessions"]:
        print(f"  {s['day']}  {s['type']:10}  {s['value']:8}  {s['pace']:9}  HR:{s['hr']:5}  {_safe(s['name'])}")

    print(f"\n-- NEXT WEEK (Week {w['next_week_type']})")
    for s in w["next_sessions"]:
        print(f"  {s['day']}  {s['label']:28}  {s['desc']}")
    print()


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

STATUS_EMOJI = {"OK": "✅", "FAST": "⚡", "SLOW": "🐢", "SHORT": "⚠️", "MISS": "❌"}

def render_markdown(data, path="compliance.md"):
    w = data
    lines = []
    a = lines.append

    a(f"# Weekly Training Report — w/e {w['week_end']}")
    a(f"")
    a(f"**Goal:** {cfg.GOAL_DESCRIPTION} &nbsp;|&nbsp; **This week:** Week {w['week_type']} &nbsp;|&nbsp; **Next week:** Week {w['next_week_type']}")
    a(f"")

    # Session compliance table
    a(f"## Session Compliance")
    a(f"")
    a(f"| Day | Session | Status | Detail |")
    a(f"|-----|---------|--------|--------|")
    for row in w["compliance"]:
        emoji = STATUS_EMOJI.get(row["status"], "")
        a(f"| {row['day']} | {row['label']} | {emoji} {row['status']} | {row['detail']} |")
    a(f"")

    # Volume
    km_diff    = w["weekly_km"] - cfg.BENCHMARK_WEEKLY_KM
    km_emoji   = "✅" if 60 <= w["weekly_km"] <= 120 else "⚠️"
    lr_emoji   = "✅" if w["long_run_km"] >= cfg.BENCHMARK_LONG_RUN_KM else "⚠️"
    a(f"## Volume vs Benchmark")
    a(f"")
    a(f"| Metric | This week | Target | Status |")
    a(f"|--------|-----------|--------|--------|")
    a(f"| Weekly km | {w['weekly_km']:.1f}km | ~{cfg.BENCHMARK_WEEKLY_KM}km | {km_emoji} {km_diff:+.1f}km |")
    a(f"| Long run | {w['long_run_km']:.1f}km | {cfg.BENCHMARK_LONG_RUN_KM:.0f}km | {lr_emoji} |")
    a(f"")

    # All sessions
    a(f"## All Sessions This Week")
    a(f"")
    a(f"| Day | Type | Distance / Duration | Pace | HR | Activity |")
    a(f"|-----|------|---------------------|------|----|----------|")
    for s in w["all_sessions"]:
        a(f"| {s['day']} | {s['type']} | {s['value']} | {s['pace']} | {s['hr']} | {s['name']} |")
    a(f"")

    # Next week
    a(f"## Next Week Focus — Week {w['next_week_type']}")
    a(f"")
    a(f"| Day | Session | Target |")
    a(f"|-----|---------|--------|")
    for s in w["next_sessions"]:
        a(f"| {s['day']} | {s['label']} | {s['desc']} |")
    a(f"")
    a(f"---")
    a(f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} by strava-training-pipeline*")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Markdown saved: {path}")


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def save_csv(data):
    filename = f"weekly_report_{data['week_end']}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "day", "type", "value", "pace", "hr", "name"])
        for s in data["all_sessions"]:
            writer.writerow([s["dt"][:10] if s["dt"] else "", s["day"],
                             s["type"], s["value"], s["pace"], s["hr"], s["name"]])
    print(f"CSV saved:      {filename}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_report():
    conn = get_connection()

    today    = datetime.now() + timedelta(hours=12)
    days_ago = (today.weekday() + 1) % 7
    week_end   = (today - timedelta(days=days_ago)).date()
    week_start = week_end - timedelta(days=6)

    week_type = detect_week_type(conn)
    data = build_report(conn, week_start, week_end, week_type)

    render_terminal(data)
    render_markdown(data)
    save_csv(data)

    conn.close()


if __name__ == "__main__":
    run_report()

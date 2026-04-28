# Strava Training Pipeline

A local data pipeline that syncs your Strava activity history into a SQLite database and generates a weekly training compliance report against your own plan.

Built for marathon training — but configurable for any goal.

---

## What it does

- **Authenticates** with Strava via OAuth (one-time setup)
- **Syncs** your full activity history to a local SQLite database
- **Analyses** weekly training against your plan targets (pace, duration, session type)
- **Reports** compliance every Monday morning via Windows Task Scheduler
- **Exports** a CSV of each week for further analysis

---

## Setup

### 1. Create a Strava API app

1. Go to [strava.com/settings/api](https://www.strava.com/settings/api)
2. Create an app (any name, set **Authorization Callback Domain** to `localhost`)
3. Note your **Client ID** and **Client Secret**

### 2. Configure your Client ID

Create a `.env` file based on `.env.example` and set your Client ID:

```bash
cp .env.example .env
```

Edit `.env`:

```env
STRAVA_CLIENT_ID=your_client_id_here
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Authenticate

```bash
python main.py --auth
```

A browser window opens. Authorise the app, and your tokens are saved to `strava_tokens.json` (this file is gitignored — never commit it).

### 5. Sync your activity history

```bash
# Full history sync
python main.py --full

# Incremental sync (only new activities since last sync)
python main.py --sync
```

---

## Weekly report

```bash
python report.py
```

Outputs a compliance report for the most recently completed Mon–Sun week, comparing each session against your plan targets. Also saves a dated CSV.

### Automate it (Windows)

To run every Monday at 8am automatically, create a scheduled task in Task Scheduler pointing to:

```
run_weekly_report.bat
```

---

## Customise your plan

**All plan targets live in `plan_config.py`.** Edit this file to match your training:

```python
# Your goal (shown in report header)
GOAL_DESCRIPTION = "Sub-3 marathon"

# Volume benchmarks
BENCHMARK_WEEKLY_KM   = 73.6
BENCHMARK_LONG_RUN_KM = 35.0

# Pace targets (seconds per km)
EASY_PACE_MIN    = 5*60+10   # 5:10/km
EASY_PACE_MAX    = 5*60+50   # 5:50/km
LONG_RUN_B_MIN   = 4*60+5    # marathon pace band low
LONG_RUN_B_MAX   = 4*60+20   # marathon pace band high
...

# Your weekly sessions
SESSIONS = [
    {"day": 0, "label": "Mon bike",     "type": "bike",     ...},
    {"day": 1, "label": "Tue easy run", "type": "run_easy", ...},
    ...
]
```

### Session types

| Type | Description |
|---|---|
| `run_easy` | Easy run — checks against `EASY_PACE_MIN/MAX` |
| `run_workout` | Quality run — checks faster than `WORKOUT_PACE_MAX` |
| `run_parkrun` | Tempo parkrun — checks against `PARKRUN_PACE_MIN/MAX` |
| `run_long_A` | Long run easy week — checks against `LONG_RUN_A_MIN/MAX` |
| `run_long_B` | Long run quality week — checks against `LONG_RUN_B_MIN/MAX` |
| `bike` | Bike session — checks total minutes against `BIKE_TARGET_MINS` |
| `strength` | Strength session — checks total minutes against `STRENGTH_TARGET_MINS` |

### Alternating weeks

Set `"alternating": True` with a `"pair_id"` and `"week": "A"` or `"B"` to define sessions that alternate week-by-week:

```python
{"day": 5, "label": "Sat parkrun", "type": "run_parkrun", "alternating": True, "pair_id": "sat", "week": "A"},
{"day": 5, "label": "Sat easy",    "type": "run_easy",    "alternating": True, "pair_id": "sat", "week": "B"},
```

The report auto-detects which week type it is by looking at your most recent Saturday pace.

---

## Analysis tools

```bash
# 20-week build into your marathon PB
python analyse.py --pb-build

# Last N weeks of training
python analyse.py --weekly 16
```

---

## Files

| File | Purpose |
|---|---|
| `auth.py` | OAuth flow + token refresh |
| `db.py` | SQLite schema and upsert logic |
| `sync.py` | Paginated Strava activity fetch |
| `main.py` | CLI entry point (`--auth`, `--sync`, `--full`) |
| `report.py` | Weekly compliance report |
| `analyse.py` | Historical trend analysis |
| `plan_config.py` | **Your plan — edit this** |
| `strava_tokens.sample.json` | Token file format reference |
| `run_weekly_report.bat` | Windows scheduled task script |

---

## Notes

- `strava_tokens.json` and `strava.db` are gitignored — they stay local
- The pipeline uses NZ timezone (UTC+12) by default; adjust the `+12` offset in `report.py` if needed
- Strava rate limits are handled automatically (429 → 60s wait → retry)

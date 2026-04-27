"""
plan_config.py — Edit this file to define YOUR training plan.

The weekly report (report.py) reads everything from here.
Each session is defined by:
  - which day(s) of the week it falls on (0=Mon, 1=Tue, ... 6=Sun)
  - the activity type (run, bike, strength)
  - the pace or duration target

Pace targets are in seconds per km.
Duration targets are in minutes.
"""

# ---------------------------------------------------------------------------
# YOUR GOAL
# ---------------------------------------------------------------------------
GOAL_DESCRIPTION = "Sub-3 marathon"

# Benchmark weekly km and long run from your best training block.
# The report flags you if you fall short of these.
BENCHMARK_WEEKLY_KM = 73.6   # avg km/week during your PB build
BENCHMARK_LONG_RUN_KM = 35.0  # long run to aim for each week


# ---------------------------------------------------------------------------
# PACE TARGETS  (format: minutes * 60 + seconds)
# ---------------------------------------------------------------------------
EASY_PACE_MIN    = 5*60+10   # slowest easy pace (5:10/km)
EASY_PACE_MAX    = 5*60+50   # fastest easy pace (5:50/km)

WORKOUT_PACE_MAX = 5*60+0    # workout runs should be faster than this

LONG_RUN_A_MIN   = 5*60+10   # long run easy week: target pace band
LONG_RUN_A_MAX   = 5*60+50

LONG_RUN_B_MIN   = 4*60+5    # long run quality week: marathon pace band
LONG_RUN_B_MAX   = 4*60+20   # (e.g. 4:05-4:20 for sub-3)

PARKRUN_PACE_MIN = 3*60+45   # tempo parkrun target band
PARKRUN_PACE_MAX = 4*60+0


# ---------------------------------------------------------------------------
# DURATION TARGETS  (minutes)
# ---------------------------------------------------------------------------
BIKE_TARGET_MINS     = 55    # 1hr bike session (55min counts as OK)
STRENGTH_TARGET_MINS = 40    # 45min strength (40min counts as OK)

# Minimum km for a run to count as a proper session (filters commutes)
MIN_RUN_KM = 3.0


# ---------------------------------------------------------------------------
# WEEKLY SESSIONS
# Define your plan as a list of session checks.
# Each entry is a dict with:
#   day        : 0-6 (Mon-Sun)
#   label      : name shown in the report
#   type       : "run_easy" | "run_workout" | "run_parkrun" |
#                "run_long_A" | "run_long_B" | "bike" | "strength"
#
# For alternating weeks (type "run_long_A" / "run_long_B" or
# "run_parkrun" / "run_easy"), set alternating=True and pair them
# with the same `pair_id`. Week A runs the first session with that
# pair_id; Week B runs the second.
# ---------------------------------------------------------------------------
SESSIONS = [
    # Monday
    {"day": 0, "label": "Mon bike",     "type": "bike",         "alternating": False},
    {"day": 0, "label": "Mon strength", "type": "strength",     "alternating": False},

    # Tuesday
    {"day": 1, "label": "Tue easy run", "type": "run_easy",     "alternating": False},

    # Wednesday
    {"day": 2, "label": "Wed workout",  "type": "run_workout",  "alternating": False},
    {"day": 2, "label": "Wed strength", "type": "strength",     "alternating": False},

    # Friday
    {"day": 4, "label": "Fri bike",     "type": "bike",         "alternating": False},
    {"day": 4, "label": "Fri strength", "type": "strength",     "alternating": False},

    # Saturday — alternates between parkrun tempo (Week A) and easy (Week B)
    {"day": 5, "label": "Sat parkrun",  "type": "run_parkrun",  "alternating": True, "pair_id": "sat", "week": "A"},
    {"day": 5, "label": "Sat easy",     "type": "run_easy",     "alternating": True, "pair_id": "sat", "week": "B"},

    # Sunday — alternates between easy Waiwera (Week A) and marathon-pace Waiwera (Week B)
    {"day": 6, "label": "Sun Waiwera easy",       "type": "run_long_A", "alternating": True, "pair_id": "sun", "week": "A"},
    {"day": 6, "label": "Sun Waiwera marathon pace", "type": "run_long_B", "alternating": True, "pair_id": "sun", "week": "B"},
]


# ---------------------------------------------------------------------------
# WEEK DETECTION
# The report auto-detects whether the current week is A or B by looking
# at last Saturday's run. If it matched parkrun tempo, it was Week A.
# Override here if you want to force a specific week type.
# ---------------------------------------------------------------------------
FORCE_WEEK_TYPE = None   # set to "A" or "B" to override auto-detection

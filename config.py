OTHER_SOURCE_MAX_CHARS = 20000
REFERENCE_NEWSLETTER_FILE = "newsletter_reference.html"

# All per-cadence settings in one place. To add a new cadence, just add an entry.
#   hours:              source lookback window (interval + 4h margin)
#   recent_newsletters: how many past issues to check for anti-repetition
#   run_day:            weekday to run (0=Mon ... 6=Sun), None = every day
CADENCE = {
  "Daily": {
    "hours": 28,
    "recent_newsletters": 7,
    "run_day": None,
  },
  "Weekly": {
    "hours": 172,
    "recent_newsletters": 2,
    "run_day": 0,
  },
}
DEFAULT_CADENCE = "Daily"

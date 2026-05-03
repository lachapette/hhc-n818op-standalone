# Standard Library
import sys
from datetime import timedelta
from pathlib import Path

PLUGIN_RELAYS = "plugin_relays"
RELAYS_SCENARIOS = "relays_scenarios"
RELAYS_DEFAULT = "relays_default"
TIMEZONE = "timezone"
RELAY = "hhc-n818op"
PIDFILE = "pidfile"
HOST = "host"
PORT = "port"
DAEMON = "daemon"
LOG_LEVEL = "log_level"
YAML_EXTENSION = ".yaml"
CYCLE = "cycle"
CYCLE_SLEEPING = "cycle_sleeping"
TIMEOUT = "timeout"
LOGFILE = "logfile"
DATE_TIME_FORMAT = "%d/%m/%y %H:%M:%S.%f"
TIMEOUT_PLUGINS_INIT = 15
# Periodicity configuration
PERIODICITY = "periodicity"
MASK_END_STRATEGY = "mask_end_strategy"
CUSTOM_DAYS = "custom_days"
ONE_DAY_DELTA = timedelta(days=1)

# Mask end strategy constants
MASK_END_STRATEGY_END_OF_DAY = "end_of_day"
MASK_END_STRATEGY_END_OF_WEEK = "end_of_week"
MASK_END_STRATEGY_END_OF_MONTH = "end_of_month"
MASK_END_STRATEGY_CUSTOM_DAYS = "custom_days"

# Add the parent directory to sys.path to ensure we can import from daemon_hhc_n818op
PROJECT_ROOT_DIR: Path = Path(__file__)
if PROJECT_ROOT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_DIR.as_posix())

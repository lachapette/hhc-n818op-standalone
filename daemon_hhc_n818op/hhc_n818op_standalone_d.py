# Standard Library
import logging
import os
import signal
import sys
import threading
import time
import traceback
from pathlib import Path

# Third Party Libraries
from ruamel.yaml import YAML

# HHC_N818OP Client daemonized
from daemon_hhc_n818op import CYCLE, CYCLE_SLEEPING, DAEMON, HOST, LOG_LEVEL, LOGFILE, PIDFILE, PLUGIN_RELAYS, PORT, RELAY, RELAYS_SCENARIOS, TIMEOUT_PLUGINS_INIT, TIMEZONE, YAML_EXTENSION
from daemon_hhc_n818op.hhc_n818op.relay_client import Plugins, RelayClient, RelaysUtils

# Global references for cleanup
relay_client = None
relay_plugins = None


def shutdown(signum=None, frame=None):
    """Handle shutdown signals (SIGTERM, SIGINT, etc.)"""
    logging.info(f"Shutdown requested (signal: {signum})")
    try:
        if relay_client:
            relay_client.disconnect()
            relay_client.close()
        logging.info(f"{__file__} daemon stopped")
    except Exception as e:
        logging.error(f"Error during shutdown: {e}")
    try:
        if _pidfile and os.path.exists(_pidfile):
            os.remove(_pidfile)
            logging.debug(f"Removed PID file {_pidfile}")
    except OSError as e:
        logging.debug(f"Error removing PID file: {e}")
    logging.info("Exit 0")
    sys.stdout.flush()
    sys.exit(0)


def load_config():
    daemon_config_file = Path(__file__.replace(Path(__file__).suffix, YAML_EXTENSION))
    yaml = YAML()
    return yaml.load(daemon_config_file)


class SignalsHandler(threading.Thread):

    def __init__(self):
        super().__init__()
        # Configure signal handlers
        signal.signal(signal.SIGTERM, shutdown)  # Kill / SystemCtl stop
        signal.signal(signal.SIGINT, shutdown)  # Ctrl+C

    def run(self):
        try:
            # Note: signal.pause() is Unix-only, time.sleep() works on all platforms
            if hasattr(signal, "pause"):
                while True:
                    signal.pause()
            else:
                # Fallback for Windows
                while True:
                    time.sleep(1)
        except Exception as e:
            logging.error(f"Error : {e}")


# ----------------------------------------------------------------------------

cfg = load_config()

_log_level = cfg[DAEMON][LOG_LEVEL]
_pidfile = cfg[DAEMON][PIDFILE]
_cycle = cfg[DAEMON][CYCLE]
_cycle_sleeping = cfg[DAEMON][CYCLE_SLEEPING]
_logfile = cfg[DAEMON][LOGFILE] if LOGFILE in cfg[DAEMON] else None
_timezone = cfg[DAEMON][TIMEZONE] if TIMEZONE in cfg[DAEMON] else None

_relay_client_port = cfg[RELAY][PORT]
_relay_client_host = cfg[RELAY][HOST]
_relays_scenarios = cfg[RELAYS_SCENARIOS]
_relays_plugins_config: dict = cfg.get(PLUGIN_RELAYS, {})

RelaysUtils.set_log_level(_log_level, _logfile)

logging.info(f"Start {Path(__file__).name}")
logging.info(f"Log level : {_log_level}")
logging.info(f"Log file : {_logfile}")
logging.info(f"PID file : {_pidfile}")

try:
    RelaysUtils.write_pid(Path(_pidfile))
    relay_plugins = Plugins(_relays_plugins_config)
    relay_plugins.start()
    if not relay_plugins.wait_until_ready(timeout=TIMEOUT_PLUGINS_INIT):
        raise TimeoutError(f"Plugins initialization did not complete within {TIMEOUT_PLUGINS_INIT} seconds")
    relay_client = RelayClient(relay_plugins, _relay_client_host, _relay_client_port, _timezone, _cycle, _cycle_sleeping, _relays_scenarios)
    relay_client.start()

    # Wait indefinitely (signal handlers will trigger shutdown)
    SignalsHandler().start()

except Exception as e:
    logging.error(f"Fatal error : {e}")
    logging.info(traceback.format_exc())
    shutdown()

# Standard Library
import logging
import os
import signal
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Optional

# Third Party Libraries
from ruamel.yaml import YAML

# HHC_N818OP Client daemonized
from daemon_hhc_n818op import CYCLE, CYCLE_SLEEPING, DAEMON, HOST, LOG_LEVEL, LOGFILE, PERIODICITY, PIDFILE, PLUGIN_RELAYS, PORT, RELAY, RELAYS_DEFAULT, RELAYS_SCENARIOS, TIMEOUT_PLUGINS_INIT, TIMEZONE, YAML_EXTENSION
from daemon_hhc_n818op.hhc_n818op.relay_client import Plugins, RelayClient, RelaysUtils

# Global references for cleanup
relay_client: Optional[RelayClient] = None
relay_plugins: Optional[Plugins] = None
_pidfile: Optional[Path] = None


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
    # Ne pas appeler sys.exit() pendant les tests pytest (évite de tuer le processus pytest)
    # Vérification de plusieurs variables d'environnement pour détecter pytest
    in_pytest = os.environ.get("PYTEST_CURRENT_TEST") is not None or os.environ.get("PYTEST_XDIST_WORKER") is not None or os.environ.get("PYTEST_VERSION") is not None
    if not in_pytest:
        sys.exit(0)


def load_config():
    daemon_config_file = Path(__file__.replace(Path(__file__).suffix, YAML_EXTENSION))
    yaml = YAML()
    return yaml.load(daemon_config_file)


class SignalsHandler(threading.Thread):

    def __init__(self):
        super().__init__(daemon=True)
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


def main():
    """Main entry point for the daemon."""
    global relay_client, relay_plugins, _pidfile

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
    _relays_default = cfg.get(RELAYS_DEFAULT, [])
    _relays_plugins_config: dict = cfg.get(PLUGIN_RELAYS, {})
    _periodicity_config: dict = cfg.get(PERIODICITY, {})

    RelaysUtils.set_log_level(_log_level, _logfile)

    logging.info(f"Start {Path(__file__).name}")
    logging.info(f"Log level : {_log_level}")
    logging.info(f"Log file : {_logfile}")
    logging.info(f"PID file : {_pidfile}")

    try:
        RelaysUtils.write_pid(Path(_pidfile))

        # Create a barrier with 2 participants: RelayClient thread and Plugins thread
        # This ensures plugins initialization only happens AFTER relay precondition mask is applied
        plugins_barrier = threading.Barrier(2)

        # Initialize Plugins with barrier - it will wait for signal from RelayClient
        relay_plugins = Plugins(_relays_plugins_config, plugins_barrier)
        relay_plugins.start()

        # Create RelayClient with barrier - it will apply mask and signal the barrier
        relay_client = RelayClient(relay_plugins, _relay_client_host, _relay_client_port, _timezone, _cycle, _cycle_sleeping, _relays_scenarios, _relays_default, plugins_barrier, _periodicity_config)
        relay_client.start()

        # Wait for plugins to be ready (they were waiting for barrier signal from RelayClient)
        if not relay_plugins.wait_until_ready(timeout=TIMEOUT_PLUGINS_INIT):
            raise TimeoutError(f"Plugins initialization did not complete within {TIMEOUT_PLUGINS_INIT} seconds")

        # Wait indefinitely (signal handlers will trigger shutdown)
        SignalsHandler().start()

    except Exception as e:
        logging.error(f"Fatal error : {e}")
        logging.info(traceback.format_exc())
        shutdown()


if __name__ == "__main__":
    main()

from __future__ import annotations

# Standard Library
import logging
import os
import re
import sched
import socket
import threading
import time
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from sched import scheduler
from time import sleep

# Third Party Libraries
import _socket
from pytz import timezone

# HHC_N818OP Client daemonized
from daemon_hhc_n818op.hhc_n818op import ALL_RELAYS_ID, ALL_RELAYS_OFF, BUFFER_SIZE, LISTENER_SLEEPING_DELAY, NAME, READ, RELAYS, START_TIME
from daemon_hhc_n818op.hhc_n818op.relay_plugins import Plugins
from daemon_hhc_n818op.hhc_n818op.time_parser import RelayTimeParser

enum_socket = {value: key for (key, value) in vars(_socket).items() if isinstance(value, (str, int)) and not key.startswith("_")}


class RelayClient(threading.Thread):
    """
    A client for managing relay devices and their scheduling.
    This class handles the connection to a relay server, manages relay status updates,
    and schedules relay operations based on predefined scenarios.
    Args:
        plugins: A Plugins object managing plugin devices.
        _relay_server_host (str): Hostname or IP address of the relay server.
        _relay_server_port (int): Port number of the relay server.
        _timezone (str, optional): Timezone for scheduling. Defaults to the system timezone.
        _cycle (int): Refresh cycle duration in seconds.
        _cycle_sleeping (int): Sleep duration between cycles in seconds.
        _relays_scenarios (dict): Configuration for relay scenarios.
    """

    def __init__(
        self,
        plugins: "Plugins",
        _relay_server_host: str,
        _relay_server_port: int,
        _timezone: str | None,
        _cycle: int,
        _cycle_sleeping: int,
        _relays_scenarios: dict,
    ):
        """
        Initializes the RelayClient instance.
        Args:
            plugins (Plugins): A Plugins object managing plugin devices.
            _relay_server_host (str): Hostname or IP address of the relay server.
            _relay_server_port (int): Port number of the relay server.
            _timezone (str, optional): Timezone for scheduling. Defaults to the system timezone.
            _cycle (int): Refresh cycle duration in seconds.
            _cycle_sleeping (int): Sleep duration between cycles in seconds.
            _relays_scenarios (dict): Configuration for relay scenarios.
        """
        super().__init__()
        self.plugins: Plugins = plugins
        self.tz: tzinfo = timezone(_timezone) if _timezone else timezone(str(datetime.now().astimezone().tzname()))
        self.s: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.lock: threading.Lock = threading.Lock()
        self.relay_status_listener: RelayClientStatusListener = RelayClientStatusListener(self.s, self.lock)
        self._relay_status: str = ""
        self._host: str = _relay_server_host
        self._port: int = _relay_server_port
        self._refresh_cycle: int = _cycle
        self._refresh_cycle_sleeping: int = _cycle_sleeping
        self._scenarios_config: dict = _relays_scenarios
        self._pump_status: int = 0
        self.in_between_tasks_delay: timedelta = timedelta(seconds=2)

    def run(self):
        """
        Main execution loop for the RelayClient.
        Connects to the relay server, starts the status listener, and schedules relay operations
        based on the configured scenarios. Handles reconnection on errors.
        """
        try:
            self.connect()
            self.relay_status_listener.start()
            relays_scheduler = sched.scheduler(timefunc=time.monotonic, delayfunc=time.sleep)
            self.set_all_relays(ALL_RELAYS_ID, False)  # DEBUG TODO to remove when official release
            start_time = datetime.now(self.tz).replace(hour=0, minute=0, second=0, microsecond=0)
            while True:
                if self.relay_status_listener.has_error():
                    logging.warning("RelayClientStatusListener error detected, reconnecting...")
                    try:
                        self.connect()
                    except Exception as e:
                        logging.error(f"Reconnection failed: {e}")
                        time.sleep(5)
                        continue
                if relays_scheduler.empty():
                    for current_scenario_relays in self._scenarios_config:
                        start_time, end_time = self.get_times_scenario(current_scenario_relays)
                        self.set_scheduler_relays_beginning(start_time, end_time, relays_scheduler)
                        task_start_time = start_time
                        previous_scenario_relays_times_on = {relay_id: timedelta(0) for relay_id in ALL_RELAYS_ID}
                        for scenario_relays_durations in current_scenario_relays[RELAYS]:
                            current_scenario_relays_times_on = self.get_relays_times_on(start_time, scenario_relays_durations)
                            self.set_scheduler_relays_running(task_start_time, current_scenario_relays_times_on, previous_scenario_relays_times_on, relays_scheduler)
                            task_start_time += RelayTimeParser.get_max_delay_relays_times_on(current_scenario_relays_times_on)
                            previous_scenario_relays_times_on = current_scenario_relays_times_on.copy()
                        self.set_scheduler_relays_finishing(task_start_time, previous_scenario_relays_times_on, relays_scheduler)
                    # -DEBUG----------------------------------------------------------------------
                    current_queue = relays_scheduler.queue
                    for event in current_queue:
                        logging.debug(f"{event.time} P{event.priority} {event.argument}")
                    logging.debug(f'{"":-^120}')
                    # ----------------------------------------------------------------------------
                else:
                    next_job_delay = relays_scheduler.run(blocking=False)
                    self._relay_status = self.relay_status_listener.get_status_str()
                    delay_before_scheduled_task_starts = self.get_delay_scheduled_task(start_time)
                    thread_wait = self._refresh_cycle if delay_before_scheduled_task_starts < timedelta(seconds=self._refresh_cycle_sleeping) else self._refresh_cycle_sleeping
                    # -DEBUG----------------------------------------------------------------------
                    logging.debug(f"Next scheduled event remaining delay: {next_job_delay}")
                    logging.debug(f"RelayClient thread sleeping for {thread_wait} seconds. Next estimated start delay remaining: {delay_before_scheduled_task_starts}. Queue length: {len(relays_scheduler.queue)}")
                    logging.debug(f'{"":-^120}')
                    # ----------------------------------------------------------------------------
                    time.sleep(thread_wait)
        except Exception as e:
            self.set_all_relays(ALL_RELAYS_ID, False)
            self.disconnect()
            self.relay_status_listener.stop()
            logging.error(f"RelayClient error: {e}", exc_info=True)

    def set_scheduler_relays_beginning(self, started_time: datetime, ended_time: datetime, relays_scheduler: scheduler) -> None:
        """
        Schedules the beginning of a relay scenario.
        Args:
            started_time (datetime): The start time of the scenario.
            ended_time (datetime): The end time of the scenario.
            relays_scheduler (scheduler): The scheduler for relay tasks.
        """
        msg_start = f"Scheduled a scenario relays at [{started_time}] with stop time planned at [{ended_time}]"
        logging.warning(msg_start)
        msg_start_scheduled = f"started relays scenario at [{started_time}] with stop time planned at [{ended_time}]"
        task_delay = self.get_delay_scheduled_task(started_time)
        relays_scheduler.enter(task_delay.seconds, 1, logging.warning, (msg_start_scheduled,))

    def set_scheduler_relays_running(
        self,
        started_time: datetime,
        scenario_relays_times_on: dict[int, timedelta],
        previous_scenario_relays_times_on: dict[int, timedelta],
        relays_scheduler: scheduler,
    ) -> None:
        """
        Schedules the running of a relay scenario.
        Args:
            started_time (datetime): The start time of the scenario.
            scenario_relays_times_on (dict[int, timedelta]): The relays and their durations.
            previous_scenario_relays_times_on (dict[int, timedelta]): The previous relays and their durations.
            relays_scheduler (scheduler): The scheduler for relay tasks.
        """
        self.set_relays_scheduling_to_be_switched_off(started_time, scenario_relays_times_on, previous_scenario_relays_times_on, relays_scheduler)
        self.set_relays_scheduling_to_be_switched_on(started_time, scenario_relays_times_on, relays_scheduler)

    def set_scheduler_relays_finishing(self, started_time: datetime, previous_relays_id_times_on: dict[int, timedelta], relays_scheduler: scheduler) -> None:
        """
        Schedules the finishing of a relay scenario.
        Args:
            started_time (datetime): The start time of the scenario.
            previous_relays_id_times_on (dict[int, timedelta]): The previous relays and their durations.
            relays_scheduler (scheduler): The scheduler for relay tasks.
        """
        self.set_relays_scheduling_to_be_switched_off(started_time, {}, previous_relays_id_times_on, relays_scheduler)

    def get_times_scenario(self, scenario: dict) -> tuple[datetime, datetime]:
        """
        Gets the start and end times for a scenario.
        Args:
            scenario (dict): The scenario configuration.
        Returns:
            tuple[datetime, datetime]: The start and end times of the scenario.
        """
        time_init = datetime.now(self.tz).replace(hour=0, minute=0, second=0, microsecond=0)
        started_time = RelayTimeParser.parse_date_time_config(time_init, scenario[START_TIME])
        started_time = started_time if started_time > datetime.now(self.tz) else started_time + timedelta(days=1)
        ended_time = self.get_datetime_end_scenario(started_time, scenario)
        return started_time, ended_time

    def connect(self) -> int:
        """
        Connects to the relay server.
        Returns:
            int: Status code from the server.
        """
        with self.lock:
            try:
                self.s.close()
            except OSError as e:
                logging.debug(f"Error closing socket: {e}")
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.relay_status_listener.update_socket(self.s)
            self.s.connect((self._host, self._port))
            ret = self.s.send(f"{NAME}".encode())
            self.name = self.s.recv(BUFFER_SIZE).decode().replace(f"{NAME}=", "").replace('"', "")
            logging.info(f"Connected to {self.name} [{enum_socket[ret]}]")
            return ret

    def close(self) -> None:
        """
        Closes the connection to the relay server.
        """
        with self.lock:
            self.s.close()
            logging.warning(f"RelayClient {self.name} has closed")

    def disconnect(self) -> None:
        """
        Disconnects from the relay server.
        """
        with self.lock:
            try:
                self.s.shutdown(socket.SHUT_RDWR)
            except OSError as e:
                logging.debug(f"Error shutting down socket: {e}")
            logging.warning(f"RelayClient {self.name} is disconnected")

    @staticmethod
    def get_datetime_end_scenario(started_time: datetime, scenario: dict) -> datetime:
        """
        Gets the end time for a scenario.
        Args:
            started_time (datetime): The start time of the scenario.
            scenario (dict): The scenario configuration.
        Returns:
            datetime: The end time of the scenario.
        """
        total_delta_durations = timedelta(microseconds=0)
        for relays_durations in scenario[RELAYS]:
            relays_durations_values = []
            for relay_id, relay_duration in relays_durations.items():
                end_time_relay_cfg = RelayTimeParser.parse_date_time_delta(started_time, relay_duration)
                delta_duration = end_time_relay_cfg - started_time if end_time_relay_cfg > started_time else timedelta(microseconds=0)
                relays_durations_values.append(delta_duration)
            total_delta_durations += max(relays_durations_values)
        return started_time + total_delta_durations

    @staticmethod
    def get_delay_estimated_scenario(started_time: datetime, scenario: dict) -> timedelta:
        """
        Gets the estimated delay for a scenario.
        Args:
            started_time (datetime): The start time of the scenario.
            scenario (dict): The scenario configuration.
        Returns:
            timedelta: The estimated delay for the scenario.
        """
        total_delta_durations = timedelta(microseconds=0)
        for relays_durations in scenario[RELAYS]:
            for relay_duration in list(relays_durations.values()):
                end_time_relay_cfg = RelayTimeParser.parse_date_time_delta(started_time, relay_duration)
                delta_duration = end_time_relay_cfg - started_time if end_time_relay_cfg > started_time else timedelta(0)
                total_delta_durations += delta_duration
        return total_delta_durations

    def get_delay_scheduled_task(self, start_time: datetime) -> timedelta:
        """
        Gets the delay until a scheduled task starts.
        Args:
            start_time (datetime): The start time of the task.
        Returns:
            timedelta: The delay until the task starts.
        """
        return start_time - datetime.now(self.tz)

    @staticmethod
    def get_relays_times_on(started_time: datetime, relays_durations: dict[int, str]) -> dict[int, timedelta]:
        """
        Gets the times for which relays should be on.
        Args:
            started_time (datetime): The start time of the scenario.
            relays_durations (dict[int, str]): The relays and their durations.
        Returns:
            dict[int, timedelta]: The relays and their times on.
        """
        relays_times_on = {}
        for relay, delta_duration in relays_durations.items():
            end_time_relay_config = RelayTimeParser.parse_date_time_delta(started_time, delta_duration)
            time_duration = end_time_relay_config - started_time if end_time_relay_config > started_time else timedelta(0)
            relays_times_on[relay] = time_duration
        return relays_times_on

    def set_relays_scheduling_to_be_switched_on(self, start_time: datetime, relays_id_times_on: dict[int, timedelta], relays_scheduler: scheduler) -> None:
        """
        Schedules relays to be switched on.
        Args:
            start_time (datetime): The start time for the relays.
            relays_id_times_on (dict[int, timedelta]): The relays and their times on.
            relays_scheduler (scheduler): The scheduler for relay tasks.
        """
        task_delay = self.get_delay_scheduled_task(start_time)
        relays_ids_on = list(relays_id_times_on.keys())
        if relays_ids_on:
            relays_scheduler.enter(task_delay.seconds, 1, self.set_all_relays, (relays_ids_on, True))
            relays_scheduler.enter(task_delay.seconds, 1, self.set_all_plugins, (relays_ids_on, True))

    def set_relays_scheduling_to_be_switched_off(
        self,
        start_time: datetime,
        relays_id_times_on: dict[int, timedelta],
        previous_relays_id_times_on: dict[int, timedelta],
        relays_scheduler: scheduler,
    ) -> None:
        """
        Schedules relays to be switched off.
        Args:
            start_time (datetime): The start time for the relays.
            relays_id_times_on (dict[int, timedelta]): The relays and their times on.
            previous_relays_id_times_on (dict[int, timedelta]): The previous relays and their times on.
            relays_scheduler (scheduler): The scheduler for relay tasks.
        """
        task_delay = self.get_delay_scheduled_task(start_time)
        relays_ids_off = RelayTimeParser.deduce_relays_id_to_set_off(relays_id_times_on, previous_relays_id_times_on)
        if relays_ids_off:
            relays_scheduler.enter(task_delay.seconds, 1, self.set_all_relays, (relays_ids_off, False))
            relays_scheduler.enter(task_delay.seconds, 1, self.set_all_plugins, (relays_ids_off, False))

    def _set_status_lsb(self, relays_id: list[int], on_off: bool) -> list[int]:
        """
        Sets the status of relays in LSB format.
        Args:
            relays_id (list[int]): The IDs of the relays to set.
            on_off (bool): The status to set for the relays.
        Returns:
            list[int]: The status of the relays in LSB format.
        Raises:
            Exception: If an error occurs while setting the status.
        """
        relays_status_msb = self.relay_status_listener.get_status_msb() if self.relay_status_listener.get_status_msb() else ALL_RELAYS_OFF
        try:
            for relay_id in relays_id:
                relays_status_msb[relay_id - 1] = int(on_off)
        except Exception as e:
            raise e
        return relays_status_msb

    def set_all_relays(self, relays_id_8bit_msb: list[int], on_off: bool) -> None:
        """
        Sets the status of all relays.
        Args:
            relays_id_8bit_msb (list[int]): The IDs of the relays to set in MSB format.
            on_off (bool): The status to set for the relays.
        """

        def _get_status_lsb_str(relays_status_msb: list[int]) -> str:
            """
            Gets the status of relays in LSB format as a string.
            Args:
                relays_status_msb (list[int]): The status of the relays in MSB format.
            Returns:
                str: The status of the relays in LSB format as a string.
            Raises:
                Exception: If an error occurs while getting the status.
            """
            try:
                relays_status_lsb = relays_status_msb.copy()
                relays_status_lsb.reverse()  # Back to LSB
            except Exception as e:
                raise e
            return "".join(str(bit) for bit in relays_status_lsb)

        all_relays_id_msb = self._set_status_lsb(relays_id_8bit_msb, on_off)
        str_all_relays_id_lsb = _get_status_lsb_str(all_relays_id_msb)
        with self.lock:
            ret = self.s.send(f"all{str_all_relays_id_lsb}".encode())
        logging.info("Waiting for request being applied")
        start_wait = time.time()
        while self.relay_status_listener.get_status_msb() != all_relays_id_msb:
            if time.time() - start_wait > 5:  # 5-second timeout
                logging.error("Timeout waiting for relay status update")
                break
            logging.debug(f"{self.relay_status_listener.get_status_msb()} != {all_relays_id_msb}")
            sleep(LISTENER_SLEEPING_DELAY)
        switch_status = "enabled" if on_off else "disabled"
        logging.info(f"Relays ALL [{str_all_relays_id_lsb}] {switch_status} [{enum_socket[ret]}]")

    def set_relay_on(self, relay_id: int, time_on: timedelta) -> None:
        """
        Sets a relay on.
        Args:
            relay_id (int): The ID of the relay to set on.
            time_on (timedelta): The duration for which the relay should be on.
        """
        with self.lock:
            ret = self.s.send(f"on{relay_id}".encode())
        logging.info(f"Relay {relay_id} enabled [{enum_socket[ret]}] for {time_on}")

    def set_relay_off(self, relay_id: int) -> None:
        """
        Sets a relay off.
        Args:
            relay_id (int): The ID of the relay to set off.
        """
        with self.lock:
            ret = self.s.send(f"off{relay_id}".encode())
        logging.info(f"Relay {relay_id} disabled [{enum_socket[ret]}]")

    def set_relay_on_timed(self, relay_id: int, time_on: timedelta) -> None:
        """
        Sets a relay on for a specific duration.
        Args:
            relay_id (int): The ID of the relay to set on.
            time_on (timedelta): The duration for which the relay should be on.
        """
        with self.lock:
            ret = self.s.send(f"on{relay_id}:{time_on}".encode())
        logging.info(f"Relay {relay_id} enabled for {time_on} minutes [{enum_socket[ret]}]")

    def set_all_plugins(self, relays_ids: list[int], on_off: bool) -> None:
        """
        Sets the status of all plugins.
        Args:
            relays_ids (list[int]): The IDs of the relays to set.
            on_off (bool): The status to set for the plugins.
        """
        for relay_id in relays_ids:  # Switch off plugin devices mapped to a relay_id
            if on_off:
                if self.plugins.is_trigger_exists(relay_id) and not self.plugins.is_trigger_on(relay_id):
                    self.plugins.set_trigger_toggle(relay_id, True)
            else:
                if self.plugins.is_trigger_exists(relay_id) and self.plugins.is_trigger_on(relay_id):
                    self.plugins.set_trigger_toggle(relay_id, False)

    def is_relay_on(self, relay_id: int) -> bool:
        """
        Checks if a specific relay is on.
        Args:
            relay_id (int): The ID of the relay to check.
        Returns:
            bool: True if the relay is on, False otherwise.
        """
        relays_status_msb = self.relay_status_listener.get_status_msb() if self.relay_status_listener.get_status_msb() else ALL_RELAYS_OFF
        return True if relays_status_msb[relay_id] else False


class RelayClientStatusListener(threading.Thread):
    """
    A listener for relay status updates.
    This class runs in a separate thread and continuously polls the relay server
    for status updates. It handles connection errors and provides methods to
    retrieve the current relay status.
    Args:
        socket_relay_client (socket.socket): The socket connected to the relay server.
        lock (threading.Lock): A lock for thread-safe socket operations.
        listener_sleeping_delay (float, optional): Delay between status polls in seconds.
    """

    def __init__(
        self,
        socket_relay_client: socket.socket,
        lock: threading.Lock,
        listener_sleeping_delay: float = LISTENER_SLEEPING_DELAY,
    ) -> None:
        """
        Initializes the RelayClientStatusListener instance.
        Args:
            socket_relay_client (socket.socket): The socket connected to the relay server.
            lock (threading.Lock): A lock for thread-safe socket operations.
            listener_sleeping_delay (float, optional): Delay between status polls in seconds.
        """
        super().__init__()
        self._event: threading.Event = threading.Event()
        self._event_error: threading.Event = threading.Event()
        self._socket_relay: socket.socket = socket_relay_client
        self._lock: threading.Lock = lock
        self._thread_sleeping_delay: float = listener_sleeping_delay
        self._relay_status_str: str = ""

    def update_socket(self, new_socket: socket.socket):
        self._socket_relay = new_socket
        self._event_error.clear()

    def has_error(self) -> bool:
        return self._event_error.is_set()

    def run(self):
        """
        Main execution loop for the RelayClientStatusListener.
        Continuously polls the relay server for status updates and handles connection errors.
        """
        while not self.is_stopped():
            try:
                self._relay_status_str = self._request_relay_status()
            except (ConnectionResetError, BrokenPipeError, socket.error) as e:
                logging.error(f"RelayClientStatusListener socket error: {e}")
                self._relay_status_str = f"Connection error: {e.args[0]}"
                self._event_error.set()
            time.sleep(self._thread_sleeping_delay)

    def stop(self) -> None:
        """
        Stops the RelayClientStatusListener thread.
        """
        self._event.set()

    def is_stopped(self) -> bool:
        """
        Checks if the RelayClientStatusListener thread is stopped.
        Returns:
            bool: True if the thread is stopped, False otherwise.
        """
        return self._event.is_set()

    def _request_relay_status(self) -> str:
        """
        Requests the current relay status from the server.
        Returns:
            str: The relay status string.
        Raises:
            ConnectionResetError: If the connection is reset.
            BrokenPipeError: If the pipe is broken.
            socket.error: If a socket error occurs.
        """
        socket_response = ""
        with self._lock:
            try:
                request_code = self._socket_relay.send(f"{READ}".encode())
                self.display_status(request_code)
                socket_response = self._socket_relay.recv(BUFFER_SIZE).decode()
            except (ConnectionResetError, BrokenPipeError, socket.error) as e:
                raise e
        if len(socket_response) > 0:
            return socket_response
        return "No message received"

    def get_status_str(self):
        """
        Gets the current relay status string.
        Returns:
            str: The relay status string.
        """
        return self._relay_status_str

    def get_status_msb(self) -> list[int]:
        """
        Gets the current relay status as a list of integers (MSB format).
        Returns:
            list[int]: The relay status in MSB format.
        """
        relays_status_msb = []
        try:
            raw_status_list = re.findall(r"([01]{8})", self._relay_status_str)
            raw_lsb = raw_status_list[len(raw_status_list) - 1] if len(raw_status_list) > 0 else []
            relays_status_lsb = [int(bit) for bit in raw_lsb]
            relays_status_lsb.reverse()
            relays_status_msb = relays_status_lsb.copy()
        except Exception as ie:
            logging.debug(f'get_status MSB {ie} => {"".join(str(bit) for bit in relays_status_msb)}')
        return relays_status_msb

    def is_relay_on(self, relay_id: int) -> bool:
        """
        Checks if a specific relay is on.
        Args:
            relay_id (int): The ID of the relay to check.
        Returns:
            bool: True if the relay is on, False otherwise.
        """
        relays_status_msb = self.get_status_msb()
        return True if len(relays_status_msb) > 0 and relays_status_msb[relay_id - 1] == 1 else False

    def is_relays_on(self, relays_id: list[int]) -> bool:
        """
        Checks if all specified relays are on.
        Args:
            relays_id (list[int]): The IDs of the relays to check.
        Returns:
            bool: True if all relays are on, False otherwise.
        """
        relays_status_msb = self.get_status_msb()
        relays_status = all(True if len(relays_status_msb) > 0 and relays_status_msb[relay_id - 1] == 1 else False for relay_id in relays_id)
        return relays_status

    def is_relay_off(self, relay_id: int) -> bool:
        """
        Checks if a specific relay is off.
        Args:
            relay_id (int): The ID of the relay to check.
        Returns:
            bool: True if the relay is off, False otherwise.
        """
        relays_status_msb = self.get_status_msb()
        return True if len(relays_status_msb) > 0 and relays_status_msb[relay_id - 1] == 0 else False

    def is_relays_off(self, relays_id_times_on: dict[int, timedelta]) -> bool:
        """
        Checks if all specified relays are off.
        Args:
            relays_id_times_on (dict[int, timedelta]): The relays and their times on.
        Returns:
            bool: True if all relays are off, False otherwise.
        """
        relays_status_msb = self.get_status_msb()
        relays_status = all(True if len(relays_status_msb) > 0 and relays_status_msb[relay_id - 1] == 0 else False for relay_id, time_on in relays_id_times_on.items())
        logging.info(f"is relays off {list(relays_id_times_on.keys())} [{relays_status}]")
        return relays_status

    def is_all_relays_off(self) -> bool:
        """
        Checks if all relays are off.
        Returns:
            bool: True if all relays are off, False otherwise.
        """
        all_relays_off = all(not relay_id for relay_id in self.get_status_msb())
        logging.info(f"is_all_relays_off {self.get_status_msb()} => {all_relays_off}")
        return all_relays_off

    def display_status(self, return_code=None) -> None:
        """
        Displays the current relay status.
        Args:
            return_code (int, optional): The return code from the server.
        """
        logging.debug(f"{self.name} relays status : [{self._relay_status_str}] => [{enum_socket.get(return_code, '')}]")


class RelaysUtils:
    """
    Utility class for relay operations.
    This class provides static methods for logging and process management.
    """

    @staticmethod
    def convert_log_level(level="error"):
        """
        Converts a log level string to a logging level constant.
        Args:
            level (str, optional): The log level string. Defaults to "error".
        Returns:
            int: The logging level constant.
        """
        levels = {"debug": logging.DEBUG, "info": logging.INFO, "notice": logging.WARNING, "warning": logging.WARNING, "error": logging.ERROR, "critical": logging.CRITICAL, "none": logging.CRITICAL}
        return levels.get(level, logging.CRITICAL)

    @staticmethod
    def set_log_level(level="warning", file_logging="relays.log"):
        """
        Sets the log level and configures file logging.
        Args:
            level (str, optional): The log level string. Defaults to "warning".
            file_logging (str, optional): The file to log to. Defaults to "relays.log".
        """
        log_format = "[%(asctime)-15s][%(levelname)s] : %(message)s"
        date_format = "%Y-%m-%d %H:%M:%S"
        logging.basicConfig(level=RelaysUtils.convert_log_level(level), format=log_format, datefmt=date_format)
        if file_logging:
            logger = logging.getLogger()
            file_handler = logging.FileHandler(filename=file_logging, mode="a")
            formatter = logging.Formatter(log_format)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logger.setLevel(level.upper())

    @staticmethod
    def write_pid(path: Path):
        """
        Writes the process ID to a file.
        Args:
            path (str): The path to the file to write the PID to.
        """
        pid = str(os.getpid())
        logging.info(f"Writing PID {pid} to {path.as_posix()}")
        open(path, "w").write(f"{pid}\n")

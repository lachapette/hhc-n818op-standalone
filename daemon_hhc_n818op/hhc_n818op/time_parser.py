"""
RelayTimeParser: Helper class for parsing time configurations in relay scenarios.
"""

from __future__ import annotations

# Standard Library
import logging
import re
from datetime import datetime, timedelta

# HHC_N818OP Client daemonized
from daemon_hhc_n818op.hhc_n818op import ALL_RELAYS_ID, CFG_TIME_PATTERN, DATE, MILLISECONDS, RELAYS, TIME


class RelayTimeParser:
    """Helper class for parsing date/time configurations from relay scenarios."""

    @staticmethod
    def parse_date_time_config(base_date_time: datetime, date_time_to_parse: str) -> datetime:
        """
        Parses a date and time configuration string.
        Args:
            base_date_time: The base date and time to use.
            date_time_to_parse: The date and time string to parse.
        Returns:
            The parsed date and time.
        """
        cfg_start_time = None
        try:
            cfg_start_time = re.search(CFG_TIME_PATTERN, date_time_to_parse)
        except TypeError:
            logging.error(f"Configuration error with {date_time_to_parse} into section {RELAYS}\n" f"{RELAYS} shall follow possible Date Time formats:\n" f"- %d/%m/%y %H:%M:%S.%f\n- %H:%M:%S.%f\n- %f\n- %H:%M:%S\n- %d/%m/%y\n- %d/%m/%y %H:%M:%S")
        if cfg_start_time is None:
            return base_date_time
        str_date = cfg_start_time.group(DATE)
        if str_date is not None:
            day, month, year = str_date.split("/")
            base_date_time = base_date_time.replace(day=int(day), month=int(month), year=int(year))
        str_time = cfg_start_time.group(TIME)
        if str_time is not None:
            hour, minute, second = str_time.split(":")
            base_date_time = base_date_time.replace(hour=int(hour), minute=int(minute), second=int(second))
        str_milliseconds = cfg_start_time.group(MILLISECONDS)
        if str_milliseconds is not None:
            base_date_time = base_date_time.replace(microsecond=int(str_milliseconds))
        return base_date_time

    @staticmethod
    def parse_date_time_delta(base_date_time: datetime, date_time_to_parse: str) -> datetime:
        """
        Parses a date and time delta configuration string.
        Args:
            base_date_time: The base date and time to use.
            date_time_to_parse: The date and time delta string to parse.
        Returns:
            The parsed date and time with the delta applied.
        """
        cfg_start_time = None
        try:
            cfg_start_time = re.search(CFG_TIME_PATTERN, date_time_to_parse)
        except TypeError:
            logging.error(f"Configuration error with {date_time_to_parse} into section {RELAYS}\n" f"{RELAYS} shall follow possible Date Time formats:\n" f"- %d/%m/%y %H:%M:%S.%f\n- %H:%M:%S.%f\n- %f\n- %H:%M:%S\n- %d/%m/%y\n- %d/%m/%y %H:%M:%S")
        if cfg_start_time is None:
            return base_date_time
        str_date = cfg_start_time.group(DATE)
        if str_date is not None:
            day, month, year = str_date.split("/")
            base_date_time = base_date_time + timedelta(days=int(day))
        str_time = cfg_start_time.group(TIME)
        if str_time is not None:
            hour, minute, second = str_time.split(":")
            base_date_time = base_date_time + timedelta(hours=int(hour), minutes=int(minute), seconds=int(second))
        str_milliseconds = cfg_start_time.group(MILLISECONDS)
        if str_milliseconds is not None:
            base_date_time = base_date_time + timedelta(microseconds=int(str_milliseconds))
        return base_date_time

    @staticmethod
    def get_max_delay_relays_times_on(relays_times_on: dict[int, timedelta]) -> timedelta:
        """
        Gets the maximum delay for relays to be on.
        Args:
            relays_times_on: The relays and their times on.
        Returns:
            The maximum delay for relays to be on.
        """
        max_delay_relays_times_on: timedelta = timedelta(0)
        for relay_id, delta_duration in relays_times_on.items():
            max_delay_relays_times_on = max(max_delay_relays_times_on, delta_duration)
        return max_delay_relays_times_on

    @staticmethod
    def deduce_relays_id_to_set_off(relays_id_times_on: dict[int, timedelta], previous_relays_id_times_on: dict[int, timedelta]) -> list[int]:
        """
        Deduces which relays should be switched off.
        Args:
            relays_id_times_on: The relays and their times on.
            previous_relays_id_times_on: The previous relays and their times on.
        Returns:
            The IDs of the relays to switch off.
        """
        relays_ids_off: list[int] = []
        for relay_id in ALL_RELAYS_ID:
            if relay_id in previous_relays_id_times_on and relay_id not in relays_id_times_on:
                relays_ids_off.append(relay_id)
        return relays_ids_off

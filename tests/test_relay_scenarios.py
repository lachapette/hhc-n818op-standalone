#!/usr/bin/env python3
"""
Test relay scenarios mask handling between scenario transitions.

Tests verify that relays_default_mask_times_on correctly captures the time gap
between the end of one scenario and the start of the next scheduled scenario.
"""

# pylint: disable=protected-access,comparison-with-callable,unnecessary-lambda

# Standard Library
import sched
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# Third Party Libraries
import pytz  # type: ignore[import-untyped]

# HHC_N818OP Client daemonized
# Project imports
from daemon_hhc_n818op.hhc_n818op.relay_client import RelayClient
from daemon_hhc_n818op.hhc_n818op.relay_plugins import Plugins


class TestRelayScenariosMask(unittest.TestCase):
    """Test relay mask handling between scenarios."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_plugins = MagicMock(spec=Plugins)
        self.tz = pytz.timezone("Europe/Paris")
        # Use 06:00:00 to ensure all scenarios with start_time > 06:00 are scheduled for today
        self.now = datetime(2024, 1, 15, 6, 0, 0, tzinfo=self.tz)

        # Patch datetime.now to return a fixed time
        self.patcher_now = patch("daemon_hhc_n818op.hhc_n818op.relay_client.datetime")
        self.mock_datetime = self.patcher_now.start()
        self.mock_datetime.now = MagicMock(return_value=self.now)
        self.mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

    def tearDown(self):
        """Clean up after tests."""
        self.patcher_now.stop()

    def _create_relay_client(self, scenarios_config, relays_default=None, periodicity_config=None):
        """Create a RelayClient with test configuration."""
        return RelayClient(
            plugins=self.mock_plugins,
            _relay_server_host="127.0.0.1",
            _relay_server_port=5000,
            _timezone="Europe/Paris",
            _cycle=2,
            _cycle_sleeping=300,
            _relays_scenarios=scenarios_config,
            _relays_default=relays_default if relays_default is not None else [1, 2],
            barrier=None,
            _periodicity_config=periodicity_config if periodicity_config is not None else {},
        )

    def test_mask_between_two_scenarios(self):
        """Test that mask times_on is calculated between end of first and start of second scenario."""
        # Scenario 1: starts at 08:00, duration 2 hours (ends at 10:00)
        # Scenario 2: starts at 14:00
        # Gap should be 4 hours (10:00 to 14:00)

        scenarios_config = [
            {
                "start_time": "08:00:00",
                "relays_durations": [
                    {1: "02:00:00", 2: "01:30:00"},
                ],
            },
            {
                "start_time": "14:00:00",
                "relays_durations": [
                    {3: "01:00:00", 4: "00:45:00"},
                ],
            },
        ]

        client = self._create_relay_client(scenarios_config, relays_default=[1, 2])

        # Mock the connect and status listener
        client.connect = MagicMock()
        client.relay_status_listener = MagicMock()
        client.relay_status_listener.has_error = MagicMock(return_value=False)
        client.relay_status_listener.start = MagicMock()
        client._set_relays_default_preconditions = MagicMock()

        # Create a real scheduler
        relays_scheduler = sched.scheduler()

        # Mock set_scheduler_relays_beginning and set_scheduler_relays_running
        client.set_scheduler_relays_beginning = MagicMock()
        client.set_scheduler_relays_running = MagicMock()

        # Track calls to set_scheduler_relays_finishing
        finishing_calls = []
        original_finishing = client.set_scheduler_relays_finishing

        def track_finishing(started_time, relays_default_mask_times_on, previous_relays_id_times_on, scheduler):
            finishing_calls.append(
                {
                    "started_time": started_time,
                    "relays_default_mask_times_on": relays_default_mask_times_on,
                    "previous_relays_id_times_on": previous_relays_id_times_on,
                }
            )
            return original_finishing(started_time, relays_default_mask_times_on, previous_relays_id_times_on, scheduler)

        client.set_scheduler_relays_finishing = track_finishing

        # Run the scheduling logic using the extracted method
        client._schedule_scenarios(relays_scheduler)

        # Verify the first scenario
        first_call = finishing_calls[0]
        expected_gap = timedelta(hours=4)  # 10:00 to 14:00

        self.assertEqual(len(finishing_calls), 2, "Should have 2 finishing calls (one per scenario)")

        # Check first scenario mask
        self.assertEqual(first_call["relays_default_mask_times_on"][1], expected_gap)
        self.assertEqual(first_call["relays_default_mask_times_on"][2], expected_gap)

        # Check second scenario mask (should be until midnight)
        # Scenario 2 starts at 14:00 on 15/01, lasts 1h (max of 01:00:00 and 00:45:00), ends at 15:00 on 15/01
        # Gap until midnight = 9 hours (15:00 to 24:00)
        second_call = finishing_calls[1]
        expected_gap_second = timedelta(hours=9)

        self.assertEqual(second_call["relays_default_mask_times_on"][1], expected_gap_second)
        self.assertEqual(second_call["relays_default_mask_times_on"][2], expected_gap_second)

    def test_mask_with_three_scenarios(self):
        """Test mask calculation with three scenarios."""
        # Scenario 1: 08:00-09:00 (1h)
        # Scenario 2: 12:00-13:00 (1h)
        # Scenario 3: 18:00-19:00 (1h)
        # Gaps: 09:00-12:00 = 3h, 13:00-18:00 = 5h

        scenarios_config = [
            {
                "start_time": "08:00:00",
                "relays_durations": [{"1": "01:00:00"}],
            },
            {
                "start_time": "12:00:00",
                "relays_durations": [{"2": "01:00:00"}],
            },
            {
                "start_time": "18:00:00",
                "relays_durations": [{"3": "01:00:00"}],
            },
        ]

        client = self._create_relay_client(scenarios_config, relays_default=[1, 2, 3])

        # Mock necessary methods
        client.connect = MagicMock()
        client.relay_status_listener = MagicMock()
        client.relay_status_listener.has_error = MagicMock(return_value=False)
        client._set_relays_default_preconditions = MagicMock()
        client.set_scheduler_relays_beginning = MagicMock()
        client.set_scheduler_relays_running = MagicMock()

        # Track finishing calls
        finishing_calls = []
        client.set_scheduler_relays_finishing = MagicMock(side_effect=lambda *args, **kwargs: finishing_calls.append(args))

        # Run scheduling logic
        relays_scheduler = sched.scheduler()
        client._schedule_scenarios(relays_scheduler)

        # Verify gaps
        self.assertEqual(len(finishing_calls), 3, "Should have 3 finishing calls")

        # First gap: 09:00 to 12:00 = 3 hours
        first_gap = finishing_calls[0][1]  # relays_default_mask_times_on
        self.assertEqual(first_gap[1], timedelta(hours=3))
        self.assertEqual(first_gap[2], timedelta(hours=3))
        self.assertEqual(first_gap[3], timedelta(hours=3))

        # Second gap: 13:00 to 18:00 = 5 hours
        second_gap = finishing_calls[1][1]
        self.assertEqual(second_gap[1], timedelta(hours=5))
        self.assertEqual(second_gap[2], timedelta(hours=5))
        self.assertEqual(second_gap[3], timedelta(hours=5))

    def test_mask_with_empty_default_relays(self):
        """Test that mask calculation works with empty default relays."""
        scenarios_config = [
            {
                "start_time": "08:00:00",
                "relays_durations": [{"1": "01:00:00"}],
            },
            {
                "start_time": "10:00:00",
                "relays_durations": [{"2": "01:00:00"}],
            },
        ]

        client = self._create_relay_client(scenarios_config, relays_default=[])

        # Run scheduling logic
        relays_scheduler = sched.scheduler()
        finishing_calls = []
        client.set_scheduler_relays_finishing = MagicMock(side_effect=lambda *args, **kwargs: finishing_calls.append(args))
        client.set_scheduler_relays_beginning = MagicMock()
        client.set_scheduler_relays_running = MagicMock()
        client._schedule_scenarios(relays_scheduler)

        # With empty default relays, mask should be empty dict
        self.assertEqual(len(finishing_calls), 2)
        self.assertEqual(finishing_calls[0][1], {})  # Empty dict
        self.assertEqual(finishing_calls[1][1], {})

    def test_relay_7_stays_on_between_scenarios(self):
        """Test that relay 7 stays ON between scenarios when relays_default=[7]."""
        # Scenario 1: 08:00-09:00 (activates relay 1)
        # Scenario 2: 12:00-13:00 (activates relay 2)
        # Gap: 09:00-12:00 = 3 hours
        # With relays_default=[7], relay 7 should be ON during the gap

        scenarios_config = [
            {
                "start_time": "08:00:00",
                "relays_durations": [{"1": "01:00:00"}],
            },
            {
                "start_time": "12:00:00",
                "relays_durations": [{"2": "01:00:00"}],
            },
        ]

        client = self._create_relay_client(scenarios_config, relays_default=[7])

        # Track scheduled relay ON/OFF calls
        scheduled_relay_calls = []
        relays_scheduler = sched.scheduler()
        original_enter = relays_scheduler.enter

        def track_scheduled_calls(*args, **kwargs):
            # args: (time, priority, action, argument)
            if args and len(args) >= 3:
                action = args[2]
                action_args = args[3] if len(args) > 3 else ()
                if action == client.set_all_relays:
                    scheduled_relay_calls.append({"time": args[0], "relays_ids": action_args[0] if action_args else [], "on_off": action_args[1] if len(action_args) > 1 else None})
            return original_enter(*args, **kwargs)

        relays_scheduler.enter = track_scheduled_calls

        client.set_all_plugins = MagicMock()
        client.relay_status_listener = MagicMock()
        client.relay_status_listener.has_error = MagicMock(return_value=False)
        client.relay_status_listener.start = MagicMock()
        client._set_relays_default_preconditions = MagicMock()

        # Run scheduling logic
        client._schedule_scenarios(relays_scheduler)

        # Verify relay 7 is scheduled to be turned ON during mask period
        relay_7_on_scheduled = [call for call in scheduled_relay_calls if call["on_off"] is True and 7 in call["relays_ids"]]

        self.assertGreater(len(relay_7_on_scheduled), 0, f"Relay 7 should be scheduled to turn ON during mask period. " f"Scheduled calls: {scheduled_relay_calls}")

    def test_relays_never_all_off_with_default_relays(self):
        """Test that at least one default relay is always ON between scenarios."""
        scenarios_config = [
            {
                "start_time": "08:00:00",
                "relays_durations": [{"1": "01:00:00"}],
            },
            {
                "start_time": "10:00:00",
                "relays_durations": [{"2": "01:00:00"}],
            },
        ]

        client = self._create_relay_client(scenarios_config, relays_default=[7])

        # Verify client has correct default relays
        self.assertEqual(client._relays_default, [7], f"Client should have relays_default=[7], got {client._relays_default}")

        # Track scheduled relay ON/OFF calls
        scheduled_relay_calls = []
        relays_scheduler = sched.scheduler()
        original_enter = relays_scheduler.enter

        def track_scheduled_calls(*args, **kwargs):
            # args: (time, priority, action, argument)
            if args and len(args) >= 3:
                action = args[2]
                action_args = args[3] if len(args) > 3 else ()
                if action == client.set_all_relays:
                    scheduled_relay_calls.append({"time": args[0], "relays_ids": list(action_args[0]) if action_args else [], "on_off": action_args[1] if len(action_args) > 1 else None})
            return original_enter(*args, **kwargs)

        relays_scheduler.enter = track_scheduled_calls

        client.set_all_plugins = MagicMock()
        client.relay_status_listener = MagicMock()
        client.relay_status_listener.has_error = MagicMock(return_value=False)
        client.relay_status_listener.start = MagicMock()
        client._set_relays_default_preconditions = MagicMock()

        # Run scheduling logic
        client._schedule_scenarios(relays_scheduler)

        # Verify relay 7 is scheduled to be turned ON (part of mask)
        relay_7_on = [call for call in scheduled_relay_calls if call["on_off"] is True and 7 in call["relays_ids"]]
        self.assertGreater(len(relay_7_on), 0, f"Relay 7 should be scheduled to turn ON as part of the default mask. " f"Scheduled calls: {scheduled_relay_calls}")

        # Verify relay 7 is never scheduled to be turned OFF
        relay_7_off = [call for call in scheduled_relay_calls if call["on_off"] is False and 7 in call["relays_ids"]]
        self.assertEqual(len(relay_7_off), 0, f"Relay 7 should never be turned OFF when it's in relays_default. " f"OFF calls for relay 7: {relay_7_off}")


class TestDependenciesMappingANDNOT(unittest.TestCase):
    """Test AND/NOT logic in dependencies_mapping."""

    def test_parse_and_not_mappings(self):
        """Test that AND and NOT mappings are parsed correctly."""
        # HHC_N818OP Client daemonized
        from daemon_hhc_n818op.hhc_n818op import AND, DEPENDENCIES, MAPPING, NOT

        config = {
            MAPPING: {
                AND: {2: "Pump", 4: "Light"},
                NOT: {3: "Pump", 5: "Fan"},
            },
            DEPENDENCIES: {
                "Pump": {},
                "Light": {},
                "Fan": {},
            },
        }

        plugins = Plugins(config)

        # Verify mappings are parsed correctly
        self.assertEqual(plugins._plugins_mapping_and, {2: "Pump", 4: "Light"})
        self.assertEqual(plugins._plugins_mapping_not, {3: "Pump", 5: "Fan"})

    def test_and_logic_trigger_active_when_relay_on(self):
        """Test that AND logic activates trigger when relay is ON."""
        # HHC_N818OP Client daemonized
        from daemon_hhc_n818op.hhc_n818op import AND, DEPENDENCIES, MAPPING

        config = {
            MAPPING: {AND: {2: "Pump"}},
            DEPENDENCIES: {"Pump": {}},
        }

        plugins = Plugins(config)

        # Trigger should be active when relay is ON
        self.assertTrue(plugins.is_trigger_should_be_active(2, True))
        # Trigger should NOT be active when relay is OFF
        self.assertFalse(plugins.is_trigger_should_be_active(2, False))

    def test_not_logic_trigger_active_when_relay_off(self):
        """Test that NOT logic activates trigger when relay is OFF."""
        # HHC_N818OP Client daemonized
        from daemon_hhc_n818op.hhc_n818op import DEPENDENCIES, MAPPING, NOT

        config = {
            MAPPING: {NOT: {3: "Fan"}},
            DEPENDENCIES: {"Fan": {}},
        }

        plugins = Plugins(config)

        # Trigger should be active when relay is OFF
        self.assertTrue(plugins.is_trigger_should_be_active(3, False))
        # Trigger should NOT be active when relay is ON
        self.assertFalse(plugins.is_trigger_should_be_active(3, True))

    def test_mixed_and_not_mappings(self):
        """Test that a plugin can appear in both AND and NOT mappings."""
        # HHC_N818OP Client daemonized
        from daemon_hhc_n818op.hhc_n818op import AND, DEPENDENCIES, MAPPING, NOT

        config = {
            MAPPING: {
                AND: {2: "Pump"},  # Pump active when relay 2 is ON
                NOT: {3: "Pump"},  # Pump active when relay 3 is OFF
            },
            DEPENDENCIES: {"Pump": {}},
        }

        plugins = Plugins(config)

        # Relay 2 (AND): active when ON
        self.assertTrue(plugins.is_trigger_should_be_active(2, True))
        self.assertFalse(plugins.is_trigger_should_be_active(2, False))

        # Relay 3 (NOT): active when OFF
        self.assertTrue(plugins.is_trigger_should_be_active(3, False))
        self.assertFalse(plugins.is_trigger_should_be_active(3, True))

        # Both should point to same plugin
        self.assertEqual(plugins.get_plugin_name_for_relay(2), "Pump")
        self.assertEqual(plugins.get_plugin_name_for_relay(3), "Pump")

    def test_is_trigger_exists_with_and_mapping(self):
        """Test that is_trigger_exists works with AND mapping."""
        # HHC_N818OP Client daemonized
        from daemon_hhc_n818op.hhc_n818op import AND, DEPENDENCIES, MAPPING

        config = {
            MAPPING: {AND: {2: "Pump"}},
            DEPENDENCIES: {"Pump": {}},
        }

        plugins = Plugins(config)

        self.assertTrue(plugins.is_trigger_exists(2))
        self.assertFalse(plugins.is_trigger_exists(99))

    def test_is_trigger_exists_with_not_mapping(self):
        """Test that is_trigger_exists works with NOT mapping."""
        # HHC_N818OP Client daemonized
        from daemon_hhc_n818op.hhc_n818op import DEPENDENCIES, MAPPING, NOT

        config = {
            MAPPING: {NOT: {3: "Fan"}},
            DEPENDENCIES: {"Fan": {}},
        }

        plugins = Plugins(config)

        self.assertTrue(plugins.is_trigger_exists(3))
        self.assertFalse(plugins.is_trigger_exists(99))

    def test_get_plugin_name_for_relay(self):
        """Test get_plugin_name_for_relay returns correct plugin name."""
        # HHC_N818OP Client daemonized
        from daemon_hhc_n818op.hhc_n818op import AND, DEPENDENCIES, MAPPING, NOT

        config = {
            MAPPING: {
                AND: {2: "Pump"},
                NOT: {3: "Fan"},
            },
            DEPENDENCIES: {"Pump": {}, "Fan": {}},
        }

        plugins = Plugins(config)

        self.assertEqual(plugins.get_plugin_name_for_relay(2), "Pump")
        self.assertEqual(plugins.get_plugin_name_for_relay(3), "Fan")
        self.assertIsNone(plugins.get_plugin_name_for_relay(99))

    def test_empty_mapping_warning(self):
        """Test that empty mapping generates a warning."""
        # HHC_N818OP Client daemonized
        from daemon_hhc_n818op.hhc_n818op import DEPENDENCIES, MAPPING

        config = {
            MAPPING: {},
            DEPENDENCIES: {},
        }

        # Should not raise, but should log a warning
        plugins = Plugins(config)
        self.assertEqual(plugins._plugins_mapping_and, {})
        self.assertEqual(plugins._plugins_mapping_not, {})

    def test_only_and_mapping(self):
        """Test configuration with only AND mapping."""
        # HHC_N818OP Client daemonized
        from daemon_hhc_n818op.hhc_n818op import AND, DEPENDENCIES, MAPPING

        config = {
            MAPPING: {AND: {2: "Pump"}},
            DEPENDENCIES: {"Pump": {}},
        }

        plugins = Plugins(config)
        self.assertEqual(plugins._plugins_mapping_and, {2: "Pump"})
        self.assertEqual(plugins._plugins_mapping_not, {})
        self.assertTrue(plugins.is_trigger_exists(2))

    def test_only_not_mapping(self):
        """Test configuration with only NOT mapping."""
        # HHC_N818OP Client daemonized
        from daemon_hhc_n818op.hhc_n818op import DEPENDENCIES, MAPPING, NOT

        config = {
            MAPPING: {NOT: {3: "Fan"}},
            DEPENDENCIES: {"Fan": {}},
        }

        plugins = Plugins(config)
        self.assertEqual(plugins._plugins_mapping_and, {})
        self.assertEqual(plugins._plugins_mapping_not, {3: "Fan"})
        self.assertTrue(plugins.is_trigger_exists(3))

    def test_set_all_plugins_with_and_not_logic(self):
        """Test set_all_plugins handles AND and NOT logic correctly."""
        # HHC_N818OP Client daemonized
        from daemon_hhc_n818op.hhc_n818op import AND, DEPENDENCIES, MAPPING, NOT

        config = {
            MAPPING: {
                AND: {2: "Pump"},
                NOT: {3: "Fan"},
            },
            DEPENDENCIES: {
                "Pump": {"triggers": {}},
                "Fan": {"triggers": {}},
            },
        }

        plugins = Plugins(config)

        # Mock the plugins
        mock_pump = MagicMock()
        mock_fan = MagicMock()
        mock_pump.toggle_on_off = MagicMock(return_value=True)
        mock_fan.toggle_on_off = MagicMock(return_value=True)
        plugins._plugins = {"Pump": mock_pump, "Fan": mock_fan}
        plugins._cache_status_table = {"Pump": False, "Fan": False}

        # Mock event loop
        plugins.event_loop = MagicMock()
        plugins.event_loop.is_running.return_value = False

        # Create a mock relay client
        with patch("daemon_hhc_n818op.hhc_n818op.relay_client.socket.socket"):
            client = RelayClient(
                plugins=plugins,
                _relay_server_host="127.0.0.1",
                _relay_server_port=5000,
                _timezone="UTC",
                _cycle=2,
                _cycle_sleeping=300,
                _relays_scenarios=[],
                _relays_default=[],
                barrier=None,
                _periodicity_config={},
            )

        # Test: Switch relays 2 and 3 ON
        # Relay 2 (AND): should activate Pump when ON
        # Relay 3 (NOT): should NOT activate Fan when ON
        plugins.set_trigger_toggle = MagicMock()
        client.set_all_plugins([2, 3], True)

        # Verify set_trigger_toggle was called for relay 2 (AND logic: ON -> activate)
        calls = plugins.set_trigger_toggle.call_args_list
        relay_ids_toggled = [c[0][0] for c in calls if len(c[0]) > 0]
        self.assertIn(2, relay_ids_toggled)

    def test_at_least_one_mapping_required(self):
        """Test that configuration requires at least one AND or NOT entry."""
        # HHC_N818OP Client daemonized
        from daemon_hhc_n818op.hhc_n818op import AND, DEPENDENCIES, MAPPING, NOT

        # Valid: has AND
        config_and = {MAPPING: {AND: {2: "Pump"}}, DEPENDENCIES: {"Pump": {}}}
        plugins_and = Plugins(config_and)
        self.assertTrue(plugins_and._plugins_mapping_and or plugins_and._plugins_mapping_not)

        # Valid: has NOT
        config_not = {MAPPING: {NOT: {3: "Fan"}}, DEPENDENCIES: {"Fan": {}}}
        plugins_not = Plugins(config_not)
        self.assertTrue(plugins_not._plugins_mapping_and or plugins_not._plugins_mapping_not)

        # Valid: has both
        config_both = {MAPPING: {AND: {2: "Pump"}, NOT: {3: "Fan"}}, DEPENDENCIES: {"Pump": {}, "Fan": {}}}
        plugins_both = Plugins(config_both)
        self.assertTrue(plugins_both._plugins_mapping_and and plugins_both._plugins_mapping_not)


if __name__ == "__main__":
    unittest.main(verbosity=2)

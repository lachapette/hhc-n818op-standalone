# Standard Library
import asyncio
import importlib
import inspect
import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Coroutine

# HHC_N818OP Client daemonized
from daemon_hhc_n818op import HOST, PORT
from daemon_hhc_n818op.hhc_n818op import DEPENDENCIES, DEVICE_UNKNOWN, HTTP, MAPPING, MQTT, PLUGIN_CLASS, PLUGIN_MODULE, TRIGGERS


class PluginMQTT(ABC):
    """
    Abstract base class for MQTT plugins.
    This class defines the interface for MQTT-based plugin devices.
    """

    def __init__(self):
        """
        Initializes the PluginMQTT instance.
        """
        self.manager = None

    @abstractmethod
    async def get_manager_mqtt(self) -> object:
        """
        Gets the MQTT manager for the plugin.
        Returns:
            object: The MQTT manager.
        """

    @abstractmethod
    async def disconnect(self, **kwargs) -> object:
        """
        Disconnects the plugin.
        Returns:
            object: The result of the disconnection.
        """

    @abstractmethod
    async def status(self, **kwargs) -> object:
        """
        Gets the status of the plugin.
        Returns:
            object: The status of the plugin.
        """

    @abstractmethod
    async def switch_on(self, **kwargs) -> object:
        """
        Switches the plugin on.
        Returns:
            object: The result of the operation.
        """

    @abstractmethod
    async def switch_off(self, **kwargs) -> object:
        """
        Switches the plugin off.
        Returns:
            object: The result of the operation.
        """

    @abstractmethod
    async def toggle_on_off(self, **kwargs) -> object:
        """
        Toggles the plugin on or off.
        Returns:
            object: The result of the operation.
        """


class PluginHTTP(ABC):
    """
    Abstract base class for HTTP plugins.
    This class defines the interface for HTTP-based plugin devices.
    """

    def __init__(self):
        """
        Initializes the PluginHTTP instance.
        """
        self.manager = None

    @abstractmethod
    async def get_manager_http(self) -> object:
        """
        Gets the HTTP manager for the plugin.
        Returns:
            object: The HTTP manager.
        """

    @abstractmethod
    async def disconnect(self, **kwargs) -> object:
        """
        Disconnects the plugin.
        Returns:
            object: The result of the disconnection.
        """

    @abstractmethod
    async def status(self, **kwargs) -> object:
        """
        Gets the status of the plugin.
        Returns:
            object: The status of the plugin.
        """

    @abstractmethod
    async def switch_on(self, **kwargs) -> object:
        """
        Switches the plugin on.
        Returns:
            object: The result of the operation.
        """

    @abstractmethod
    async def switch_off(self, **kwargs) -> object:
        """
        Switches the plugin off.
        Returns:
            object: The result of the operation.
        """

    @abstractmethod
    async def toggle_on_off(self, **kwargs) -> object:
        """
        Toggles the plugin on or off.
        Returns:
            object: The result of the operation.
        """


class Plugins(threading.Thread):
    """
    Manages plugin devices and their interactions with relays.
    This class initializes and manages plugin devices, maps them to relays,
    and provides methods to control plugin devices based on relay status.
    Args:
        relays_plugins_config (dict): Configuration for relays and plugins.
        barrier (threading.Barrier, optional): Barrier to synchronize with relay precondition mask initialization.
    """

    def __init__(self, relays_plugins_config: dict, barrier: threading.Barrier | None = None) -> None:
        """
        Initializes the Plugins instance.
        Args:
            relays_plugins_config (dict): Configuration for relays and plugins.
            barrier (threading.Barrier, optional): Barrier for synchronization. Defaults to None.
        """
        super().__init__()
        self._plugins_mapping: dict = relays_plugins_config.get(MAPPING, {})
        self._dependencies: dict = relays_plugins_config.get(DEPENDENCIES, {})
        self._relays_plugins_config: dict = relays_plugins_config
        self._plugins: dict[str, PluginMQTT | PluginHTTP] = {}
        self._cache_status_table: dict[str, bool] = {}
        self.event_loop: asyncio.AbstractEventLoop | None = None
        self._initialized: threading.Event = threading.Event()
        self._barrier: threading.Barrier | None = barrier

    def run(self):
        """
        Main execution loop for the Plugins thread.
        Initializes plugin managers, sets up the cache status table, and starts
        the event loop for async tasks.
        """
        try:
            # Wait for the barrier signal that relay precondition mask is applied
            if self._barrier is not None:
                logging.info("Plugins thread waiting for relay precondition mask barrier")
                self._barrier.wait()
                logging.info("Plugins thread received barrier signal - proceeding with initialization")

            self.init_plugins_async_tasks()
            self._plugins_managers_init(self._relays_plugins_config)
            self._cache_status_table = self._initialize_cache_status_table(self._relays_plugins_config)
            self._initialized.set()
            self.event_loop.run_forever()
        except Exception:
            self._initialized.set()
            raise

    def _run_async(self, coroutine_plugin: Coroutine):
        """
        Runs an async coroutine in the event loop.
        Args:
            coroutine_plugin (Coroutine): The coroutine to run.
        Returns:
            The result of the coroutine.
        Raises:
            RuntimeError: If the event loop is not initialized.
        """
        if inspect.isawaitable(coroutine_plugin):
            if self.event_loop is None:
                raise RuntimeError("Plugins event loop is not initialized")
            if self.event_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(coroutine_plugin, self.event_loop)  # pylint: disable=no-member
                return future.result()
            return self.event_loop.run_until_complete(coroutine_plugin)
        return coroutine_plugin

    def init_plugins_async_tasks(self) -> None:
        """
        Initializes the async event loop for plugin tasks.
        """
        self.event_loop = asyncio.new_event_loop()  # pylint: disable=no-member
        asyncio.set_event_loop(self.event_loop)  # pylint: disable=no-member

    def wait_until_ready(self, timeout: float | None = None) -> bool:
        """
        Waits until the Plugins thread is ready.
        Args:
            timeout (float, optional): Maximum time to wait in seconds.
        Returns:
            bool: True if the thread is ready, False if the timeout was reached.
        """
        return self._initialized.wait(timeout=timeout)

    def _initialize_cache_status_table(self, relays_plugins_config: dict) -> dict[str, bool]:
        """
        Initializes the cache status table for plugin devices.
        Args:
            relays_plugins_config (dict): Configuration for relays and plugins.
        Returns:
            dict[str, bool]: A dictionary mapping plugin device names to their status.
        """
        return {plugin_device_name: bool(self._run_async(self._plugins[plugin_device_name].status(device_name=plugin_device_name))) for plugin_device_name in list(relays_plugins_config.get(DEPENDENCIES, {}).keys())}

    def is_trigger_exists(self, relay_id: int) -> bool:
        """
        Checks if a trigger exists for a relay.
        Args:
            relay_id (int): The ID of the relay to check.
        Returns:
            bool: True if the trigger exists, False otherwise.
        """
        is_plugin_name = True if self._plugins_mapping and relay_id in self._plugins_mapping else False
        is_plugin_config = True if is_plugin_name and self._plugins_mapping[relay_id] in self._dependencies else False
        return True if all([is_plugin_name, is_plugin_config]) else False

    def set_trigger_toggle(self, relay_id: int, on_off_forced: bool = True):
        """
        Toggles the trigger for a relay.
        Args:
            relay_id (int): The ID of the relay to toggle.
            on_off_forced (bool, optional): If True, forces the relay on or off. Defaults to True.
        """
        plugin_device_name = None
        try:
            plugin_device_name = self._plugins_mapping[relay_id]
            plugin = self._plugins[plugin_device_name]
            if on_off_forced:
                status = self._run_async(plugin.toggle_on_off(device_name=plugin_device_name, on_off_forced=on_off_forced))
            else:
                status = self._run_async(plugin.switch_off(device_name=plugin_device_name))
            msg = f"Device {plugin_device_name} is {status}"
            logging.debug(msg)
            # Updates the cache status table for the current device
            self._cache_status_table[plugin_device_name] = bool(status)
        except AttributeError as ae:
            logging.error(ae)
        except RuntimeError as rte:
            logging.error(rte)
        except Exception as e:
            logging.error(f"Device [{plugin_device_name}] is not available for relay_id [{relay_id}]: {e.args[0]}")

    def get_trigger_status(self, relay_id) -> bool:
        """
        Gets the status of a trigger for a relay.
        Args:
            relay_id (int): The ID of the relay to check.
        Returns:
            bool: The status of the trigger.
        """
        plugin_device_name = DEVICE_UNKNOWN
        status = False
        try:
            plugin_device_name = self._plugins_mapping[relay_id]
            plugin = self._plugins[plugin_device_name]
            if plugin:
                status = bool(self._run_async(plugin.status(device_name=plugin_device_name)))
            else:
                status = False
        except AttributeError:
            logging.error(f"Plugin device {plugin_device_name} is not available")
        except KeyError as ke:
            logging.debug(f"No plugin device detected for relay_id [{ke.args[0]}]")
            status = False
        except Exception as e:
            logging.error(f"Failed to get plugin device [{plugin_device_name}] status for relay_id [{relay_id}]: {e}")
        # Updates the cache status table for the current device
        self._cache_status_table[plugin_device_name] = status
        logging.debug(f"Plugin device {plugin_device_name} status: {status}")
        return status

    def is_trigger_on(self, relay_id) -> bool:
        """
        Checks if a trigger is on for a relay.
        Args:
            relay_id (int): The ID of the relay to check.
        Returns:
            bool: True if the trigger is on, False otherwise.
        """
        plugin_device_name = self._plugins_mapping[relay_id]
        return self._cache_status_table[plugin_device_name]

    def _add_plugin(self, plugin_name, plugin: PluginMQTT | PluginHTTP) -> None:
        """
        Adds a plugin to the plugins dictionary.
        Args:
            plugin_name (str): The name of the plugin.
            plugin (PluginMQTT | PluginHTTP): The plugin instance to add.
        """
        if isinstance(plugin, PluginMQTT):
            plugin.manager = self._run_async(plugin.get_manager_mqtt())
            self._plugins[plugin_name] = plugin
            logging.info(f"MQTT plugin {plugin_name} initialized")
        elif isinstance(plugin, PluginHTTP):
            plugin.manager = self._run_async(plugin.get_manager_http())
            if not getattr(plugin, "enabled", True):
                logging.warning(f"HTTP plugin {plugin_name} disabled")
                return
            self._plugins[plugin_name] = plugin
            logging.info(f"HTTP plugin {plugin_name} initialized")

    def _plugins_managers_init(self, relays_plugins_config: dict) -> None:
        """
        Initializes plugin managers based on the configuration.
        Args:
            relays_plugins_config (dict): Configuration for relays and plugins.
        """
        for plugin_name, plugin_metadata in relays_plugins_config.get(DEPENDENCIES, {}).items():
            try:
                for trigger_type, trigger_metadata in plugin_metadata[TRIGGERS].items():
                    if trigger_type == MQTT:
                        mqtt_module = importlib.import_module(trigger_metadata[PLUGIN_MODULE])  # pylint: disable=no-member
                        plugin_mqtt_class = getattr(mqtt_module, trigger_metadata[PLUGIN_CLASS])
                        PluginMQTT.register(plugin_mqtt_class)
                        plugin_mqtt = plugin_mqtt_class()
                        self._add_plugin(plugin_name, plugin_mqtt)
                    elif trigger_type == HTTP:
                        http_module = importlib.import_module(trigger_metadata[PLUGIN_MODULE])  # pylint: disable=no-member
                        plugin_http_class = getattr(http_module, trigger_metadata[PLUGIN_CLASS])
                        PluginHTTP.register(plugin_http_class)
                        plugin_http = plugin_http_class(plugin_metadata[HOST], plugin_metadata[PORT])
                        self._add_plugin(plugin_name, plugin_http)
            except Exception as e:
                logging.error(f"Failed to initialize plugin {plugin_name}: {e}")

        if not relays_plugins_config:
            logging.warning("Plugins disabled")

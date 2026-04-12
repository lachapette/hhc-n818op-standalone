# HHC-N818OP Standalone Client

A standalone client to manage HHC-N818OP relays with plugin support and programmable scenarios.

## Description

This project provides a standalone daemon client to control HHC-N818OP relay modules over the network. It allows you to:

- Control relays individually or in groups
- Define timed scenarios with scheduled activation/deactivation
- Integrate external plugins (MQTT, HTTP, Meross IoT, etc.)
- Manage dependencies between relays (e.g., well pump)

## Quickstart

### Install with pip

```bash
git clone https://github.com/yannick-lidie/hhc-n818op-standalone.git
cd hhc-n818op-standalone
python -m pip install .
```

### Install with uv

```bash
git clone https://github.com/yannick-lidie/hhc-n818op-standalone.git
cd hhc-n818op-standalone
uv pip install .
```

### Run the daemon

```bash
cp daemon_hhc_n818op/hhc_n818op_standalone_d.yaml daemon_hhc_n818op/hhc_n818op_standalone_d.local.yaml
python daemon_hhc_n818op/hhc_n818op_standalone_d.py
```

### Run with Docker (`start.sh`)

```bash
cd docker/bin
./start.sh
```

> **Note**: The `start.sh` script automatically creates the `docker/.env` file from `docker/.env.in` if it doesn't exist.

For full Docker configuration, see [Docker Installation](#docker-installation).

## Features

### Relay Management

- Control 8 relays via network connection
- Individual or group activation/deactivation
- Real-time relay status

### Programmable Scenarios

- Precise start time definitions
- Configurable durations for each relay
- Sequential or parallel execution
- Time format support: `HH:MM:SS.microseconds`

### Plugin System

- Modular architecture to extend functionality
- Native MQTT plugin support (Meross IoT)
- Dependency management between devices
- Flexible integration via YAML configuration

## Prerequisites

- Python 3.10+
- Required libraries (see `pyproject.toml`):
  - `requests`
  - `ruamel.yaml`
  - `pytz`
  - `meross-iot`

## Installation

For the fastest setup, see the [Quickstart](#quickstart) section above.

### Clone the repository

```bash
git clone https://github.com/yannick-lidie/hhc-n818op-standalone.git
cd hhc-n818op-standalone
```

### Install dependencies

```bash
make dev # creates Python environment with dependencies

# or

# Create a virtual environment (recommended)
python -m pip install pipx

pipx install uv

# Install dependencies
uv sync

source .venv/bin/activate  # Linux/Mac
# .\.venv\Scripts\activate  # Windows
```

## Configuration

Copy and adapt the configuration file:

```bash
cp daemon_hhc_n818op/hhc_n818op_standalone_d.yaml daemon_hhc_n818op/hhc_n818op_standalone_d.local.yaml
```

Edit the file to configure:

- HHC-N818OP module IP address and port
- Daemon parameters (log level, PID files, timezone)
- Relay scenarios
- Plugin configuration

## Detailed Configuration

### YAML File Structure

```yaml
daemon:
  log_level: info           # Logging level (debug, info, warning, error)
  pidfile: /run/hhc_n818op_d.pid  # PID file
  cycle: 2                  # Check cycle (seconds)
  cycle_sleeping: 300       # Sleep time between cycles (seconds)
  logfile: /var/log/daemon_hhc_n818op.log
  timezone: Europe/Paris    # Timezone

hhc-n818op:
  host: 10.0.30.2           # HHC-N818OP module IP address
  port: 5000                # Connection port

relays_scenarios: # List of scenarios
  - start_time: '23:16:00'
    relays_durations: # Activation sequence
      - 1: '00:00:10'       # Relay 1 for 10 seconds
        5: '00:00:10'       # Relay 5 for 10 seconds (parallel)
      - 1: '00:00:10'
        2: '00:00:10'

# Comment this section if you don't use plugins
plugin_relays: # Configuration for additional plugins to trigger other hardware relays by dependencies.
  dependencies_mapping:
    2: Well Pump            # Relay 2 triggers another dependent relay named "Well Pump"

  dependencies:
    Well Pump: # Meross IoT dependent switch relay
      host: 10.0.30.8
      port: 80
      triggers:
        mqtt:
          plugin_module: plugins.meross.meross_client_cloud_mqtt
          plugin_classname: PluginMeross
```

### Scenario Options

- `start_time`: Scenario start time (format: `HH:MM:SS` or `HH:MM:SS.microseconds`)
- `relays_durations`: List of dictionaries where:
  - Key = relay number (1-8)
  - Value = activation duration (format: `HH:MM:SS`)
  - Relays on the same line are activated in parallel

## Usage

### Start the daemon

```bash
python daemon_hhc_n818op/hhc_n818op_standalone_d.py
```

### Docker Installation

The project provides a `start.sh` script and a `docker-compose.yaml` file for simplified container deployment.

#### Prerequisites
- Docker installed
- Docker Compose (v2+)
- User with Docker permissions

#### Docker Configuration

1. **Configure environment**: The `start.sh` script automatically generates the `docker/.env` file from `docker/.env.in` with default values. You can modify these values:
   ```bash
   # docker/.env.in (default values)
   CONTAINER_NAME=hhc_n818op/relay_client
   INSTALL_FOLDER_CLIENT=/usr/share/${CONTAINER_NAME}
   CONTAINER_USER=hhc_n818op_user
   CONTAINER_NETWORK=hhc_n818op_network
   UID_GID_DEFAULT=1000
   ```

   > **Tip**: To customize, modify the generated `docker/.env` file directly.


#### Start the service

```bash
# Go to the docker/bin directory
cd docker/bin

# Run the startup script (creates network, builds image, and starts container)
./start.sh
```

The `start.sh` script automatically:
- Creates the Docker network `hhc_n818op_network` (if it doesn't exist)
- Creates the dedicated system user (if needed)
- Stops the existing container
- Rebuilds and starts the container with `docker-compose.yaml`

#### Useful Docker Commands

```bash
# Stop the container
docker stop hhc_n818op_client

# View logs
docker logs hhc_n818op_client -f

# Restart the container
docker restart hhc_n818op_client

# Remove container and network
docker compose -f ../docker-compose.yaml down

# Rebuild image (after code changes)
docker compose -f ../docker-compose.yaml build --no-cache

# Access container shell
docker exec -it hhc_n818op_client sh
```

#### Advanced Docker Configuration

The `Dockerfile` (in `docker/Dockerfile`) uses:
- **Base image**: `python:3.11-alpine`
- **Working directory**: `${INSTALL_FOLDER_CLIENT}` (default: `/usr/share/hhc_n818op/relay_client`)
- **PYTHONPATH**: Set to `${INSTALL_FOLDER_CLIENT}` to enable Python imports
- **Entry point**: `sh -c "export PYTHONPATH=$(pwd) && python hhc_n818op_standalone_d.py"`
- **System files created**: `/var/log/daemon_hhc_n818op.log` and `/run/hhc_n818op_d.pid` with `666` permissions
- **Python dependencies**: `requests`, `ruamel.yaml`, `pytz`, `meross-iot`

To modify the image, edit the `Dockerfile` and then rebuild using the command above.

#### Docker Environment Variables

| Variable | Description | Default Value |
|----------|-------------|---------------|
| `CONTAINER_NAME` | Docker image/container name | `hhc_n818op/relay_client` |
| `INSTALL_FOLDER_CLIENT` | Installation directory in container | `/usr/share/${CONTAINER_NAME}` |
| `CONTAINER_NETWORK` | Docker network name | `hhc_n818op_network` |
| `WRK_DOCKER_DIR` | Docker directory (generated by `start.sh`) | Absolute path to `docker/` directory |
| `PUID`/`PGID` | User/Group ID | `1000` (or from `${UID_GID_DEFAULT}`) |

#### Useful Docker Commands

```bash
# Stop the container
docker stop hhc_n818op/relay_client

# View logs
docker compose -f docker/docker-compose.yaml logs -f hhc_n818op_client

# Restart the container
docker restart hhc_n818op_client

# Remove container and network
cd docker && docker compose -f docker-compose.yaml down

# Rebuild image (after code changes)
cd docker && docker compose -f docker-compose.yaml build --no-cache

# Check resolved Docker configuration
docker compose -f docker/docker-compose.yaml config

# Access container shell
docker exec -it docker-hhc_n818op_client-1 sh
```

#### Docker Troubleshooting

**Issue: `Cannot locate Dockerfile` or `path not found`**
- **Cause**: The `build.context` in `docker-compose.yaml` is incorrect.
- **Solution**: Ensure `context: ${WRK_DOCKER_DIR}/../` points to the project root (`hhc-n818op-standalone/`).
- **Verification**: Run `docker compose -f docker/docker-compose.yaml config` to see the resolved context.

**Issue: `ModuleNotFoundError: No module named 'daemon_hhc_n818op'`**
- **Cause**: The Python package `daemon_hhc_n818op` is not in PYTHONPATH.
- **Solution**: The Dockerfile now sets `ENV PYTHONPATH=${INSTALL_FOLDER_CLIENT}` and the ENTRYPOINT dynamically exports `PYTHONPATH=$(pwd)`. Rebuild the image with `--no-cache`.

**Issue: `Permission denied: '/var/log/daemon_hhc_n818op.log'` or `/run/hhc_n818op_d.pid'`**
- **Solution**: The Dockerfile now creates these files with `chmod 666` during the build. Rebuild the image with `--no-cache`.

**Issue: Container keeps restarting**
- **Cause**: An unhandled application error (e.g., YAML configuration error).
- **Diagnostic**: `docker compose -f docker/docker-compose.yaml logs hhc_n818op_client`
- **Solution**: Fix the configuration (e.g., ensure `plugin_relays.dependencies` exists in your YAML).

## Project Structure

```
hhc-n818op-standalone/
├── daemon_hhc_n818op/
│   ├── __init__.py                    # Common constants
│   ├── hhc_n818op/
│   │   ├── __init__.py                # Relay module constants
│   │   ├── relay_client.py            # Main relay client
│   │   ├── relay_plugins.py           # Plugin management
│   │   └── time_parser.py             # Time parser
│   ├── hhc_n818op_standalone_d.py      # Daemon entry point
│   └── hhc_n818op_standalone_d.yaml    # Default configuration
├── docker/
│   ├── .env.in                        # Docker environment template
│   ├── .env                           # Docker environment (generated by start.sh)
│   ├── Dockerfile                     # Docker image definition
│   ├── bin/
│   │   └── start.sh                   # Startup script
│   └── docker-compose.yaml            # Docker Compose configuration
├── plugins/
│   └── meross/
│       └── meross_client_cloud_mqtt.py  # Meross IoT plugin
├── tests/
│   └── ...                            # Unit tests
├── pyproject.toml                     # Project configuration
├── README_FR.md                       # French documentation
└── LICENSE                            # GPL-3.0 License
```

## Available Plugins

### Meross MQTT Plugin

Allows control of Meross IoT devices via MQTT and integrates them as dependencies for relays.

**Configuration:**

```yaml
plugin_module: plugins.meross.meross_client_cloud_mqtt
plugin_classname: PluginMeross
```

## Development

### Add a new plugin

1. Create a module in the `plugins/` directory
2. Implement a class that inherits from `BasePlugin` (see `relay_plugins.py`)
3. Implement required methods:
   - `start()`: Start the plugin
   - `stop()`: Stop the plugin
   - `is_ready()`: Check if plugin is ready
   - `get_device_status(device_id)`: Get device status

### Run tests

```bash
pytest tests/ -v
```

### Code analysis

```bash
make sct # Launches pylint, black, isort, flake8, etc...
```

## Contribution

Contributions are welcome! Please:

1. Fork the project
2. Create a branch for your feature (`git checkout -b feature/new-feature`)
3. Commit your changes (`git commit -m 'Add new feature'`)
4. Push to the branch (`git push origin feature/new-feature`)
5. Open a Pull Request

## License

This project is distributed under the **GPL-3.0** license. See the [LICENSE](LICENSE) file for more details.

## Contact

Author: Yannick LIDIE
Email: yannick@lidie.fr

---

*Documentation generated for HHC-N818OP Standalone Client project*

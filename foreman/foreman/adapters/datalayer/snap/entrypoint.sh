#!/bin/bash

while ! snapctl is-connected active-solution
do
  sleep 5
done

CONFIG_DIR="$SNAP_COMMON/solutions/activeConfiguration/foreman"
ENV_FILE="$CONFIG_DIR/foreman.env"
DEFAULT_ENV_FILE="$SNAP/etc/foreman.default.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "Creating default configuration at $ENV_FILE"
    mkdir -p "$CONFIG_DIR"
    cp "$DEFAULT_ENV_FILE" "$ENV_FILE"
fi

source "$ENV_FILE"

echo "Loading configuration from $ENV_FILE"

# Future, add default config file as well
CONFIG_FILE="$CONFIG_DIR/scenario.yaml"
DEFAULT_CONFIG="$SNAP/opt/ros/snap/share/foreman/scenario.yaml"

mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Config file not found at $CONFIG_FILE."
    if [ -f "$DEFAULT_CONFIG" ]; then
        echo "Populating with default scenario config..."
        cp "$DEFAULT_CONFIG" "$CONFIG_FILE"
    else
        echo "WARNING: Default config $DEFAULT_CONFIG not found in snap."
    fi
else
    echo "Using existing config: $CONFIG_FILE"
fi

exec ros2 run foreman foreman_node
#     --ros-args -p config_file:="$CONFIG_FILE"

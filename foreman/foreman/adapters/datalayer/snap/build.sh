#!/bin/bash
set -e

# Run this script from the foreman/adapters/datalayer/snap directory

SDK_VERSION="4.6.0"
SDK_ZIP="ctrlx-automation-sdk-${SDK_VERSION}.zip"
ASSETS_DIR="assets"

# Files we're interested in, relative to extracted releases
DATALAYER_DEB_NAME="ctrlx-datalayer-3.5.2.deb"
FLATBUFFER_WHEEL_NAME="ctrlx_fbs-2.6.0-py3-none-any.whl"

# Why handle the .deb and .whl manually instead of installing ctrlx datalayer on host computer, like in the example
# found here: https://github.com/boschrexroth/ctrlx-automation-sdk/blob/main/scripts/install-ctrlx-datalayer.sh
# and then staged here: https://github.com/boschrexroth/ctrlx-automation-sdk/blob/65228210674f5f70cd0c9ec990180d05fa3fa196/samples-python/datalayer.provider/snap/snapcraft.yaml#L39

# The official examples use a script to install a .deb package into the
# host machine's apt repository, so it can be staged via 'stage-packages' in snapcraft.
# We download and extract the .deb and .whl directly into a local assets folder.
# This avoids modifying the host system's global apt sources (no sudo needed)
# and makes the build completely self-contained and CI/CD friendly.

mkdir -p "$ASSETS_DIR"

if [ ! -f "${ASSETS_DIR}/${DATALAYER_DEB_NAME}" ] || [ ! -f "${ASSETS_DIR}/${FLATBUFFER_WHEEL_NAME}" ]; then
    echo "Downloading ctrlX SDK v${SDK_VERSION}..."
    wget -q --show-progress "https://github.com/boschrexroth/ctrlx-automation-sdk/releases/download/${SDK_VERSION}/${SDK_ZIP}" -O "${ASSETS_DIR}/${SDK_ZIP}"
    
    echo "Extracting the .deb and .whl from the SDK zip..."
    unzip -j "${ASSETS_DIR}/${SDK_ZIP}" "ctrlx-automation-sdk/deb/${DATALAYER_DEB_NAME}" "ctrlx-automation-sdk/whl/${FLATBUFFER_WHEEL_NAME}" -d "${ASSETS_DIR}/"
    
    echo "Cleaning up downloaded zip..."
    rm "${ASSETS_DIR}/${SDK_ZIP}"
else
    echo "Assets already exist in ${ASSETS_DIR}/. Skipping download."
fi

echo "Assets ready. Building snap..."
snapcraft clean scripts && snapcraft pack #--verbosity=debug --debug
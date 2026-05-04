import os
import ctrlxdatalayer
from ctrlxdatalayer.variant import Variant, Result
from ctrlxdatalayer.provider_node import ProviderNodeCallbacks, ProviderNode, NodeCallback
from ctrlxdatalayer.metadata_utils import MetadataBuilder, AllowedOperation, ReferenceType
from comm.datalayer import NodeClass

class SimpleStringNode:
    """A minimal ctrlX Data Layer provider node holding a string."""
    
    def __init__(self, provider, address: str, initial_value: str):
        self._provider = provider
        self._address = address
        
        # Initialize variant holding the data
        self._data = Variant()
        self._data.set_string(initial_value)

        # 1. Define the mandatory 6 callbacks
        self._cbs = ProviderNodeCallbacks(
            self.__on_create,
            self.__on_remove,
            self.__on_browse,
            self.__on_read,
            self.__on_write,
            self.__on_metadata,
        )
        self._provider_node = ProviderNode(self._cbs)

        # 2. Build node metadata
        builder = MetadataBuilder(allowed=AllowedOperation.READ | AllowedOperation.WRITE)
        builder = builder.set_display_name(self._address)
        builder = builder.set_node_class(NodeClass.NodeClass.Variable)
        builder.add_reference(ReferenceType.ReferenceType.read, "types/datalayer/string")
        builder.add_reference(ReferenceType.ReferenceType.write, "types/datalayer/string")
        self._metadata = builder.build()

    def register(self) -> Result:
        return self._provider.register_node(self._address, self._provider_node)

    def unregister(self):
        self._provider.unregister_node(self._address)
        self._metadata.close()
        self._data.close()

    def set_value(self, new_value: str):
        self._data.set_string(new_value)

    # --- Callbacks ---
    def __on_create(self, userdata, address: str, data: Variant, cb: NodeCallback):
        cb(Result.OK, data)

    def __on_remove(self, userdata, address: str, cb: NodeCallback):
        cb(Result.UNSUPPORTED, None)

    def __on_browse(self, userdata, address: str, cb: NodeCallback):
        with Variant() as new_data:
            new_data.set_array_string([])
            cb(Result.OK, new_data)

    def __on_read(self, userdata, address: str, data: Variant, cb: NodeCallback):
        # We simply return the internally stored variant
        cb(Result.OK, self._data)

    def __on_write(self, userdata, address: str, data: Variant, cb: NodeCallback):
        if self._data.get_type() != data.get_type():
            cb(Result.TYPE_MISMATCH, None)
            return
        _, self._data = data.clone()
        cb(Result.OK, self._data)

    def __on_metadata(self, userdata, address: str, cb: NodeCallback):
        cb(Result.OK, self._metadata)


class DatalayerAdapter:
    def __init__(self):
        self.system = None
        self.provider = None
        self.node = None
        self.node_path = "foreman/test_string"

    def start(self):
        # 1. Initialize the Data Layer System
        self.system = ctrlxdatalayer.system.System("")
        self.system.start(False)

        # 2. Connect to Provider
        # If SNAP is in the environment, "ipc://" automatically maps to $SNAP_DATA/.datalayer
        conn_string = "ipc://" if 'SNAP' in os.environ else "tcp://boschrexroth:boschrexroth@192.168.1.1"
        self.provider = self.system.factory().create_provider(conn_string)
        
        if self.provider.start() != Result.OK:
            print("Failed to start Provider!")
            return False

        if not self.provider.is_connected():
            print("Provider not connected!")
            return False

        # 3. Create and register our custom node
        self.node = SimpleStringNode(self.provider, self.node_path, "Initial Foreman Value")
        result = self.node.register()
        print(f"Registered node '{self.node_path}' with result: {result}")
        
        return True

    def update_test_string(self, new_value: str):
        """Called by your ROS 2 node to update the string internally."""
        if self.node:
            self.node.set_value(new_value)

    def stop(self):
        if self.node:
            self.node.unregister()
        if self.provider:
            self.provider.stop()
        if self.system:
            self.system.stop(False)
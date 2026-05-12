import os
import ctrlxdatalayer
from ctrlxdatalayer.variant import Variant, Result
from ctrlxdatalayer.provider_node import ProviderNodeCallbacks, ProviderNode, NodeCallback
from ctrlxdatalayer.provider import Provider

class SimpleStringNode:
    """A minimal ctrlX Data Layer provider node holding a string."""
    
    def __init__(self, provider: Provider, address: str, initial_value: str):
        self.provider = provider
        self.address = address
        
        self.data = Variant()
        self.data.set_string(initial_value)

        self.cbs = ProviderNodeCallbacks(
            self.__on_create,
            self.__on_remove,
            self.__on_browse,
            self.__on_read,
            self.__on_write,
            self.__on_metadata,
        )
        self.provider_node = ProviderNode(self.cbs)

    def register(self) -> Result:
        """Register the node with the Data Layer."""
        return self.provider.register_node(self.address, self.provider_node)

    def unregister(self):
        """Unregister the node from the Data Layer."""
        self.provider.unregister_node(self.address)

    def set_value(self, new_value: str):
        """Update the value exposed to the Data Layer."""
        self.data.set_string(new_value)

    # --- Callbacks ---
    def __on_create(self, userdata, address: str, data: Variant, cb: NodeCallback):
        cb(Result.OK, data)

    def __on_remove(self, userdata, address: str, cb: NodeCallback):
        cb(Result.UNSUPPORTED, None)

    def __on_browse(self, userdata, address: str, cb: NodeCallback):
        new_data = Variant()
        new_data.set_array_string([])
        cb(Result.OK, new_data)

    def __on_read(self, userdata, address: str, data: Variant, cb: NodeCallback):
        cb(Result.OK, self.data)

    def __on_write(self, userdata, address: str, data: Variant, cb: NodeCallback):
        if self.data.get_type() != data.get_type():
            cb(Result.TYPE_MISMATCH, None)
            return
        
        _, self.data = data.clone()
        cb(Result.OK, self.data)

    def __on_metadata(self, userdata, address: str, cb: NodeCallback):
        cb(Result.FAILED, None)


class DatalayerAdapter:
    def __init__(self):
        self.system = None
        self.provider = None
        self.node = None
        self.node_path = "foreman/test_string"

    def start(self):
        """Start the provider and register the node."""
        self.system = ctrlxdatalayer.system.System("")
        self.system.start(False)

        # Environment detection logic
        conn_string = "ipc://" if 'SNAP' in os.environ else "tcp://boschrexroth:boschrexroth@192.168.1.1"
        self.provider = self.system.factory().create_provider(conn_string)
        
        if self.provider.start() != Result.OK:
            print("Failed to start ctrlX Provider!")
            return False

        if not self.provider.is_connected():
            print("ctrlX Provider not connected!")
            return False

        self.node = SimpleStringNode(self.provider, self.node_path, "Initial Foreman Value")
        result = self.node.register()
        
        if result != Result.OK:
            print(f"Failed to register node '{self.node_path}'. Result: {result}")
            return False
            
        print(f"Registered node '{self.node_path}' successfully.")
        return True

    def update_test_string(self, new_value: str):
        """Called by your ROS 2 node to update the string internally."""
        if self.node:
            self.node.set_value(new_value)

    def stop(self):
        """Safely stop and clean up. Must be called explicitly."""
        print("Stopping Datalayer adapter...")
        if self.node:
            self.node.unregister()
            self.node = None
        if self.provider:
            self.provider.stop()
            self.provider.close()
            self.provider = None
        if self.system:
            self.system.stop(False)
            self.system = None
        print("Datalayer adapter successfully stopped.")
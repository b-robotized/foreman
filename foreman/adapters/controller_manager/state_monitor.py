import threading
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

from controller_manager_msgs.msg import ControllerManagerActivity
from foreman.types import Component, ComponentType, LifecycleState, SystemState


class StateMonitor:
    """
    Southbound Inbound Adapter.
    
    Monitors the Controller Manager's activity topic and maintains the 
    internal SystemState.
    """

    def __init__(self, node: Node, system_state: SystemState, state_lock: threading.Lock, controller_manager_name: str):
        self._node = node
        self._system_state = system_state
        self._state_lock = state_lock
        
        # Need TransientLocal here
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        self._subscription = self._node.create_subscription(
            ControllerManagerActivity,
            f'/{controller_manager_name}/activity',
            self._callback,
            qos_profile,
            callback_group=self._node.callback_group_subscriber
        )
        self._node.get_logger().info(f"Adapters.ControllerManager.StateMonitor: Subscribed to /{controller_manager_name}/activity")

    def _callback(self, msg: ControllerManagerActivity):
        """Processes the activity message and updates the shared SystemState."""
        with self._state_lock:
            for hw_msg in msg.hardware_components:
                try:
                    state = LifecycleState(hw_msg.state.id)
                    self._system_state.components[hw_msg.name] = Component(
                        name=hw_msg.name,
                        component_type=ComponentType.HARDWARE,
                        lifecycle_state=state
                    )
                except ValueError:
                    pass

            for ctrl_msg in msg.controllers:
                try:
                    state = LifecycleState(ctrl_msg.state.id)
                    self._system_state.components[ctrl_msg.name] = Component(
                        name=ctrl_msg.name,
                        component_type=ComponentType.CONTROLLER,
                        lifecycle_state=state
                    )
                except ValueError:
                    pass
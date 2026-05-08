from typing import Dict, List

from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

from controller_manager_msgs.msg import ControllerManagerActivity
from lifecycle_msgs.srv import GetState
from lifecycle_msgs.msg import TransitionEvent

from foreman.engine import ForemanEngine
from foreman.types import Component, ComponentType, LifecycleState


class ComponentStateMonitor:
    """
    Observes full system state from all sources, merges the component state and pushes it to the Engine.

    Sources:
      - /<controller_manager>/activity (TRANSIENT_LOCAL): HW + Controllers
      - /<node>/get_state (service, on discovery): Lifecycle Nodes initial state
      - /<node>/transition_event (VOLATILE): Lifecycle Nodes reactive updates

    For lifecycle nodes, we have to poll /get_state/ for discovery, as /transition_event is volatile and we might not
    catch the node appearing in all cases.
    If you have an idea how to do this better, please open an issue or PR.
    """

    def __init__(
        self,
        node: Node,
        engine: ForemanEngine,
        controller_manager_name: str,
        lifecycle_nodes: List[str],
    ):
        self._node = node
        self._engine = engine
        self.logger_prefix = "Adapters.ComponentStateMonitor:"

        self._cm_components: Dict[str, Component] = {}
        self._lc_components: Dict[str, Component] = {}
        self._lc_nodes_alive: Dict[str, bool] = {n: False for n in lifecycle_nodes}
        self._lifecycle_node_names = lifecycle_nodes

        # Controller Manager /activity topic
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        self._subscription = self._node.create_subscription(
            ControllerManagerActivity,
            f'/{controller_manager_name}/activity',
            self._activity_callback,
            qos_profile,
            callback_group=self._node.callback_group_subscriber
        )
        self._node.get_logger().info(
            f"{self.logger_prefix}  Subscribed to /{controller_manager_name}/activity"
        )

        # Lifecycle node service clients + subscriptions
        self._get_state_clients: Dict[str, object] = {}
        self._transition_event_subs: Dict[str, object] = {}

        for lc_name in lifecycle_nodes:
            client = self._node.create_client(
                GetState,
                f'/{lc_name}/get_state',
                callback_group=self._node.callback_group_services
            )
            self._get_state_clients[lc_name] = client

        # This livelines check if for the sole case when a lifecycle node crashes and 
        # does not emit a /node/transition_event/ message for us to detect it.
        # I'll check LIVELINESS QoS if we can do it via a callback
        # TODO: https://design.ros2.org/articles/qos_deadline_liveliness_lifespan.html
        if lifecycle_nodes:
            self._liveness_timer = self._node.create_timer(
                1.0,
                self._lifecycle_liveness_check,
                callback_group=self._node.callback_group_subscriber
            )
            self._node.get_logger().info(
                f"{self.logger_prefix}  Monitoring lifecycle nodes: {lifecycle_nodes}"
            )
    # TODO: monitor liveliness of this topic as well? That way we know if controller manager dies.
    # Minor. Currently we catch unexpected transitions in the engine (all components go to finalized)
    def _activity_callback(self, msg: ControllerManagerActivity):
        """Parse /activity message into components and push merged state."""
        components = {}

        for hw_msg in msg.hardware_components:
            try:
                components[hw_msg.name] = Component(
                    name=hw_msg.name,
                    component_type=ComponentType.HARDWARE,
                    lifecycle_state=LifecycleState(hw_msg.state.id)
                )
            except ValueError:
                continue

        for ctrl_msg in msg.controllers:
            try:
                components[ctrl_msg.name] = Component(
                    name=ctrl_msg.name,
                    component_type=ComponentType.CONTROLLER,
                    lifecycle_state=LifecycleState(ctrl_msg.state.id)
                )
            except ValueError:
                continue

        self._cm_components = components
        self._push_merged_state()

    def _lifecycle_liveness_check(self):
        """Periodic check: discover lifecycle nodes and confirm liveness."""
        for name, client in self._get_state_clients.items():
            is_reachable = client.service_is_ready()

            if is_reachable and not self._lc_nodes_alive[name]:
                # Node just appeared — poll get_state for actual state
                self._poll_get_state(name)

            elif not is_reachable and self._lc_nodes_alive[name]:
                # Node was alive, now gone
                self._lc_nodes_alive[name] = False
                self._lc_components[name] = Component(
                    name=name,
                    component_type=ComponentType.LIFECYCLE_NODE,
                    lifecycle_state=LifecycleState.FINALIZED
                )
                self._node.get_logger().warn(
                    f"{self.logger_prefix}  Lifecycle node '{name}' is no longer reachable."
                )
                self._push_merged_state()

    def _poll_get_state(self, name: str):
        """Async call to /<node>/get_state. On response, mark alive and subscribe."""
        client = self._get_state_clients[name]
        future = client.call_async(GetState.Request())
        future.add_done_callback(lambda f: self._on_get_state_response(name, f))

    def _on_get_state_response(self, name: str, future):
        """Handle get_state response: update state, mark alive, subscribe to events."""
        try:
            response = future.result()
            state = LifecycleState(response.current_state.id)

            was_alive = self._lc_nodes_alive[name]
            self._lc_nodes_alive[name] = True
            self._lc_components[name] = Component(
                name=name,
                component_type=ComponentType.LIFECYCLE_NODE,
                lifecycle_state=state
            )

            if not was_alive:
                self._subscribe_transition_event(name)
                self._node.get_logger().info(
                    f"{self.logger_prefix}  Lifecycle node '{name}' discovered. State: {state.name}"
                )

            self._push_merged_state()

        except Exception as e:
            self._node.get_logger().warn(
                f"{self.logger_prefix}  Failed to get state for '{name}': {e}"
            )

    def _subscribe_transition_event(self, name: str):
        """Subscribe to /<node>/transition_event for reactive state updates."""
        if name in self._transition_event_subs:
            return

        sub = self._node.create_subscription(
            TransitionEvent,
            f'/{name}/transition_event',
            lambda msg, n=name: self._transition_event_callback(n, msg),
            10,
            callback_group=self._node.callback_group_subscriber
        )
        self._transition_event_subs[name] = sub

    def _transition_event_callback(self, name: str, msg: TransitionEvent):
        """Handle lifecycle transition event: update component state."""
        try:
            new_state = LifecycleState(msg.goal_state.id)
            self._lc_components[name] = Component(
                name=name,
                component_type=ComponentType.LIFECYCLE_NODE,
                lifecycle_state=new_state
            )
            self._push_merged_state()
        except ValueError:
            pass

    def _push_merged_state(self):
        """Combine all sources and push complete state to the engine."""
        all_components = list(self._cm_components.values()) + list(self._lc_components.values())

        was_ready = self._engine.is_ready
        response = self._engine.set_system_state(all_components)

        if not was_ready and self._engine.is_ready:
            self._node.get_logger().info(f"{self.logger_prefix} Foreman is READY. Fresh state received.")

        if not response.success and response.error:
            self._node.get_logger().error(
                f"{self.logger_prefix} [{response.error.category.value}] \n{response.error.message}"
            )

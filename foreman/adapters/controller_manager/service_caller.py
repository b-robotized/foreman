import time
from typing import List
from rclpy.node import Node

from foreman.types import ComponentType, LifecycleState, SystemTransitionCommand
from controller_manager_msgs.srv import (
    CleanupController,
    ConfigureController,
    SetHardwareComponentState,
    SwitchController,
)


class ServiceCaller:
    """
    Executes a list of SystemTransitionCommands using controller_manager ROS2 services.
    """

    def __init__(self, node: Node, transition_pause: float, controller_manager_name: str):
        self._node = node
        self._pause = transition_pause
        # TODO: parametrize this?
        self._timeout = 30.0

        group = self._node.callback_group_services

        self._client_set_hardware_component_state = self._node.create_client(
            SetHardwareComponentState, f'/{controller_manager_name}/set_hardware_component_state', callback_group=group)
        self._client_configure_controller = self._node.create_client(
            ConfigureController, f'/{controller_manager_name}/configure_controller', callback_group=group)
        self._client_cleanup_controller = self._node.create_client(
            CleanupController, f'/{controller_manager_name}/cleanup_controller', callback_group=group)
        self._client_switch_controller = self._node.create_client(
            SwitchController, f'/{controller_manager_name}/switch_controller', callback_group=group)

        self._node.get_logger().info(f"Adapters.ControllerManager.ServiceCaller: {controller_manager_name} service clients created.")

    def execute_transitions(self, commands: List[SystemTransitionCommand]):
        """Executes the plan with safe sequencing: Deactivation -> HW Down -> HW Up -> Config/Cleanup -> Activation."""

        cmds_hw_step_up = []
        cmds_hw_step_down = []
        cmds_ctrl_config = []
        cmds_ctrl_cleanup = []
        cmds_ctrl_activate = []
        cmds_ctrl_deactivate = []

        for cmd in commands:
            current, goal = cmd.component.lifecycle_state, cmd.goal_state

            if cmd.component.component_type == ComponentType.HARDWARE:
                if goal > current: cmds_hw_step_up.append(cmd)
                else: cmds_hw_step_down.append(cmd)
            elif cmd.component.component_type == ComponentType.CONTROLLER:
                if current == LifecycleState.ACTIVE and goal == LifecycleState.INACTIVE: cmds_ctrl_deactivate.append(cmd)
                elif current == LifecycleState.INACTIVE and goal == LifecycleState.ACTIVE: cmds_ctrl_activate.append(cmd)
                elif current == LifecycleState.UNCONFIGURED and goal == LifecycleState.INACTIVE: cmds_ctrl_config.append(cmd)
                elif current == LifecycleState.INACTIVE and goal == LifecycleState.UNCONFIGURED: cmds_ctrl_cleanup.append(cmd)

        # 1. Deactivate controllers first
        if cmds_ctrl_deactivate:
            self._controller_switch([], [c.component.name for c in cmds_ctrl_deactivate])
            time.sleep(self._pause)

        # 2. then hardware down
        for cmd in cmds_hw_step_down:
            self._hardware_set_state(cmd.component.name, cmd.goal_state)
            time.sleep(self._pause)

        # 3. Then hardware transition up
        for cmd in cmds_hw_step_up:
            self._hardware_set_state(cmd.component.name, cmd.goal_state)
            time.sleep(self._pause)

        # 4. clontroller cleanup/config
        for cmd in cmds_ctrl_cleanup: self._controller_cleanup(cmd.component.name); time.sleep(self._pause)
        for cmd in cmds_ctrl_config: self._controller_configure(cmd.component.name); time.sleep(self._pause)

        # 5. controller activation LAST
        if cmds_ctrl_activate:
            self._controller_switch([c.component.name for c in cmds_ctrl_activate], [])
            time.sleep(self._pause)

    def _hardware_set_state(self, name, state):
        self._node.get_logger().info(f"ServiceCaller: Setting {name} -> {state.name}")
        req = SetHardwareComponentState.Request()
        req.name, req.target_state.id = name, state.value
        self._service_call(self._client_set_hardware_component_state, req)

    def _controller_configure(self, name):
        self._node.get_logger().info(f"ServiceCaller: Configuring {name}")
        self._service_call(self._client_configure_controller, ConfigureController.Request(name=name))

    def _controller_cleanup(self, name):
        self._node.get_logger().info(f"ServiceCaller: Cleaning up {name}")
        self._service_call(self._client_cleanup_controller, CleanupController.Request(name=name))

    def _controller_switch(self, activate, deactivate):
        self._node.get_logger().info(f"ServiceCaller: Switching (Act: {activate}, Deact: {deactivate})")
        req = SwitchController.Request(activate_controllers=activate, deactivate_controllers=deactivate, strictness=SwitchController.Request.STRICT)
        self._service_call(self._client_switch_controller, req)

    def _service_call(self, client, request):
        if not client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError(f"Service {client.srv_name} not available")
        future = client.call_async(request)
        start = time.time()
        while not future.done():
            if time.time() - start > self._timeout:
                future.cancel()
                raise TimeoutError(f"Service {client.srv_name} timed out")
            time.sleep(0.05) # Yield GIL
        res = future.result()
        if not res or not getattr(res, 'ok', True):
            raise RuntimeError(f"Service {client.srv_name} failed")
        return res
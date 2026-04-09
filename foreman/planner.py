from typing import List

from foreman.types import Component
from foreman.types import ComponentType
from foreman.types import ControllerDependencyRule
from foreman.types import LifecycleState
from foreman.types import SystemGoal
from foreman.types import SystemState
from foreman.types import SystemTransitionCommand


class Planner:
    """Plan the next single step towards the lifecycle state goal of the system."""

    def __init__(self, dependency_rules: List[ControllerDependencyRule]):
        self.rules = {rule.controller_name: rule for rule in dependency_rules}

    def calculate_transitions(
        self, current_state: SystemState, goal: SystemGoal
    ) -> List[SystemTransitionCommand]:
        commands = []

        # 1. Hardware Transitions
        for hardware_goal in goal.hardware_goals:
            hardware = current_state.components.get(hardware_goal.name)

            if not hardware:
                hardware = Component(
                    hardware_goal.name,
                    ComponentType.HARDWARE,
                    LifecycleState.UNCONFIGURED
                )

            next_state = hardware.lifecycle_state.step_towards(hardware_goal.lifecycle_state)
            if next_state:
                # block hardware step down if controllers are relying on it
                if next_state < hardware.lifecycle_state:
                    if not self._can_hardware_step_down(hardware.name, next_state, current_state):
                        continue

                commands.append(SystemTransitionCommand(hardware, next_state))

        # 2. Controller Transitions
        for controller_goal in goal.controller_goals:
            controller = current_state.components.get(controller_goal.name)

            if not controller:
                controller = Component(
                    controller_goal.name,
                    ComponentType.CONTROLLER,
                    LifecycleState.UNCONFIGURED
                )

            next_state = controller.lifecycle_state.step_towards(controller_goal.lifecycle_state)

            if next_state:
                # Block controller activation if hardware is not ready
                if next_state == LifecycleState.ACTIVE:
                    if not self._are_hardware_dependencies_met(controller_goal.name, current_state):
                        continue

                commands.append(SystemTransitionCommand(controller, next_state))

        return commands

    def _are_hardware_dependencies_met(self, ctrl_name: str, current_state: SystemState) -> bool:
        """Check if all required hardware for a given controller meet the minimum state."""
        rule = self.rules.get(ctrl_name)
        if not rule:
            return True

        for req in rule.required_hardware:
            hw_component = current_state.components.get(req.name)
            if not hw_component or hw_component.lifecycle_state < req.state:
                return False

        return True

    def _can_hardware_step_down(
        self, hw_name: str, next_hw_state: LifecycleState, current_state: SystemState
    ) -> bool:
        """Check if hardware can safely step down without violating controller dependencies."""
        for comp in current_state.components.values():
            if comp.component_type != ComponentType.CONTROLLER:
                continue

            rule = self.rules.get(comp.name)
            if not rule:
                continue

            for req in rule.required_hardware:
                if req.name == hw_name:
                    # If controller is ACTIVE, hardware cannot drop below explicitly required state
                    if comp.lifecycle_state == LifecycleState.ACTIVE:
                        if next_hw_state < req.state:
                            return False

                    # If controller is INACTIVE, hardware cannot be UNCONFIGURED
                    elif comp.lifecycle_state == LifecycleState.INACTIVE:
                        if next_hw_state < LifecycleState.INACTIVE:
                            return False

        return True
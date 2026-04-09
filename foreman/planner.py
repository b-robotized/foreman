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

    def calculate_transitions(self, current_state: SystemState, goal: SystemGoal) -> List[SystemTransitionCommand]:
        commands = []

        # Hardware Transitions
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
                commands.append(SystemTransitionCommand(hardware, next_state))

        # Controller Transitions
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
                # Check hardware state dependencies
                if next_state == LifecycleState.ACTIVE:
                    if not self._are_hardware_dependencies_active(controller_goal.name, current_state):
                        continue

                commands.append(SystemTransitionCommand(controller, next_state))

        return commands

    def _are_hardware_dependencies_active(self, controller_name: str, current_state: SystemState) -> bool:
        """Check if all required hardware for a given controller is currently ACTIVE."""
        rule = self.rules.get(controller_name)
        if not rule:
            return True

        for required_hw_name in rule.required_hardware:
            required_hw_component = current_state.components.get(required_hw_name)
            if not required_hw_component or required_hw_component.lifecycle_state != LifecycleState.ACTIVE:
                return False

        return True

from typing import List, Optional, Tuple
import threading

from foreman.planner import Planner
from foreman.parser import ParsedScenario
from foreman.types import (
    Component,
    ComponentType,
    LifecycleState,
    SystemState,
    SystemTransitionCommand,
    SystemGoal
)
from controller_manager_msgs.msg import ControllerManagerActivity

class ForemanEngine:
    """
    Foreman domain facade.
    All business logic is here, no ROS, jsut python.
    """
    # TODO: rework names. Write an engine_api.py using Typing.Protocol when API solidifies.

    def __init__(self, config: ParsedScenario, state_lock: threading.Lock):
        self._config = config
        self._planner = Planner(config.dependency_rules)
        self._state = SystemState()
        self._state_lock = state_lock

        # TODO: somehow set this up automatically. Current goal will be currently read state.
        self._current_goal = config.goals.get('broadcast_only')
        self._is_ready = False # when we get first /activity reading
        self._is_faulted = False
        self._error_message = ""

    @property
    def is_at_goal(self) -> bool:
        """Checks if there are any remaining transitions to reach the goal."""
        with self._state_lock:
            return self._is_at_goal();

    def request_goal(self, goal_name: str) -> Tuple[bool, str]:
        """
        Request a new goal for the system
        Returns: (success, message)
        """
        goal = self._config.goals.get(goal_name)
        if not goal:
            return False, f"Goal '{goal_name}' not found in configuration."
        
        with self._state_lock:
            self._is_faulted = False
            if self._current_goal == goal:
                if self._is_at_goal():
                    return True, f"Already at goal '{goal_name}'."
                return True, f"Already transitioning to '{goal_name}'."
            self._current_goal = goal
            self._is_ready = not self._any_goal_components_missing()
        
        # TODO: ok for now, but do we return more informative error structs for frontends?
        return True, f"Goal '{goal_name}' requested."
    
    def abort_goal(self, reason: str):
        """Aborts the current goal by stopping transitions and yelling about the reason."""
        with self._state_lock:
            self._is_faulted = True
            self._error_message = reason
        self._abort_transition()

    def _abort_transition(self) -> Tuple[bool, str]:
        """
        Aborts any ongoing transitions by setting the current goal to exactly match the current state.
        """
        with self._state_lock:
            if not self._is_ready:
                return False, "Cannot abort: system state is not yet ready/observed."

            hw_goals = []
            ctrl_goals = []
            
            for component in self._state.components.values():
                component_goal = Component(
                    name=component.name, 
                    component_type=component.component_type, 
                    lifecycle_state=component.lifecycle_state
                )
                if component.component_type == ComponentType.HARDWARE:
                    hw_goals.append(component_goal)
                else:
                    ctrl_goals.append(component_goal)

            self._current_goal = SystemGoal(
                name="aborted",
                hardware_goals=hw_goals,
                controller_goals=ctrl_goals
            )
            
            return True, "Transition aborted."

    def get_next_transition(self) -> Optional[SystemTransitionCommand]:
        """
        Calculate the next step toward the goal.
        """
        if not self._current_goal:
            return None

        with self._state_lock:
            if not self._is_ready:
                return None
            
            return self._planner.get_next_transition(self._state, self._current_goal)

    def set_system_state(self, components: List[Component]):
        """
        Set internal system state to that which is observed.
        The internal state should exactly match that state.
        """
        # TODO: check if we're unexpectedly dropping a component state. add that to the monitor?
        with self._state_lock:
            self._state.components = {comp.name: comp for comp in components}
            self._is_ready = not self._any_goal_components_missing()

    @property
    def current_goal_name(self) -> str:
        return self._current_goal.name if self._current_goal else "None"

    @property
    def is_ready(self) -> bool:
        """Is the system observed and ready to plan?"""
        return self._is_ready

    def get_engine_snapshot(self) -> dict:
        """
        Returns a simplified snapshot of the system.
        """
        with self._state_lock:
            return {
                "goal": self.current_goal_name,
                "ready": self._is_ready,
                "at_goal": self._is_at_goal(),
                "faulted": self._is_faulted,
                "error": self._error_message,
                "components": {
                    name: comp.lifecycle_state.name 
                    for name, comp in self._state.components.items()
                }
            }

    def _is_at_goal(self) -> bool:
        """
        Checks if the current goal is reached.
        MUST be called while holding self._state_lock!
        """
        if not self._is_ready or not self._current_goal:
            return False
        
        # If planner returns nothing, we have reached the goal state
        return self._planner.get_next_transition(self._state, self._current_goal) is None

    def _any_goal_components_missing(self) -> bool:
        """Checks if all components in the goal are present in current state."""
        if not self._current_goal:
            return True
            
        all_component_goals = (
            self._current_goal.hardware_goals + 
            self._current_goal.controller_goals
        )
        
        for component_goal in all_component_goals:
            if component_goal.name not in self._state.components:
                return True
        return False
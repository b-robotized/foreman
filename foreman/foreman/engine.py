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
    SystemGoal,
    ForemanError,
    ForemanResponse,
    ForemanErrorCategory
)

class ForemanEngine:
    """
    Foreman domain facade.
    All business logic is here, no ROS, just python.
    """

    def __init__(self, config: ParsedScenario, state_lock: threading.Lock):
        self._config = config
        self._planner = Planner(config.dependency_rules)
        self._state = SystemState()
        self._state_lock = state_lock

        self._current_goal = None
        self._is_ready = False # when we get first /activity reading
        self._error_state: Optional[ForemanError] = None
        self._last_issued_command: Optional[SystemTransitionCommand] = None

    @property
    def is_at_goal(self) -> bool:
        """Checks if there are any remaining transitions to reach the goal."""
        with self._state_lock:
            return self._locked_is_at_goal()

    def request_goal(self, goal_name: str) -> ForemanResponse:
        """
        Request a new goal for the system
        Returns: (success, message)
        """
        goal = self._config.goals.get(goal_name)
        if not goal:
            return ForemanResponse(False, f"Goal '{goal_name}' not found in configuration.")
        
        with self._state_lock:
            if not self._is_ready:
                return ForemanResponse(False, "Foreman not ready. Is /activity topic being published?")

            missing_components = self._locked_missing_goal_components(goal)
            if missing_components:
                return ForemanResponse(
                    False, 
                    f"Cannot accept goal '{goal_name}'. Missing components in observed state: {missing_components}"
                )

            error_cleared_msg = "Error cleared on new goal. " if self._error_state else ""
            self._error_state = None # new goal received, clear error and try again.
            self._last_issued_command = None
            
            # TODO: minor. On first goal, if we're already at goal, we don't catch this, as self._current_goal == Null.
            # Fix this so we log "Already at goal"
            if self._current_goal == goal:
                if self._locked_is_at_goal():
                    return ForemanResponse(True, f"Already at goal '{goal_name}'.")
                return ForemanResponse(True, f"Already transitioning to '{goal_name}'.")
                
            self._current_goal = goal
        
        return ForemanResponse(True, f"{error_cleared_msg}Goal '{goal_name}' accepted.")
    
    def abort_goal(self, error: ForemanError):
        """Aborts the current goal by stopping transitions."""
        with self._state_lock:
            self._error_state = error
            self._last_issued_command = None
            self._locked_abort_transition()

    def get_next_transition(self) -> Optional[SystemTransitionCommand]:
        """
        Calculate the next step toward the goal.
        """
        if not self._current_goal:
            return None

        with self._state_lock:
            if not self._is_ready or self._error_state:
                return None
            
            cmd = self._planner.get_next_transition(self._state, self._current_goal)
            self._last_issued_command = cmd
            return cmd
            
    def set_system_state(self, components: List[Component]) -> ForemanResponse:
        """
        Set internal system state to that which is observed.
        Monitors for unexpected changes in component state.
        """
        with self._state_lock:
            # overwrite existing state
            previous_state = self._state.components
            self._state.components = {comp.name: comp for comp in components}
            
            was_ready = self._is_ready
            self._is_ready = True

            # In these cases, we just observe state
            if (self._error_state or 
                not was_ready or
                not self._current_goal):
                return ForemanResponse(True, "System state observed.")

            # otherwise, check for anomalies
            unexpected_changes = []
            missing_components = []

            # unexpected state drops
            for incoming in components:
                existing = previous_state.get(incoming.name)
                if existing and incoming.lifecycle_state != existing.lifecycle_state:
                    expected = (
                        self._last_issued_command and 
                        self._last_issued_command.component.name == incoming.name and 
                        self._last_issued_command.goal_state == incoming.lifecycle_state
                    )
                    if not expected:
                        unexpected_changes.append(
                            (incoming.name, existing.lifecycle_state.name, incoming.lifecycle_state.name)
                        )

            # unexpected missing components
            missing_components = self._locked_missing_goal_components(self._current_goal)

            # if any anomalies, emit error
            if unexpected_changes or missing_components:
                error_msgs = []
                error_components = []
                
                if missing_components:
                    error_msgs.append(f"Required components vanished from /activity: {missing_components}")
                    error_components.extend(missing_components)
                    
                if unexpected_changes:
                    msgs = [f"{name} ({old}->{new})" for name, old, new in unexpected_changes]
                    error_msgs.append(f"Unexpected state changes: {', '.join(msgs)}")
                    error_components.extend([change[0] for change in unexpected_changes])

                self._error_state = ForemanError(
                    category=ForemanErrorCategory.UNEXPECTED_STATE,
                    message="Aborting transition:\n  - " + "\n  - ".join(error_msgs),
                    component_names=list(set(error_components))
                )
                
                self._last_issued_command = None
                self._locked_abort_transition()

                return ForemanResponse(
                    success=False, 
                    message="Unexpected system state.", 
                    error=self._error_state
                )

            return ForemanResponse(True, "System state observed with no anomalies.")

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
                "at_goal": self._locked_is_at_goal(),
                "error": {
                    "is_error": self._error_state is not None,
                    "category": self._error_state.category.value if self._error_state else ForemanErrorCategory.NONE.value,
                    "message": self._error_state.message if self._error_state else "",
                    "components": self._error_state.component_names if self._error_state else []
                },
                "components": {
                    name: comp.lifecycle_state.name 
                    for name, comp in self._state.components.items()
                }
            }

    def _locked_is_at_goal(self) -> bool:
        """
        Checks if the current goal is reached.
        MUST be called while holding self._state_lock!
        """
        if not self._is_ready or not self._current_goal:
            return False
        
        # If planner returns nothing, we have reached the goal state
        return self._planner.get_next_transition(self._state, self._current_goal) is None

    def _locked_missing_goal_components(self, target_goal: SystemGoal) -> List[str]:
        """Checks if all components in the target_goal are present in current state.
        Returns a list of missing components.
        MUST be called while holding self._state_lock!
        """
        missing = []
        all_component_goals = (
            target_goal.hardware_goals + target_goal.controller_goals + target_goal.lifecycle_node_goals
        )
        
        for component_goal in all_component_goals:
            if component_goal.name not in self._state.components:
                missing.append(component_goal.name)
        return missing

    def _locked_abort_transition(self):
        """
        Aborts any ongoing transitions.
        MUST be called while holding self._state_lock!
        """
        if not self._is_ready:
            return

        self._current_goal = None
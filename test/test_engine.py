import pytest
import threading
from foreman.engine import ForemanEngine
from foreman.types import Component, ComponentType, LifecycleState, SystemGoal
from foreman.parser import ParsedScenario

@pytest.fixture
def minimal_foreman_config():
    goal = SystemGoal('active_goal', 
                      hardware_goals=[Component('hw1', ComponentType.HARDWARE, LifecycleState.ACTIVE)])
    return ParsedScenario(
        controller_manager="test_cm",
        transition_pause=0.0,
        hardware=["hw1"],
        dependency_rules=[],
        goals={'active_goal': goal}
    )

def test_engine_fault_and_abort(minimal_foreman_config):
    lock = threading.Lock()
    engine = ForemanEngine(minimal_foreman_config, lock)
    
    ERROR_MSG = "Hardware 'hw1' rejected configuration!"
    ABORT_GOAL_NAME = "aborted"

    # initialize
    initial_components = [Component('hw1', ComponentType.HARDWARE, LifecycleState.UNCONFIGURED)]
    engine.set_system_state(initial_components)
    
    # goal to activate comes
    success, msg = engine.request_goal('active_goal')
    assert success is True
    assert engine.is_at_goal is False
    
    # planner wants to transition
    next_transition_command = engine.get_next_transition()
    assert next_transition_command is not None
    assert next_transition_command.goal_state == LifecycleState.INACTIVE
    
    # some failure happens, and we abort goal
    engine.abort_goal(ERROR_MSG)
    
    # system is now AT GOAL
    assert engine.is_at_goal is True 
    
    # planner outputs nothing
    assert not engine.get_next_transition()
    
    # frontend will see the error
    snapshot = engine.get_engine_snapshot()
    assert snapshot['faulted'] is True
    assert snapshot['error'] == ERROR_MSG
    assert snapshot['goal'] == ABORT_GOAL_NAME
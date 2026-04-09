import pytest

from foreman.types import (
    SystemState, 
    Component, 
    SystemGoal, 
    ControllerDependencyRule, 
    ComponentType,
    LifecycleState
)
from foreman.planner import Planner

@pytest.fixture
def planner():
    rules = [
        ControllerDependencyRule(
            controller_name="franka_jtc",
            required_hardware=["franka_hw"]
        )
    ]
    return Planner(dependency_rules=rules)


def test_hardware_progression_one_step(planner):
    """Test that hardware correctly takes a 1-step jump towards a higher goal."""
    current = SystemState(
        components={
            "franka_hw": Component("franka_hw", ComponentType.HARDWARE, LifecycleState.UNCONFIGURED)
        }
    )
    
    # Goal is ACTIVE, but it should only step to INACTIVE first.
    goal = SystemGoal(
        name="test_goal",
        hardware_goals=[Component("franka_hw", ComponentType.HARDWARE, LifecycleState.ACTIVE)]
    )

    commands = planner.calculate_transitions(current, goal)

    assert len(commands) == 1
    assert commands[0].component.name == "franka_hw"
    assert commands[0].goal_state == LifecycleState.INACTIVE
    

def test_controller_transition_blocked_by_hardware(planner):
    """Test that a controller will NOT transition to ACTIVE if its hardware is not ACTIVE."""
    current = SystemState(
        components={
            # Hardware is only INACTIVE, not ACTIVE
            "franka_hw": Component("franka_hw", ComponentType.HARDWARE, LifecycleState.INACTIVE),
            # Controller is INACTIVE, ready to go to ACTIVE
            "franka_jtc": Component("franka_jtc", ComponentType.CONTROLLER, LifecycleState.INACTIVE)
        }
    )
    
    goal = SystemGoal(
        name="running",
        hardware_goals=[Component("franka_hw", ComponentType.HARDWARE, LifecycleState.ACTIVE)],
        controller_goals=[Component("franka_jtc", ComponentType.CONTROLLER, LifecycleState.ACTIVE)]
    )

    commands = planner.calculate_transitions(current, goal)

    # The planner should output a command to move the HARDWARE to ACTIVE.
    # The planner should NOT output a command for the CONTROLLER yet.
    assert len(commands) == 1
    assert commands[0].component.name == "franka_hw"
    assert commands[0].goal_state == LifecycleState.ACTIVE


def test_controller_allowed_when_hardware_ready(planner):
    """Test that a controller WILL transition to ACTIVE if its hardware IS ACTIVE."""
    current = SystemState(
        components={
            # Hardware is now fully ACTIVE
            "franka_hw": Component("franka_hw", ComponentType.HARDWARE, LifecycleState.ACTIVE),
            # Controller is INACTIVE, ready to go to ACTIVE
            "franka_jtc": Component("franka_jtc", ComponentType.CONTROLLER, LifecycleState.INACTIVE)
        }
    )
    
    goal = SystemGoal(
        name="running",
        hardware_goals=[Component("franka_hw", ComponentType.HARDWARE, LifecycleState.ACTIVE)],
        controller_goals=[Component("franka_jtc", ComponentType.CONTROLLER, LifecycleState.ACTIVE)]
    )

    commands = planner.calculate_transitions(current, goal)

    # HW is already at goal. Only controller needs to step up.
    assert len(commands) == 1
    assert commands[0].component.name == "franka_jtc"
    assert commands[0].goal_state == LifecycleState.ACTIVE


def test_step_down_ladder(planner):
    """Test stepping down from ACTIVE to INACTIVE."""
    current = SystemState(
        components={
            "kassow": Component("kassow", ComponentType.HARDWARE, LifecycleState.ACTIVE)
        }
    )
    # We want it fully UNCONFIGURED, but planner should only step it down to INACTIVE first.
    goal = SystemGoal(
        name="stop",
        hardware_goals=[Component("kassow", ComponentType.HARDWARE, LifecycleState.UNCONFIGURED)]
    )

    commands = planner.calculate_transitions(current, goal)
    
    assert len(commands) == 1
    assert commands[0].component.name == "kassow"
    assert commands[0].goal_state == LifecycleState.INACTIVE
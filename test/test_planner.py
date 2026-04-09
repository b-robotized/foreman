import pytest

from foreman.planner import Planner
from foreman.types import Component
from foreman.types import ComponentType
from foreman.types import ControllerDependencyRule
from foreman.types import LifecycleState
from foreman.types import SystemGoal
from foreman.types import SystemState
from foreman.types import SystemTransitionCommand
from foreman.types import HardwareRequirement


@pytest.fixture
def basic_planner():
    rules = [
        ControllerDependencyRule(
            controller_name='franka_jtc',
            required_hardware=[HardwareRequirement('franka_hw', LifecycleState.ACTIVE)]
        )
    ]
    return Planner(dependency_rules=rules)


@pytest.fixture
def broadcaster_planner():
    rules = [
        ControllerDependencyRule(
            controller_name='joint_state_broadcaster',
            required_hardware=[HardwareRequirement('franka_hw', LifecycleState.INACTIVE)]
        )
    ]
    return Planner(dependency_rules=rules)


@pytest.fixture
def asymmetric_planner():
    rules = [
        ControllerDependencyRule(
            controller_name='dual_arm_jtc',
            required_hardware=[
                HardwareRequirement('hw_a', LifecycleState.ACTIVE),
                HardwareRequirement('hw_b', LifecycleState.ACTIVE)
            ]
        )
    ]
    return Planner(dependency_rules=rules)


def apply_commands(state: SystemState, commands: list[SystemTransitionCommand]):
    """Helper to mutate state with planner commands, simulating a successful transition."""
    for cmd in commands:
        state.components[cmd.component.name] = Component(
            cmd.component.name, cmd.component.component_type, cmd.goal_state
        )


def test_scenario_1_standard_bring_up(basic_planner):
    state = SystemState(components={
        'franka_hw': Component('franka_hw', ComponentType.HARDWARE, LifecycleState.UNCONFIGURED),
        'franka_jtc': Component('franka_jtc', ComponentType.CONTROLLER, LifecycleState.UNCONFIGURED)
    })
    goal = SystemGoal('active',
                      hardware_goals=[Component('franka_hw', ComponentType.HARDWARE, LifecycleState.ACTIVE)],
                      controller_goals=[Component('franka_jtc', ComponentType.CONTROLLER, LifecycleState.ACTIVE)])

    # Tick 1: Both step to INACTIVE
    cmds = basic_planner.calculate_transitions(state, goal)
    assert len(cmds) == 2
    assert {c.goal_state for c in cmds} == {LifecycleState.INACTIVE}
    apply_commands(state, cmds)

    # Tick 2: HW steps to ACTIVE, Controller BLOCKED
    cmds = basic_planner.calculate_transitions(state, goal)
    assert len(cmds) == 1
    assert cmds[0].component.name == 'franka_hw'
    assert cmds[0].goal_state == LifecycleState.ACTIVE
    apply_commands(state, cmds)

    # Tick 3: Controller steps to ACTIVE (now that HW is ready)
    cmds = basic_planner.calculate_transitions(state, goal)
    assert len(cmds) == 1
    assert cmds[0].component.name == 'franka_jtc'
    assert cmds[0].goal_state == LifecycleState.ACTIVE


def test_scenario_2_standard_teardown(basic_planner):
    state = SystemState(components={
        'franka_hw': Component('franka_hw', ComponentType.HARDWARE, LifecycleState.ACTIVE),
        'franka_jtc': Component('franka_jtc', ComponentType.CONTROLLER, LifecycleState.ACTIVE)
    })
    goal = SystemGoal('unc',
                      hardware_goals=[Component('franka_hw', ComponentType.HARDWARE, LifecycleState.UNCONFIGURED)],
                      controller_goals=[Component('franka_jtc', ComponentType.CONTROLLER, LifecycleState.UNCONFIGURED)])

    # Tick 1: Controller drops to INACTIVE, HW is BLOCKED
    cmds = basic_planner.calculate_transitions(state, goal)
    assert len(cmds) == 1
    assert cmds[0].component.name == 'franka_jtc'
    assert cmds[0].goal_state == LifecycleState.INACTIVE
    apply_commands(state, cmds)

    # Tick 2: Controller drops to UNCONFIGURED, HW drops to INACTIVE
    cmds = basic_planner.calculate_transitions(state, goal)
    assert len(cmds) == 2
    cmd_states = {c.component.name: c.goal_state for c in cmds}
    assert cmd_states['franka_jtc'] == LifecycleState.UNCONFIGURED
    assert cmd_states['franka_hw'] == LifecycleState.INACTIVE
    apply_commands(state, cmds)

    # Tick 3: HW safely drops to UNCONFIGURED
    cmds = basic_planner.calculate_transitions(state, goal)
    assert len(cmds) == 1
    assert cmds[0].component.name == 'franka_hw'
    assert cmds[0].goal_state == LifecycleState.UNCONFIGURED


def test_scenario_3_broadcaster_bringup(broadcaster_planner):
    state = SystemState(components={
        'franka_hw': Component('franka_hw', ComponentType.HARDWARE, LifecycleState.UNCONFIGURED),
        'joint_state_broadcaster': Component('joint_state_broadcaster', ComponentType.CONTROLLER, LifecycleState.UNCONFIGURED)
    })
    goal = SystemGoal('active',
                      hardware_goals=[Component('franka_hw', ComponentType.HARDWARE, LifecycleState.ACTIVE)],
                      controller_goals=[Component('joint_state_broadcaster', ComponentType.CONTROLLER, LifecycleState.ACTIVE)])

    # Tick 1: Both to INACTIVE
    cmds = broadcaster_planner.calculate_transitions(state, goal)
    apply_commands(state, cmds)

    # Tick 2: HW moves to ACTIVE. Broadcaster moves to ACTIVE *at the same time* because its req (INACTIVE) is met.
    cmds = broadcaster_planner.calculate_transitions(state, goal)
    assert len(cmds) == 2
    assert {c.goal_state for c in cmds} == {LifecycleState.ACTIVE}


def test_scenario_4_partial_pause(basic_planner):
    state = SystemState(components={
        'franka_hw': Component('franka_hw', ComponentType.HARDWARE, LifecycleState.ACTIVE),
        'franka_jtc': Component('franka_jtc', ComponentType.CONTROLLER, LifecycleState.ACTIVE)
    })
    goal = SystemGoal('idle',
                      hardware_goals=[Component('franka_hw', ComponentType.HARDWARE, LifecycleState.INACTIVE)],
                      controller_goals=[Component('franka_jtc', ComponentType.CONTROLLER, LifecycleState.INACTIVE)])

    # Tick 1: Controller pauses. HW blocked from pausing.
    cmds = basic_planner.calculate_transitions(state, goal)
    assert len(cmds) == 1
    assert cmds[0].component.name == 'franka_jtc'
    apply_commands(state, cmds)

    # Tick 2: HW safely pauses.
    cmds = basic_planner.calculate_transitions(state, goal)
    assert len(cmds) == 1
    assert cmds[0].component.name == 'franka_hw'


def test_scenario_5_controller_swap(basic_planner):
    state = SystemState(components={
        'franka_hw': Component('franka_hw', ComponentType.HARDWARE, LifecycleState.ACTIVE),
        'ctrl_A': Component('ctrl_A', ComponentType.CONTROLLER, LifecycleState.ACTIVE),
        'ctrl_B': Component('ctrl_B', ComponentType.CONTROLLER, LifecycleState.INACTIVE)
    })
    goal = SystemGoal('swap',
                      hardware_goals=[Component('franka_hw', ComponentType.HARDWARE, LifecycleState.ACTIVE)],
                      controller_goals=[
                          Component('ctrl_A', ComponentType.CONTROLLER, LifecycleState.INACTIVE),
                          Component('ctrl_B', ComponentType.CONTROLLER, LifecycleState.ACTIVE)
                      ])

    basic_planner.rules['ctrl_A'] = ControllerDependencyRule('ctrl_A', [HardwareRequirement('franka_hw', LifecycleState.ACTIVE)])
    basic_planner.rules['ctrl_B'] = ControllerDependencyRule('ctrl_B', [HardwareRequirement('franka_hw', LifecycleState.ACTIVE)])

    cmds = basic_planner.calculate_transitions(state, goal)
    
    # Both controllers step simultaneously (expecting to call switch controller)
    assert len(cmds) == 2
    cmd_states = {c.component.name: c.goal_state for c in cmds}
    assert cmd_states['ctrl_A'] == LifecycleState.INACTIVE
    assert cmd_states['ctrl_B'] == LifecycleState.ACTIVE


def test_scenario_6_hardware_failure(basic_planner):
    # HW activation failed. It stayed in INACTIVE.
    state = SystemState(components={
        'franka_hw': Component('franka_hw', ComponentType.HARDWARE, LifecycleState.INACTIVE),
        'franka_jtc': Component('franka_jtc', ComponentType.CONTROLLER, LifecycleState.INACTIVE)
    })
    goal = SystemGoal('active',
                      hardware_goals=[Component('franka_hw', ComponentType.HARDWARE, LifecycleState.ACTIVE)],
                      controller_goals=[Component('franka_jtc', ComponentType.CONTROLLER, LifecycleState.ACTIVE)])

    cmds = basic_planner.calculate_transitions(state, goal)
    # HW continues to be commanded. Controller blocked.
    assert len(cmds) == 1
    assert cmds[0].component.name == 'franka_hw'


def test_scenario_7_controller_teardown_failure(basic_planner):

    # Controller deactivation failed. It stayed in ACTIVE.
    state = SystemState(components={
        'franka_hw': Component('franka_hw', ComponentType.HARDWARE, LifecycleState.ACTIVE),
        'franka_jtc': Component('franka_jtc', ComponentType.CONTROLLER, LifecycleState.ACTIVE)
    })
    goal = SystemGoal('unc',
                      hardware_goals=[Component('franka_hw', ComponentType.HARDWARE, LifecycleState.UNCONFIGURED)],
                      controller_goals=[Component('franka_jtc', ComponentType.CONTROLLER, LifecycleState.UNCONFIGURED)])

    cmds = basic_planner.calculate_transitions(state, goal)
    
    # We command the controller down, but simulate it FAILS to step down in the real world (state remains ACTIVE)
    assert len(cmds) == 1
    assert cmds[0].component.name == 'franka_jtc'
    
    # Tick 2: State hasn't changed. Planner MUST NOT command hardware.
    cmds_retry = basic_planner.calculate_transitions(state, goal)
    assert len(cmds_retry) == 1
    assert cmds_retry[0].component.name == 'franka_jtc'



def test_scenario_8_controller_activation_failure(basic_planner):
    state = SystemState(components={
        'franka_hw': Component('franka_hw', ComponentType.HARDWARE, LifecycleState.ACTIVE),
        'franka_jtc': Component('franka_jtc', ComponentType.CONTROLLER, LifecycleState.INACTIVE)
    })
    goal = SystemGoal('active',
                      hardware_goals=[Component('franka_hw', ComponentType.HARDWARE, LifecycleState.ACTIVE)],
                      controller_goals=[Component('franka_jtc', ComponentType.CONTROLLER, LifecycleState.ACTIVE)])

    # Planner issues command for Controller. Hardware sits safely at ACTIVE.
    cmds = basic_planner.calculate_transitions(state, goal)
    assert len(cmds) == 1
    assert cmds[0].component.name == 'franka_jtc'


def test_scenario_9_asymmetric_hardware_failure(asymmetric_planner):
    state = SystemState(components={
        'hw_a': Component('hw_a', ComponentType.HARDWARE, LifecycleState.ACTIVE), # A Succeeded
        'hw_b': Component('hw_b', ComponentType.HARDWARE, LifecycleState.INACTIVE), # B Failed/Stuck
        'dual_arm_jtc': Component('dual_arm_jtc', ComponentType.CONTROLLER, LifecycleState.INACTIVE)
    })
    goal = SystemGoal('active',
                      hardware_goals=[
                          Component('hw_a', ComponentType.HARDWARE, LifecycleState.ACTIVE),
                          Component('hw_b', ComponentType.HARDWARE, LifecycleState.ACTIVE)
                      ],
                      controller_goals=[Component('dual_arm_jtc', ComponentType.CONTROLLER, LifecycleState.ACTIVE)])

    cmds = asymmetric_planner.calculate_transitions(state, goal)
    
    # Controller is BLOCKED because hw_b is not ready. 
    # hw_b is issued a retry command.
    assert len(cmds) == 1
    assert cmds[0].component.name == 'hw_b'
    assert cmds[0].goal_state == LifecycleState.ACTIVE
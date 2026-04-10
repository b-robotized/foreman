import threading

import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

import foreman.adapters as Adapters
from foreman.parser import parse_yaml_file
from foreman.planner import Planner
from foreman.types import SystemState


class ForemanNode(Node):
    def __init__(self):
        super().__init__('foreman_node')
        
        # TODO: parametrize this!
        config_path = "/home/nikolab/bRobotized/workspaces/grc26/src/foreman/foreman/config/scenario.yaml"
        
        # self.declare_parameter('config_path', '')
        # config_path = self.get_parameter('config_path').value
        
        # if not config_path:
        #     raise ValueError("Parameter 'config_path' must be provided")

        # CORE SETUP
        self.config = parse_yaml_file(config_path)
        self.planner = Planner(self.config.dependency_rules)
        self.state = SystemState()
        self.state_lock = threading.Lock()
        self.is_service_call_in_progress = False
        
        # Initial goal
        # TODO: this has to be changed. We'll start from current read state.
        self.current_goal = self.config.goals.get('idle') 

        # Service calls are sequential and mutually exclusive
        self.callback_group_services = MutuallyExclusiveCallbackGroup()
        self.callback_group_subscriber = ReentrantCallbackGroup()
        self.callback_group_timer = ReentrantCallbackGroup()

        # --- Adapters towards ControllerManager ---
        controller_manager_name = self.config.controller_manager

        self.state_monitor = Adapters.ControllerManager.StateMonitor(
            node=self, 
            system_state=self.state, 
            state_lock=self.state_lock, 
            controller_manager_name=controller_manager_name
        )
        self.service_caller = Adapters.ControllerManager.ServiceCaller(
            node=self, 
            transition_pause=self.config.transition_pause, 
            controller_manager_name=controller_manager_name
        )

        # RUN everything at 10HZ
        # TODO: Configure this?
        self.timer = self.create_timer(0.1, self.callback_main_loop, callback_group=self.callback_group_timer)
        # TODO: Add pretty print of current state and read config?
        self.get_logger().info("Foreman Node initialized.")

    def callback_main_loop(self):
        """Main loop."""
        if self.is_service_call_in_progress or not self.current_goal:
            return

        with self.state_lock:
            # TODO: we need a check like this when we request the goal, move it there later. To the facade?
            if self._any_goal_components_missing():
                return

            commands = self.planner.calculate_transitions(self.state, self.current_goal)

        if not commands:
            return

        self.is_service_call_in_progress = True
        
        try:
            # TODO: Can we namespace these to something like "ToControllerManager"
            self.service_caller.execute_transitions(commands)
        except Exception as e:
            self.get_logger().error(f"Execution sequence failed: {e}")
            # TODO: Handle error cases here - where do we transition?
            # TODO: how do we pass mess
        finally:
            self.is_service_call_in_progress = False

    def _any_goal_components_missing(self):
        """Checks if all components required by the current goal are in the system state."""
        for g in self.current_goal.hardware_goals + self.current_goal.controller_goals:
            if g.name not in self.state.components:
                return True
        return False

def main(args=None):
    rclpy.init(args=args)
    
    node = ForemanNode()

    executor = MultiThreadedExecutor()
    executor.add_node(node)
    
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
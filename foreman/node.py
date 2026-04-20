import threading
import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

import foreman.adapters as Adapters
from foreman.parser import parse_yaml_file
from foreman.engine import ForemanEngine


class ForemanNode(Node):
    """
    Glues the Foreman Engine and its adapters.
    """

    def __init__(self):
        super().__init__('foreman_node')
        
        # CONFIG  =============================================
        # TODO: parametrize this!
        config_path = "/home/nikolab/bRobotized/workspaces/grc26/src/foreman/foreman/config/scenario.yaml"
        self.config = parse_yaml_file(config_path)
        # self.declare_parameter('config_path', '')
        # config_path = self.get_parameter('config_path').value
        
        # if not config_path:
        #     raise ValueError("Parameter 'config_path' must be provided")


        self.state_lock = threading.Lock()
        self.service_call_active_future = False
        self.last_transition_time = self.get_clock().now()

        # CORE ENGINE  =============================================
        self.engine = ForemanEngine(self.config, self.state_lock)

        # CONTROLLER MANAGER ADAPTERS ==============================
        self.callback_group_services = MutuallyExclusiveCallbackGroup()
        self.callback_group_subscriber = ReentrantCallbackGroup()
        self.callback_group_timer = MutuallyExclusiveCallbackGroup()

        controller_manager_name = self.config.controller_manager

        self.state_monitor = Adapters.ControllerManager.StateMonitor(
            node=self, 
            engine=self.engine,
            controller_manager_name=controller_manager_name
        )
        self.service_caller = Adapters.ControllerManager.ServiceCaller(
            node=self,
            controller_manager_name=controller_manager_name
        )

        # ADAPTERS TO THE REST OF ROS ==============================

        self.set_goal_server = Adapters.ROS.SetGoalServer(
            node=self, 
            engine=self.engine
        )

        # MAIN LOOP ================================================

        # RUN everything at 10HZ
        # TODO: Configure this?
        self.timer = self.create_timer(
            0.1, 
            self.callback_main_loop, 
            callback_group=self.callback_group_timer
        )
        # TODO: Add pretty print of current state and read config?
        self.get_logger().info("Foreman Node initialized.")

    def callback_main_loop(self):
        """Main loop."""

        if self.service_call_active_future and self.service_call_active_future.done():
            # TODO: check future.result() for errors here?
            self.service_call_active_future = None
            self.last_transition_time = self.get_clock().now()

        if self.service_call_active_future:
            return
        
        command = self.engine.get_next_transition()
        
        time_since_last = (self.get_clock().now() - self.last_transition_time).nanoseconds / 1e9
        if time_since_last < self.config.transition_pause:
            return

        if not command:
            return

        try:
            self.service_call_active_future = self.service_caller.execute_transition(command)
        except Exception as e:
            self.get_logger().error(f"Execution sequence failed: {e}")
            # TODO: Handle error cases here - where do we transition?

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
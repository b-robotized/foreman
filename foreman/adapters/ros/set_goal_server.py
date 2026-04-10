from rclpy.node import Node
from foreman_msgs.srv import SetGoal
from foreman.engine import ForemanEngine

class SetGoalServer:
    """   
    ROS 2 service to set a named goal for Foreman Engine
    """

    def __init__(self, node: Node, engine: ForemanEngine):
        self._node = node
        self._engine = engine
        
        # Using MutuallyExclusiveCallbackGroup
        # If a service is processing, we reject new service requests.
        self._srv = self._node.create_service(
            SetGoal,
            'foreman/set_goal',
            self._handle_set_goal,
            callback_group=self._node.callback_group_services
        )
        
        self._node.get_logger().info("Adapters.ROS.SetGoalServer: Service /foreman/set_goal is ready.")

    def _handle_set_goal(self, request, response):
        """Sets the target system state."""
        goal_name = request.goal
        # TODO: demote some of these to DEBUG logs.
        self._node.get_logger().info(f"Adapters.ROS.SetGoalServer: Received request for goal '{goal_name}'")
        
        success, message = self._engine.request_goal(goal_name)
        
        response.success = success
        response.message = message
        
        if not success:
            self._node.get_logger().warn(f"Adapters.ROS.SetGoalServer: {message}")
            
        return response
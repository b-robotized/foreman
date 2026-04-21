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

        print()
        
        self._node.get_logger().info("Adapters.ROS.SetGoalServer: Service /foreman/set_goal is ready.")

    def _handle_set_goal(self, request, response):
        """Sets the target system state."""
        goal_name = request.goal
        # TODO: demote some of these to DEBUG logs.
        self._node.get_logger().info(f"Adapters.ROS.SetGoalServer: Received request for goal '{goal_name}'")
        
        if not self._engine.is_ready:
            msg = f"Foreman not ready. Is /activity topic being published?"
            self._node.get_logger().warn(f"Adapters.ROS.SetGoalServer: {msg}")
            response.success = False
            response.message = msg
            return response

        engine_response = self._engine.request_goal(goal_name)

        response.success = engine_response.success
        response.message = engine_response.message

        if not engine_response.success:
            self._node.get_logger().warn(f"Adapters.ROS.SetGoalServer: {engine_response.message}")
        else:
            self._node.get_logger().info(f"Adapters.ROS.SetGoalServer: {engine_response.message}")
            
        return response
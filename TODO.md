Todos:

- make the core engine + datatypes.
- test core engine in unit tests with datatypes
- write yaml parsing for the configuration
- create foreman_msgs package
- write ros2 interfaces to connect to controller controller_manager
- define the facade for frontend
- write ros2 interfaces for "cli", connect to the facade
- NO LOADING COMPONENTS load components as well - all of this testing so far assumes we're already loaded the hardware and controllers. now we try and fit in component loading.
- answer... do we want to interrupt current goals with the new goals if we spam goals? Currently, a batch of goals will get executed and all blocks until that happens. Make it so that service_Caller only calls a single command at a time. The planner should track what is the current goal, but get_next_transition should output the next component that transitions.
- order -> C deactivate > HW Down > HW Up > C cleanup > C config > C activate.
- write the first docs to explain the architecture
- figure out how do we propagate error messages from controller manager throughout the core system, so frontend consumes it nicely.
    - we'll do this by exposing and API _log_and_abort_goal() which will update the error message in system snapshot and set the goal state to be 
    the current state, with a name "aborted" and an informative error message.

- consider are we catching the failure states. These have to be available in Foreman get_snapshot() so we can easily expose them in the frontend.
    - if any of the controller_manager service calls failed TO DELIVER (network, timeout), we need to be as infromative as possible.
    - if any of the controller_manager service calls failed TO EXECUTE, we need to be as infromative as possible.
    - if we unexpectedly ended up in a state that is different than what we expected - in set_system_state(). For example, we assing goal "running",
        we reach it, and franka crashes to unconfigured while no goals were active. We want to log informative error message, and not automatically try
        and reach the goal, we want to go to "faulted" goal. This should be a part of state_monitor.py
    - this should better be called "error" goal.


- is the engine.py api solidified? Typing.Protocol
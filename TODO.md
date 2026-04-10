Todos:

- make the core engine + datatypes.
- test core engine in unit tests with datatypes
- write yaml parsing for the configuration
- create foreman_msgs package
- write ros2 interfaces to connect to controller controller_manager
- define the facade for frontend
- write ros2 interfaces for "cli", connect to the facade


- answer... do we want to interrupt current goals with the new goals if we spam goals? Currently, a batch of goals will get executed and all blocks until that happens. Make it so that service_Caller only calls a single command at a time. The planner should track what is the current goal, but get_next_transition should output the next component that transitions.
- order -> C deactivate > HW Down > HW Up > C cleanup > C config > C activate.


- write the first docs to explain the architecture
- figure out how do we propagate error messages from controller manager throughout the core system, so frontend consumes it nicely.

- load components as well - all of this testing so far assumes we're already loaded the hardware and controllers. now we try and fit in component loading.
- is the engine.py api solidified? Typing.Protocol
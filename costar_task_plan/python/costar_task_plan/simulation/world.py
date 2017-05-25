
from costar_task_plan.abstract import *

import pybullet as pb

class SimulationWorld(AbstractWorld):

    def __init__(self, dt = 0.02, num_steps=1, *args, **kwargs):
        super(SimulationWorld, self).__init__(NullReward(), *args, **kwargs)
        self.num_steps = num_steps

        # stores object handles and names
        self.class_by_object = {}
        self.object_by_class = {}

    def addObject(self, obj_name, obj_class, state):
        '''
        Wraps add actor function for objects. Make sure they have the right
        policy and are added so we can easily look them up later on.
        '''
        
        obj_id = self.addActor(SimulationObjectActor(
            name=obj_name,
            dynamics=SimulationDynamics(self),
            policy=NullPolicy(),
            state=state))
        self.class_by_object[obj_id] = obj_class
        self.object_by_class[obj_class] = obj_id
        return obj_id

    def hook(self):
        '''
        Step the simulation forward after all actors have given their comments
        to associated simulated robots. Then update all actors' states.
        '''

        # Loop through the given number of steps
        for i in xrange(self.num_steps):
            pb.stepSimulation()

        # Update the states of all actors.
        for actor in self.actors:
            actor.state = actor.robot.getState()

    
    def zeroAction(self, actor):
        return SimulationRobotAction(cmd=None)

class SimulationDynamics(AbstractDynamics):
    '''
    Send robot's command over to the actor in the current simulation.
    This assumes the world is in the correct configuration, as represented
    by "state."
    '''
    def __call__(self, state, action, dt):
        if action.cmd is not None:
            state.robot.act(action.cmd)

class SimulationObjectState(AbstractState):
    '''
    Represents state and position of an arbitrary rigid object, and any
    associated predicates.
    '''
    def __init__(self, handle,
            base_pos=(0,0,0),
            base_rot=(0,0,0,1)):
        self.predicates = []
        self.base_pos = base_pos
        self.base_rot = base_rot

class SimulationObjectActor(AbstractActor):
    '''
    Not currently any different from the default actor.
    '''

    def __init__(self, name, *args, **kwargs):
        super(SimulationObjectActor, self).__init__(*args, **kwargs)
        self.name = name

class SimulationRobotState(AbstractState):
    '''
    Includes full state necessary for this robot, including gripper, base, and 
    arm position.
    '''
    def __init__(self, robot,
            base_pos=(0,0,0),
            base_rot=(0,0,0,1),
            arm=[],
            gripper=0.):

        self.predicates = []
        self.arm = arm
        self.gripper = 0.
        self.base_pos = base_pos
        self.base_rot = base_rot
        self.robot = robot

class SimulationRobotAction(AbstractAction):
    '''
    Includes the command that gets sent to robot.act()
    '''
    def __init__(self, cmd):
        self.cmd = cmd

class SimulationRobotActor(AbstractActor):
    def __init__(self, robot, *args, **kwargs):
        super(SimulationRobotActor, self).__init__(*args, **kwargs)
        self.robot = robot

class NullPolicy(AbstractPolicy):
  def evaluate(self, world, state, actor=None):
    return SimulationRobotAction(cmd=None)

# =============================================================================
# Helper Fucntions
def GetObjectState(handle):
    '''
    Look up the handle and get its base position and eventually other
    information, if we find that necessary.
    '''
    pos, rot = pb.getBasePositionAndOrientation(handle)
    return SimulationObjectState(handle,
                                 base_pos=pos,
                                 base_rot=rot)

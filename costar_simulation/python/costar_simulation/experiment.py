
import rospy

from gazebo_msgs.srv import DeleteModel
from gazebo_msgs.srv import SetModelConfiguration
from gazebo_msgs.srv import SpawnModel

from std_srvs.srv import Empty as EmptySrv
from std_srvs.srv import EmptyResponse as EmptySrvResponse

class Experiment(object):
    '''
    Spawn objects
    Clean objects
    '''

    def __init__(self, *args, **kwargs):
        pass

    def reset(self):
        raise NotImplementedError('Experiment not defined')


def GetExperiment(experiment, *args, **kwargs):
    return {
            "magnetic_assembly": MagneticAssemblyExperiment,
            "stack": StackExperiment,
            }[experiment](*args, **kwargs)

class MagneticAssemblyExperiment(Experiment):
    '''
    Magnetic assembly sim launches different blocks 
    '''

    def __init__(self, case):
        self.case = case
        self.experiment_file = "magnetic_assembly.launch"

    def reset(self):
        rospy.wait_for_service("gazebo/set_model_configuration")
        configure = rospy.ServiceProxy("gazebo/set_model_configuration", SetModelConfiguration)
        configure(model_name=self.model_name,
                joint_names=self.joint_names,
                joint_positions=self.joint_positions)
        rospy.wait_for_service("gazebo/delete_model")
        if self.uses_gbeam_soup:
            delete_model = rospy.ServiceProxy("gazebo/delete_model", DeleteModel)
            delete_model("gbeam_soup")
        res = subprocess.call([
            "roslaunch",
            "costar_simulation",
            self.experiment_file,
            "experiment:=%s"%self.case])
        res = subprocess.call(["rosservice","call","publish_planning_scene"])


class StackExperiment(Experiment):
    '''
    Create a stack of blocks more or less at random
    Also probably reset the robot's joint states
    '''

    def reset(self):
        pass

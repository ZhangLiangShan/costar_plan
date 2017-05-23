"""Code for building the input for the prediction model."""

import os
import errno

import numpy as np
import tensorflow as tf
import re

from tensorflow.python.platform import flags
from tensorflow.python.platform import gfile
from tensorflow.python.ops import data_flow_ops
from keras.utils import get_file

import moviepy.editor as mpy

tf.flags.DEFINE_string('data_dir',
                       os.path.join(os.path.expanduser("~"),
                                    '.keras', 'datasets', 'grasping'),
                       """Path to dataset in TFRecord format
                       (aka Example protobufs) and feature csv files.""")
tf.flags.DEFINE_string('gif_dir',
                       os.path.join(os.path.expanduser("~"),
                                    '.keras', 'datasets', 'grasping', 'images_extracted_grasp'),
                       """Path to output image gifs for visualization.""")
tf.flags.DEFINE_integer('batch_size', 25, 'batch size per compute device')
tf.flags.DEFINE_integer('sensor_image_width', 640, 'Camera Image Width')
tf.flags.DEFINE_integer('sensor_image_height', 512, 'Camera Image Height')
tf.flags.DEFINE_integer('sensor_color_channels', 3,
                        'Number of color channels (3, RGB)')
tf.flags.DEFINE_string('grasp_download', None,
                       """Filter the subset of 1TB Grasp datasets to download.
                       None by default. 'all' will download all datasets.
                       '052' and '057' will download the small starter datasets.
                       '102' will download the dataset with 102 features,
                       around 110 GB.
                       See https://sites.google.com/site/brainrobotdata/home
                       for a full listing.""")

FLAGS = flags.FLAGS


def mkdir_p(path):
    # http://stackoverflow.com/questions/600268/mkdir-p-functionality-in-python
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


class GraspDataset:
    """Google Grasping Dataset - about 1TB total size
        https://sites.google.com/site/brainrobotdata/home/grasping-dataset

        Data from https://arxiv.org/abs/1603.02199

        Downloads to `~/.keras/datasets/grasping` by default.

        grasp_listing.txt lists all the files in all grasping datasets;
        *.csv lists the number of features, the number of grasp attempts, and all feature names;
        *.tfrecord and *.tfrecord*-of-* is the actual data stored in the tfrecord.

    """
    def __init__(self, data_dir=None):
        if data_dir is None:
            data_dir = FLAGS.data_dir
        self.data_dir = data_dir

    def download(self, dataset=''):
        '''Google Grasping Dataset - about 1TB total size
        https://sites.google.com/site/brainrobotdata/home/grasping-dataset

        Downloads to `~/.keras/datasets/grasping` by default.
        Includes grasp_listing.txt with all files in all datasets;
        the feature csv files which specify the dataset size,
        the features (data channels), and the number of grasps;
        and the tfrecord files which actually contain all the data.

        # Arguments

            dataset: The name of the dataset to download, downloads all by default
                with the '' parameter, 102 will download the 102 feature dataset
                found in grasp_listing.txt.

        # Returns

           list of paths to the downloaded files

        '''
        if dataset is None:
            return []
        if dataset is 'all':
            dataset = ''
        mkdir_p(FLAGS.data_dir)
        print('Downloading datasets to: ', FLAGS.data_dir)
        listing_url = 'https://sites.google.com/site/brainrobotdata/home/grasping-dataset/grasp_listing.txt'
        grasp_listing_path = get_file('grasp_listing.txt', listing_url, cache_subdir=self.data_dir)
        grasp_files = np.genfromtxt(grasp_listing_path, dtype=str)
        url_prefix = 'https://storage.googleapis.com/brain-robotics-data/'
        files = [get_file(fpath.split('/')[-1], url_prefix + fpath, cache_subdir=self.data_dir)
                 for fpath in grasp_files
                 if '_' + dataset in fpath]
        return files

    def get_feature_csv_file_paths(self):
        """List feature csv files with full paths in the data_dir.
        Feature csv files identify each dataset, the size, and its data channels.
        One example is: 'features_102.csv'
        """
        return gfile.Glob(os.path.join(os.path.expanduser(self.data_dir), '*.csv*'))

    @staticmethod
    def get_grasp_tfrecord_info(feature_csv_file):
        """
        # Arguments

            feature_csv_file: path to the feature csv file for this dataset

        # Returns
            features: complete list of all features for this dataset aka tfrecord group
            feature_count: total number of features
            attempt_count: total number of grasp attempts
            tfrecord_paths: paths to all tfrecords for this dataset
        """
        features = np.genfromtxt(feature_csv_file, dtype=str)
        feature_count = int(features[0])
        attempt_count = int(features[1])
        features = features[2:]
        # note that the tfrecords are often named '*{}.tfrecord*-of-*'
        tfrecord_paths = gfile.Glob(os.path.join(os.path.expanduser(FLAGS.data_dir), '*{}.tfrecord*'.format(feature_count)))
        return features, feature_count, attempt_count, tfrecord_paths

    @staticmethod
    def get_time_ordered_features(features, step='all', feature_type='/image/encoded'):
        """Get list of all image features ordered by time, features are identified by a string path.
            See https://docs.google.com/spreadsheets/d/1GiPt57nCCbA_2EVkFTtf49Q9qeDWgmgEQ6DhxxAIIao/edit#gid=0
            for mostly correct details.
            These slides also help make the order much more clear:
            https://docs.google.com/presentation/d/13RdgkZQ_neqeXwYU3at2fP4RLl4qb1r74CTehq8d_Qc/edit?usp=sharing
            Also see the downloaded grasp_listing.txt and feature_*.csv files that the downloader puts
            into ~/.keras/datasets/grasping by default.
        # Arguments

            features: list of feature TFRecord strings
            step: string indicating which parts of the grasp sequence should be returned.
                Options are 'all', 'test_success' with the pre and post drop images,
                'view_clear_scene' shows the clear scene before the arm enters the camera view.
                'move_to_grasp' are the up to 10 steps when the gripper is moving towards an object
                    it will try to grasp, also known as the grasp phase.
                'close_gripper' when the gripper is actually closed.
                'camera' get camera intrinsics matrix and/or camera_T_base transform
                'robot' get robot name

            feature_type: feature data type, one of
                'transforms/base_T_endeffector/vec_quat_7'		A pose is a 6 degree of freedom rigid transform represented with 7 values:
                                                                    vector (x, y, z) and quaternion (x, y, z, w).
                                                                A pose is always annotated with the target and source frames of reference.
                                                                For example, base_T_camera is a transform that takes a point in the camera frame
                                                                of reference and transforms it to the base frame of reference.
                'camera/transforms/camera_T_base/matrix44'        Same as base_T_endeffector but from the camera center to the robot base
                'commanded_pose'		Commanded pose is the input to the inverse kinematics computation, which is used to determine desired joint positions.
                'reached_pose'		Pose calculated by forward kinetics from current robot state in status updates.
                'joint/commanded_torques'		Commanded torques are the torque values calculated from the inverse kinematics
                                            of the commanded pose and the robot driver.
                'joint/external_torques'		External torques are torques at each joint that are a result of gravity and other external forces.
                                            These values are reported by the robot status query.
                'joint/positions'		Robot joint positions as reported by the robot status query.
                'joint/velocities'		Robot joint velocities as reported by the robot status query.
                'depth_image'		Depth image is encoded as an RGB PNG image where the RGB 24-bit value is an integer depth with scale 1/256 of a millimeter.
                '/image/encoded' Camera RGB images are stored in JPEG format, be careful not to mismatch on depth_image/encoded.
                'params'		This is a simplified representation of a commanded robot pose and gripper status.
                            These are the values that were solved for in the network, the output of the Cross Entropy Method.
                'name'        A string indicating the name of the robot
                'status'      Unknown, but only feature is 'gripper/status', so probably an indicator of how open/closed the gripper is.

        # Returns

           list of image features organized by time step in a single grasp
        """
        matching_features = []

        def match_feature(features, feature_name_regex, feature_type='', exclude_substring=None, exclude_regex=None):
            """Get first feature from the list that meets requirements.
            Used to ensure correct ordering and easy selection of features.
            some silly tricks to get the feature names in the right order while
            allowing variation between the various datasets.
            For example, we need to make sure 'grasp/image/encoded comes'
            before grasp/0/* and post_grasp/*, but with a simple substring
            match 'grasp/', all of the above will be matched in the wrong order.
            `r'/\\d+/'` (single backslash) regex will exclude /0/, /1/, and /10/.
            """
            for ifname in features:
                if (bool(re.search(feature_name_regex, ifname)) and  # feature name matches
                        ((exclude_substring is None) or (exclude_substring not in ifname)) and
                        ((exclude_regex is None) or not bool(re.search(exclude_regex, ifname))) and
                        (feature_type in ifname)):
                    return [str(ifname)]
            return []
        if step in ['camera', 'all', '']:
            # the r'^ in r'^camera/' makes sure the start of the string matches
            matching_features.extend(match_feature(features, r'^camera/', feature_type))
        if step in ['robot', 'all', '']:
            matching_features.extend(match_feature(features, r'^robot/', feature_type))
        # r'/\d/' is a regex that will exclude things like /0/, /1/, through /10/
        # this is the first pre grasp image, even though it is called grasp
        if step in ['view_clear_scene', 'all', '']:
            matching_features.extend(match_feature(features, r'^initial/', feature_type))
            matching_features.extend(match_feature(features, r'^approach/', feature_type))
            matching_features.extend(match_feature(features, r'^approach_sequence/', feature_type))
            matching_features.extend(match_feature(features, r'^pregrasp/', feature_type, 'post', r'/\d+/'))
            matching_features.extend(match_feature(features, r'^grasp/', feature_type, 'post', r'/\d+/'))

        # up to 11 grasp steps in the datasets
        if step in ['move_to_grasp', 'all', '']:
            max_grasp_steps = 11  # 0 through 10
            for i in range(max_grasp_steps):
                matching_features.extend(match_feature(features, r'^grasp/{}/'.format(i), feature_type, 'post'))
        # closing the gripper
        if step in ['close_gripper', 'all', '']:
            matching_features.extend(match_feature(features, r'^gripper/', feature_type, 'post'))
            # Not totally sure, but probably the transforms and angles from as the gripper is closing (might shift a bit)
            matching_features.extend(match_feature(features, r'^gripper_sequence/', feature_type, 'post'))
            # Withdraw the closed gripper from the bin vertically upward, roughly 10 cm above the bin surface.
            matching_features.extend(match_feature(features, r'^withdraw_sequence/', feature_type))
            matching_features.extend(match_feature(features, r'^post_grasp/', feature_type))

        if step in ['test_success', 'all', '']:
            matching_features.extend(match_feature(features, r'^present/', feature_type))
            matching_features.extend(match_feature(features, r'^present_sequence/', feature_type))
            # After presentation (or after withdraw, if present is skipped),
            # the object is moved to a random position about 10 cm above the bin to drop the object.
            matching_features.extend(match_feature(features, r'^raise/', feature_type))
            # Open the gripper and drop the object (if any object is held) into the bin.
            matching_features.extend(match_feature(features, r'^drop/', feature_type))
            # Images recorded after withdraw, raise, and the drop.
            matching_features.extend(match_feature(features, r'^post_drop/', feature_type))
        return matching_features

    @staticmethod
    def tfrecord_minibatch(tfrecord_path_glob_pattern,
                           gpu_device_count,
                           batch_size,
                           parse_example_proto_fn=None,
                           preprocessing_fn=None,
                           create_data_and_label_op_lists_fn=None,
                           random_seed=301,
                           parallelism=64,
                           buffer_size=10000):
        """TODO: High Performance Distributed Training Batches - Adapt for grasping dataset & then broader reuse
        see https://github.com/tensorflow/benchmarks/blob/master/scripts/tf_cnn_benchmarks/preprocessing.py
        """
        with tf.name_scope('batch_processing'):
            # Split the data among all the GPU devices
            if batch_size % gpu_device_count != 0:
                raise ValueError(
                    ('batch_size must be a multiple of gpu_device_count: '
                     'batch_size %d, gpu_device_count: %d') %
                    (batch_size, gpu_device_count))
                batch_size_per_device = batch_size // gpu_device_count
            images = [[] for i in range(gpu_device_count)]
            labels = [[] for i in range(gpu_device_count)]
            record_input = data_flow_ops.RecordInput(
                file_pattern=tfrecord_path_glob_pattern,
                seed=random_seed,
                parallelism=parallelism,
                buffer_size=buffer_size,
                batch_size=batch_size,
                name='record_input')
            records = record_input.get_yield_op()
            records = tf.split(records, batch_size, 0)
            records = [tf.reshape(record, []) for record in records]
            feature_op_dicts = []
            preprocessed_data_ops = []
            for device_i in xrange(batch_size):
                protobuf = records[i]
                feature_op_dict = parse_example_proto_fn(protobuf)
                preprocessed_data = None
                if preprocessing_fn is not None:
                    # thread_id should be distortion_method_id, and calculated later
                    preprocessed_data = preprocessing_fn(feature_op_dict, i)
                device_index = i % gpu_device_count
                feature_op_dict[device_index].append(image)
                labels[device_index].append(label_index)
            label_index_batch = [None] * gpu_device_count
            return create_data_and_label_op_lists_fn(feature_op_dicts, preprocessed_data_ops, gpu_device_count)

    @staticmethod
    def parse_grasp_attempt_protobuf(features_complete_list, serialized_grasp_attempt_proto):
        """Parses an Example protobuf containing a training example of an image.
        The output of the build_image_data.py image preprocessing script is a dataset
        containing serialized Example protocol buffers. Each Example proto contains
        the fields described in get_time_ordered_features.
        Args:
            example_serialized: scalar Tensor tf.string containing a serialized
            Example protocol buffer.

            list of tensors corresponding to images, actions, and states. Each images
            tensor is 4D, batch x height x width x channels. The state and
            action tensors are 3D, batch x time x dimension.
        Returns:
            feature_op_dict: dictionary of Tensors for every feature,
                use `get_time_ordered_features` to select the subsets you need.
        """
        # Dense features in Example proto.
        num_grasp_steps_name = 'num_grasp_steps'
        camera_to_base_name = 'camera/transforms/camera_T_base/matrix44'
        camera_intrinsics_name = 'camera/intrinsics/matrix33'

        # setup one time features like the camera and number of grasp steps
        features_dict = {
            num_grasp_steps_name: tf.FixedLenFeature([1], tf.string),
            camera_to_base_name: tf.FixedLenFeature([1], tf.float32),
            camera_intrinsics_name: tf.FixedLenFeature([1], tf.float32)
        }

        # load all the images
        ordered_image_feature_names = GraspDataset.get_time_ordered_features(features_complete_list)
        features_dict.update({image_name: tf.FixedLenFeature([1], tf.string) for image_name in ordered_image_feature_names})

        # load all vec/quat base to end effector transforms
        base_to_endeffector_names = GraspDataset.get_time_ordered_features(
            features_complete_list,
            feature_type='transforms/base_T_endeffector/vec_quat_7'
            )
        features_dict.update({x_form: tf.FixedLenFeature([1], tf.float32) for x_form in base_to_endeffector_names})

        # load transforms that were modified for their network from the original paper
        transform_adapted_for_network = GraspDataset.get_time_ordered_features(
            features_complete_list,
            feature_type='params'
            )
        features_dict.update({x_form: tf.FixedLenFeature([1], tf.float32) for x_form in transform_adapted_for_network})

        feature_op_dict = tf.parse_single_example(serialized_grasp_attempt_proto, features=features_dict)
        # # Consider using feature_phase_dict_dict if it is convenient,
        # # but move it to the class or something
        # feature_phase_dict_dict = {
        #     'robot': {
        #         'name': 'robot/name'
        #     },
        #     'camera': {
        #         'camera_to_base_name': camera_to_base_name,
        #         'camera_intrinsics_name': camera_intrinsics_name
        #     },

        #     'view_clear_scene': {

        #     },

        #     'test_success': {

        #     },

        #     'move_to_grasp': {
        #         'base_to_endeffector_names': move_to_grasp_base_to_endeffector_names,

        #     }
        # }
        return feature_op_dict

    def build_image_input(self, sess, feature_csv_file, train=True, novel=True):
        """Create input tfrecord tensors.

        Args:
        novel: whether or not to grab novel or seen images.
        Returns:
        list of tensors corresponding to images. The images
        tensor is 5D, batch x time x height x width x channels.
        Raises:
        RuntimeError: if no files found.
        """
        features_complete_list, feature_count, attempt_count, tfrecord_paths = self.get_grasp_tfrecord_info(feature_csv_file)
        print(tfrecord_paths)
        if not tfrecord_paths:
            raise RuntimeError('No tfrecords found for {}.'.format(feature_csv_file))
        filename_queue = tf.train.string_input_producer(tfrecord_paths, shuffle=False)
        reader = tf.TFRecordReader()
        _, serialized_example = reader.read(filename_queue)

        image_seq = []

        num_grasp_steps_name = 'num_grasp_steps'
        images_feature_names = self.get_time_ordered_features(features_complete_list)
        print(images_feature_names)
        features_dict = {image_name: tf.FixedLenFeature([1], tf.string) for image_name in images_feature_names}
        features_dict[num_grasp_steps_name] = tf.FixedLenFeature([1], tf.string)
        features_op_dict = tf.parse_single_example(serialized_example, features=features_dict)

        for image_name in images_feature_names:
            image_buffer = tf.reshape(features_op_dict[image_name], shape=[])
            image = tf.image.decode_jpeg(image_buffer, channels=FLAGS.sensor_color_channels)
            image.set_shape([FLAGS.sensor_image_height, FLAGS.sensor_image_width, FLAGS.sensor_color_channels])

            image = tf.reshape(image, [1, FLAGS.sensor_image_height, FLAGS.sensor_image_width, FLAGS.sensor_color_channels])
            # image = tf.image.resize_bicubic(image, [IMG_HEIGHT, IMG_WIDTH])
            image_seq.append(image)

        image_seq = tf.concat(image_seq, 0)

        image_batch = tf.train.batch(
            [image_seq],
            FLAGS.batch_size,
            num_threads=1,
            capacity=1)

        return image_batch

    def npy_to_gif(self, npy, filename):
        clip = mpy.ImageSequenceClip(list(npy), fps=2)
        clip.write_gif(filename)

    def create_gif(self, sess):
        """ Create gifs of all datasets
        """
        mkdir_p(FLAGS.gif_dir)
        feature_csv_files = self.get_feature_csv_file_paths()
        for feature_csv_file in feature_csv_files:
            train_image_tensor = self.build_image_input(sess, feature_csv_file)
            tf.train.start_queue_runners(sess)
            sess.run(tf.global_variables_initializer())
            train_videos = sess.run(train_image_tensor)

            for i in range(FLAGS.batch_size):
                video = train_videos[i]
                gif_filename = os.path.basename(feature_csv_file)[:-4] + '_grasp_' + str(i) + '.gif'
                gif_path = os.path.join(FLAGS.gif_dir, gif_filename)
                self.npy_to_gif(video, gif_path)


if __name__ == '__main__':
    with tf.Session() as sess:
        gd = GraspDataset()
        gd.download(FLAGS.grasp_download)
        gd.create_gif(sess)


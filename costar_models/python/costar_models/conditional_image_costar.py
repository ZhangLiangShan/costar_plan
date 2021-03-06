from __future__ import print_function

import keras.backend as K
import keras.losses as losses
import keras.optimizers as optimizers
import numpy as np

from keras.callbacks import ModelCheckpoint
from keras.layers.advanced_activations import LeakyReLU
from keras.layers import Input, RepeatVector, Reshape
from keras.layers.embeddings import Embedding
from keras.layers.merge import Concatenate, Multiply
from keras.losses import binary_crossentropy
from keras.models import Model, Sequential
from keras.optimizers import Adam
from matplotlib import pyplot as plt

from .robot_multi_models import *
from .mhp_loss import *
from .loss import *
from .conditional_image import ConditionalImage
from .multi import *
from .costar import *
from .callbacks import *

class ConditionalImageCostar(ConditionalImage):

    def __init__(self, *args, **kwargs):
        super(ConditionalImageCostar, self).__init__(*args, **kwargs)
        self.PredictorCb = ImageWithFirstCb

    def _makeModel(self, image, *args, **kwargs):

        img_shape = image.shape[1:]
        img_size = 1.
        for dim in img_shape:
            img_size *= dim
        gripper_size = 1
        arm_size = 6

        # =====================================================================
        # Load the image decoders
        img_in = Input(img_shape, name="predictor_img_in")
        img0_in = Input(img_shape, name="predictor_img0_in")
        #arm_in = Input((arm_size,))
        #gripper_in = Input((gripper_size,))
        #arm_gripper = Concatenate()([arm_in, gripper_in])
        label_in = Input((1,))
        ins = [img0_in, img_in]

        encoder = MakeImageEncoder(self, img_shape)
        decoder = MakeImageDecoder(self, self.hidden_shape)

        LoadEncoderWeights(self, encoder, decoder)

        # =====================================================================
        # Load the arm and gripper representation
        h = encoder([img0_in, img_in])

        if self.validate:
            self.loadValidationModels(arm_size, gripper_size, h0, h)

        next_option_in = Input((1,), name="next_option_in")
        next_option_in2 = Input((1,), name="next_option_in2")
        ins += [next_option_in, next_option_in2]

        # =====================================================================
        # Apply transforms
        y = Flatten()(OneHot(self.num_options)(next_option_in))
        y2 = Flatten()(OneHot(self.num_options)(next_option_in2))

        tform = self._makeTransform() if not self.dense_transform else self._makeDenseTransform()
        tform.summary()
        x = tform([h,y])
        x2 = tform([x,y2])

        image_out, image_out2 = decoder([x]), decoder([x2])

        # Compute classifier on the last transform
        if not self.no_disc:
            image_discriminator = LoadGoalClassifierWeights(self,
                    make_classifier_fn=MakeCostarImageClassifier,
                    img_shape=img_shape)
            #disc_out1 = image_discriminator([img0_in, image_out])
            disc_out2 = image_discriminator([img0_in, image_out2])

        # Create custom encoder loss
        if self.enc_loss:
            loss = EncoderLoss(self.image_encoder, self.loss)
            enc_losses = [loss, loss]
            enc_outs = [x, x2]
            enc_wts = [1e-2, 1e-2]
            img_loss_wt = 1.
        else:
            enc_losses = []
            enc_outs = []
            enc_wts = []
            img_loss_wt = 1.

        # Create models to train
        if self.no_disc:
            disc_wt = 0.
        else:
            disc_wt = 1e-3
        if self.no_disc:
            train_predictor = Model(ins + [label_in],
                    [image_out, image_out2] + enc_outs)
            train_predictor.compile(
                    loss=[self.loss, self.loss,] + enc_losses,
                    loss_weights=[img_loss_wt, img_loss_wt] + enc_wts,
                    optimizer=self.getOptimizer())
        else:
            train_predictor = Model(ins + [label_in],
                    #[image_out, image_out2, disc_out1, disc_out2] + enc_outs)
                    [image_out, image_out2, disc_out2] + enc_outs)
            train_predictor.compile(
                    loss=[self.loss, self.loss, "categorical_crossentropy"] + enc_losses,
                    #loss_weights=[img_loss_wt, img_loss_wt, 0.9*disc_wt, disc_wt] + enc_wts,
                    loss_weights=[img_loss_wt, img_loss_wt, disc_wt] + enc_wts,
                    optimizer=self.getOptimizer())
        train_predictor.summary()

        # Set variables
        self.predictor = None
        self.model = train_predictor


    def _getData(self, image, label, goal_idx, q, gripper, labels_to_name, *args, **kwargs):
        '''
        Parameters:
        -----------
        image: jpeg encoding of image
        label: integer code for which action is being performed
        goal_idx: index of the start of the next action
        q: joint states
        gripper: floating point gripper openness
        labels_to_name: list of high level actions (AKA options)
        '''

        # Null option to be set as the first option
        # Verify this to make sure we aren't loading things with different
        # numbers of available options/high-level actions
        if len(labels_to_name) != self.null_option:
            raise ValueError('labels_to_name must match the number of values in self.null_option. '
                             'self.null_option: ' + str(self.null_option) + ' ' +
                             'labels_to_name len: ' + str(len(labels_to_name)) + ' ' +
                             'labels_to_name values: ' + str(labels_to_name) + ' ' +
                             'If this is expected because you collected a dataset with new actions '
                             'or are using an old dataset, go to  '
                             'costar_models/python/costar_models/util.py '
                             'and change model_instance.null_option and model_instance.num_options '
                             'accordingly in the "costar" features case.')
        self.null_option = len(labels_to_name)
        # Total number of options incl. null
        self.num_options = len(labels_to_name) + 1

        length = label.shape[0]
        prev_label = np.zeros_like(label)
        prev_label[1:] = label[:(length-1)]
        prev_label[0] = self.null_option

        goal_idx = np.min((goal_idx, np.ones_like(goal_idx)*(length-1)), axis=0)

        if not (image.shape[0] == goal_idx.shape[0]):
            print("Image shape:", image.shape)
            print("Goal idxs:", goal_idx.shape)
            print(label)
            print(goal_idx)
            raise RuntimeError('data type shapes did not match')
        goal_label = label[goal_idx]
        goal_image = image[goal_idx]
        goal_image2, goal_label2 = GetNextGoal(goal_image, label)

        # Extend image_0 to full length of sequence
        image0 = image[0]
        image0 = np.tile(np.expand_dims(image0,axis=0),[length,1,1,1])

        lbls_1h = np.squeeze(ToOneHot2D(label, self.num_options))
        lbls2_1h = np.squeeze(ToOneHot2D(goal_label2, self.num_options))
        if self.no_disc:
            return ([image0, image, label, goal_label, prev_label],
                    [goal_image,
                     goal_image2,])
        else:
            return ([image0, image, label, goal_label, prev_label],
                    [goal_image,
                     goal_image2,
                     lbls2_1h,])


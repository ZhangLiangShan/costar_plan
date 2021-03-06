from __future__ import print_function

import os
import sys
import keras
import matplotlib.pyplot as plt
import numpy as np
from .plotting import *

DEFAULT_MODEL_DIRECTORY = os.path.expanduser('~/.costar/models')

class LogCallback(keras.callbacks.Callback):
    def __init__(self,
            name="model",
            model_directory=DEFAULT_MODEL_DIRECTORY):
        self.directory = model_directory
        if not os.path.exists(self.directory):
            os.makedirs(self.directory)
        self.file = open(os.path.join(self.directory,"%s_log.csv"%name),'a+')
        self.file.write("Starting new log session\n")

    def on_epoch_end(self, epoch, logs={}):
        if epoch == 0:
            msg = ""
            for i, key in enumerate(logs.keys()):
                msg += str(key)
                if i < len(logs.keys())-1:
                    msg += ","
            msg += "\n"
            self.file.write(msg)
            self.file.flush()

        msg = ""
        for i, (key, value) in enumerate(logs.items()):
            msg += str(value)
            if i < len(logs.keys())-1:
                msg += ","
        msg += "\n"
        self.file.write(msg)
        self.file.flush()

class PredictorShowImage(keras.callbacks.Callback):
    '''
    Save an image showing what some number of frames and associated predictions
    will look like at the end of an epoch.
    '''

    variables = ["x","y","z","roll","pitch","yaw","gripper"]

    def __init__(self, saved_model, predictor, features, targets,
            model_directory=DEFAULT_MODEL_DIRECTORY,
            name="model",
            num_hypotheses=4,
            verbose=False,
            features_name=None,
            use_prev_option=True,
            noise_dim=64,
            use_noise=False,
            min_idx=0, max_idx=66, step=11):
        '''
        Set up a data set we can use to output validation images.

        Parameters:
        -----------
        predictor: model used to generate predictions
        targets: training target info, in compressed form
        num_hypotheses: how many outputs to expect
        verbose: print out extra information
        '''
        self.saved_model = saved_model
        self.verbose = verbose
        self.use_prev_option = use_prev_option
        self.predictor = predictor
        self.idxs = range(min_idx, max_idx, step)
        self.num = len(self.idxs)
        self.features = [f[self.idxs] for f in features]
        self.targets = [np.squeeze(t[self.idxs]) for t in targets]
        self.num_hypotheses = num_hypotheses
        self.directory = os.path.join(model_directory,'debug')
        self.noise_dim = noise_dim
        self.use_noise = use_noise
        self.files=[]
        if not os.path.exists(self.directory):
            os.makedirs(self.directory)
        self.header = "V(h),max(p(A|H)),o_{i-1}"
        for i in range(self.num_hypotheses):
            for var in self.variables:
                self.header += ",%s%d"%(var,i)
        for var in self.variables:
            self.header += ",observed_%s"%(var)
        for i in range(self.num):
            self.files.append(open(os.path.join(model_directory,"%s_poses_log%d.csv"%(name,i)),'w'))
            self.files[-1].write(self.header+"\n")
            self.files[-1].flush()

    def on_epoch_end(self, epoch, logs={}):
        # take the model and print it out
        imglen = 64*64*3
        if len(self.targets[0].shape) == 2:
            img = self.targets[0][:,:imglen]
        elif len(self.targets[0].shape) == 3:
            assert self.targets[0].shape[1] == 1
            img = self.targets[0][:,0,:imglen]
        else:
            raise RuntimeError('did not recognize big train target shape; '
                               'are you sure you meant to use this callback'
                               'and not a normal image callback?')
        img = np.reshape(img, (self.num,64,64,3))
        features = self.saved_model.addNoiseIfNeeded(self.features)
        data, arms, grippers, label, probs, v = self.predictor.predict(features)
        plt.ioff()
        if self.verbose:
            print("============================")
        for j in range(self.num):
            msg = ''
            name = os.path.join(self.directory,
                    "predictor_epoch%03d_result%d.png"%(epoch+1,j))
            if self.verbose:
                print("----------------")
                print(name)
                print("max(p(o' | x)) =", np.argmax(probs[j]))
                print("v(x) =", v[j])
                print("o_{i-1} = ", self.features[3][j])
                msg += "%f,%d,%d"%(v[j],np.argmax(probs[j]),self.features[3][j])
            fig = plt.figure(figsize=(3+int(1.5*self.num_hypotheses),2))
            plt.subplot(1,2+self.num_hypotheses,1)
            Title('Input Image')
            Show(self.features[0][j])
            plt.subplot(1,2+self.num_hypotheses,2+self.num_hypotheses)
            Title('Observed Goal')
            Show(img[j])
            arm_target = self.targets[0][j,imglen:imglen+6]
            gripper_target = self.targets[0][j,imglen+6]
            for i in range(self.num_hypotheses):
                if self.verbose:
                    print("Arms = ", arms[j][i])
                    print("Gripper = ", grippers[j][i])
                    print("Label = ", np.argmax(label[j][i]))
                for q, q0 in zip(arms[j][i],arm_target):
                    msg += ",%f"%(q-q0)
                msg += ",%f"%(grippers[j][i][0]-gripper_target)
                plt.subplot(1,2+self.num_hypotheses,i+2)
                Show(np.squeeze(data[j][i]))
                Title('Hypothesis %d'%(i+1))
            fig.savefig(name, bbox_inches="tight")
            for q0 in arm_target:
                msg += ",%f"%q0
            msg += ",%f"%gripper_target
            self.files[j].write(msg+"\n")
            self.files[j].flush()
            if self.verbose:
                print("Arm/gripper target =",
                        self.targets[0][j,imglen:imglen+7])
                print("Label target =",
                        np.argmax(self.targets[0][j,(imglen+7):]))
                print("Label target 2 =", np.argmax(self.targets[1][j]))
                if len(self.targets) > 2:
                    print("Value target =", np.argmax(self.targets[2][j]))
            plt.close(fig)

class StateCb(keras.callbacks.Callback):
    '''
    Just predict state information from our models
    '''

    def __init__(self, saved_model, predictor, features, targets,
            model_directory=DEFAULT_MODEL_DIRECTORY,
            name="model",
            features_name=None,
            min_idx=0, max_idx=66, step=11,
            *args, **kwargs):
        '''
        Set up a data set we can use to output validation images.

        Parameters:
        -----------
        predictor: model used to generate predictions (can be different from
                   the model being trained)
        targets: training target info, in compressed form
        verbose: print out extra information
        '''
        self.saved_model = saved_model
        self.predictor = predictor
        self.idxs = range(min_idx, max_idx, step)
        self.num = len(self.idxs)
        #self.features = features[0][self.idxs]
        self.features = [f[self.idxs] for f in features]
        self.targets = [np.squeeze(t[self.idxs]) for t in targets]
        self.directory = os.path.join(model_directory,'debug')
        if not os.path.exists(self.directory):
            os.makedirs(self.directory)

    def on_epoch_end(self, epoch, logs={}):
        features = self.saved_model.addNoiseIfNeeded(self.features)
        res = self.predictor.predict(features)
        show_label = False
        if not isinstance(res, list):
            arm = res
        elif len(res) == 3:
            show_label = True
            arm, gripper, label = res
        elif len(res) == 2:
            arm, gripper = res
        for j in range(self.num):
            print("--------")
            print("%d: arm = %s"%(j,arm[j]))
            print("vs. arm =", self.targets[0][j])
            print("%d: gripper = %s"%(j,gripper[j]))
            print("vs. gripper =", self.targets[1][j])
            if show_label:
                print("%d: label = %s"%(j,np.argmax(label[j])))
                print("vs. label =", np.argmax(self.targets[2][j]))


class ImageCb(keras.callbacks.Callback):
    '''
    Save an image showing what some number of frames and associated predictions
    will look like at the end of an epoch. This will only show the input,
    target, and predicted target image.
    '''

    def __init__(self, saved_model, predictor, features, targets,
            model_directory=DEFAULT_MODEL_DIRECTORY,
            name="model", features_name=None,
            min_idx=0, max_idx=66, step=11, show_idx=0,
            *args, **kwargs):
        '''
        Set up a data set we can use to output validation images.

        Parameters:
        -----------
        predictor: model used to generate predictions (can be different from
                   the model being trained)
        targets: training target info, in compressed form
        verbose: print out extra information
        '''
        self.name = name
        if features_name is None:
            self.features_name = "def"
        else:
            self.features_name = features_name
        self.saved_model = saved_model
        self.predictor = predictor
        self.idxs = range(min_idx, max_idx, step)
        self.num = len(self.idxs)
        self.features = [f[self.idxs] for f in features]
        self.targets = [np.squeeze(t[self.idxs]) for t in targets]
        self.show_idx = show_idx
        self.directory = os.path.join(model_directory,'debug')
        if not os.path.exists(self.directory):
            os.makedirs(self.directory)

    def on_epoch_end(self, epoch, logs={}):
        features = self.saved_model.addNoiseIfNeeded(self.features)
        res = self.predictor.predict(features)
        if isinstance(res, list):
            img = res[0]
            if len(res) == 4:
                img, arm, gripper, label = res
        else:
            img = res
        for j in range(self.num):
            name = os.path.join(self.directory,
                    "%s_%s_epoch%03d_result%d.png"%(self.name,self.features_name,epoch+1,j))
            fig = plt.figure()
            plt.subplot(1,3,1)
            Title('Input Image')
            Show(self.features[self.show_idx][j])
            plt.subplot(1,3,3)
            Title('Observed Goal')
            Show(self.targets[0][j])
            plt.subplot(1,3,2)
            Show(np.squeeze(img[j]))
            Title('Output')
            fig.savefig(name, bbox_inches="tight")
            plt.close(fig)

class ImageWithFirstCb(ImageCb):
    def __init__(self, *args, **kwargs):
        super(ImageWithFirstCb, self).__init__(show_idx=1, *args, **kwargs)

    def on_epoch_end(self, epoch, logs={}):
        features = self.saved_model.addNoiseIfNeeded(self.features)
        res = self.predictor.predict(features)
        if isinstance(res, list):
            img = res[0]
            img2 = res[1]
            if len(res) == 4:
                img, arm, gripper, label = res

        else:
            img = res
        for j in range(self.num):
            name = os.path.join(self.directory,
                    "%s_%s_epoch%03d_result%d.png"%(self.name,self.features_name,epoch+1,j))
            fig = plt.figure()
            plt.subplot(1,5,1)
            Title('Input Image')
            Show(self.features[self.show_idx][j])
            plt.subplot(1,5,4)
            Title('Observed Goal')
            Show(self.targets[0][j])
            plt.subplot(1,5,5)
            Title('Observed Goal 2')
            Show(self.targets[1][j])
            plt.subplot(1,5,2)
            Show(np.squeeze(img[j]))
            Title('Output')
            plt.subplot(1,5,3)
            Show(np.squeeze(img2[j]))
            Title('Output 2')
            fig.savefig(name, bbox_inches="tight")
            plt.close(fig)

class PredictorShowImageOnlyMultiStep(keras.callbacks.Callback):
    '''
    Save an image showing what some number of frames and associated predictions
    will look like at the end of an epoch.
    '''

    def __init__(self, saved_model, predictor, features, targets,
            model_directory=DEFAULT_MODEL_DIRECTORY,
            num_hypotheses=4,
            verbose=False,
            features_name=None,
            noise_dim=64,
            use_noise=False,
            name="model",
            use_prev_option=True,
            min_idx=0, max_idx=66, step=11):
        '''
        Set up a data set we can use to output validation images.

        Parameters:
        -----------
        predictor: model used to generate predictions
        targets: training target info, in compressed form
        num_hypotheses: how many outputs to expect
        verbose: print out extra information
        '''

        if features_name is None:
            self.features_name = "def"
        else:
            self.features_name = features_name
        self.verbose = verbose
        self.saved_model = saved_model
        self.predictor = predictor
        self.idxs = range(min_idx, max_idx, step)
        self.num = len(self.idxs)
        self.features = [f[self.idxs] for f in features]
        self.targets = [np.squeeze(t[self.idxs]) for t in targets]
        self.num_hypotheses = num_hypotheses
        self.directory = os.path.join(model_directory,'debug')
        self.noise_dim = noise_dim
        self.use_noise = use_noise
        if not os.path.exists(self.directory):
            os.makedirs(self.directory)

    def on_epoch_end(self, epoch, logs={}):
        # take the model and print it out
        features = self.saved_model.addNoiseIfNeeded(self.features)
        data = self.predictor.predict(features)
        plt.ioff()
        if self.verbose:
            print("============================")
        for j in range(self.num):
            name = os.path.join(self.directory,
                    "%s_predictor_epoch%03d_result%d.png"%(self.features_name,
                        epoch+1, j))
            fig = plt.figure()#figsize=(3+int(1.5*self.num_hypotheses),2))

            plt.subplot(2,2+self.num_hypotheses,1)
            Title('Input Image')
            Show(self.features[0][j])
            for k in range(2):
                # This counts off rows
                rand_offset = (k*(2+self.num_hypotheses))
                plt.subplot(2,2+self.num_hypotheses,2+self.num_hypotheses+rand_offset)
                Title('Observed Goal')
                Show(np.squeeze(self.targets[k][j]))
                for i in range(self.num_hypotheses):
                    plt.subplot(2,2+self.num_hypotheses,i+2+rand_offset)
                    Show(np.squeeze(data[k][j][i]))
                    Title('Hypothesis %d'%(i+1))

            if self.verbose:
                print(name)
            fig.savefig(name, bbox_inches="tight")
            plt.close(fig)



class PredictorShowImageOnly(keras.callbacks.Callback):
    '''
    Save an image showing what some number of frames and associated predictions
    will look like at the end of an epoch.
    '''

    def __init__(self, saved_model, predictor, features, targets,
            model_directory=DEFAULT_MODEL_DIRECTORY,
            num_hypotheses=4,
            verbose=False,
            noise_dim=64,
            features_name=None,
            use_noise=False,
            name="model",
            use_prev_option=True,
            min_idx=0, max_idx=66, step=11):
        '''
        Set up a data set we can use to output validation images.

        Parameters:
        -----------
        predictor: model used to generate predictions
        targets: training target info, in compressed form
        num_hypotheses: how many outputs to expect
        verbose: print out extra information
        '''
        self.verbose = verbose
        self.saved_model = saved_model
        self.predictor = predictor
        self.idxs = range(min_idx, max_idx, step)
        self.num = len(self.idxs)
        self.features = [f[self.idxs] for f in features]
        self.targets = [np.squeeze(t[self.idxs]) for t in targets]
        self.num_hypotheses = num_hypotheses
        self.directory = os.path.join(model_directory,'debug')
        self.noise_dim = noise_dim
        self.use_noise = use_noise
        self.num_random = 3
        if not os.path.exists(self.directory):
            os.makedirs(self.directory)

    def on_epoch_end(self, epoch, logs={}):
        # take the model and print it out
        imglen = 64*64*3
        if len(self.targets[0].shape) == 2:
            img = self.targets[0][:,:imglen]
        elif len(self.targets[0].shape) == 3:
            assert self.targets[0].shape[1] == 1
            img = self.targets[0][:,0,:imglen]
        else:
            raise RuntimeError('did not recognize big train target shape; '
                               'are you sure you meant to use this callback'
                               'and not a normal image callback?')
        img = np.reshape(img, (self.num,64,64,3))
        data = [0] * self.num_random
        if self.use_noise:
            for k in range(self.num_random):
                z= np.random.random((self.targets[0].shape[0], self.num_hypotheses, self.noise_dim))
                data[k] = self.predictor.predict(self.features + [z])
        else:
            for k in range(self.num_random):
                data[k] = self.predictor.predict(self.features)
        plt.ioff()
        if self.verbose:
            print("============================")
        for j in range(self.num):
            name = os.path.join(self.directory,
                    "image_predictor_epoch%03d_result%d.png"%(epoch+1,j))
            fig = plt.figure()#figsize=(3+int(1.5*self.num_hypotheses),2))
            for k in range(self.num_random):
                rand_offset = (k*(2+self.num_hypotheses))
                plt.subplot(self.num_random,2+self.num_hypotheses,1+rand_offset)
                #print (self.num_random,2+self.num_hypotheses,1+rand_offset)
                Title('Input Image')
                Show(self.features[0][j])
                plt.subplot(self.num_random,2+self.num_hypotheses,2+self.num_hypotheses+rand_offset)
                #print(self.num_random,2+self.num_hypotheses,2+self.num_hypotheses+rand_offset)
                Title('Observed Goal')
                Show(img[j])
                for i in range(self.num_hypotheses):
                    plt.subplot(self.num_random,2+self.num_hypotheses,i+2+rand_offset)
                    #print(self.num_random,2+self.num_hypotheses,2+i+rand_offset)
                    Show(np.squeeze(data[k][i]))
                    Title('Hypothesis %d'%(i+1))
            if self.verbose:
                print(name)
            fig.savefig(name, bbox_inches="tight")
            plt.close(fig)

class PredictorGoals(keras.callbacks.Callback):
    '''
    Save an image showing what some number of frames and associated predictions
    will look like at the end of an epoch.
    '''

    def __init__(self, saved_model, predictor, features, targets,
            model_directory=DEFAULT_MODEL_DIRECTORY,
            num_hypotheses=4,
            verbose=False,
            use_prev_option=True,
            features_name=None,
            noise_dim=64,
            name="model",
            use_noise=False,
            min_idx=0, max_idx=66, step=11):
        '''
        Set up a data set we can use to output validation images.

        Parameters:
        -----------
        predictor: model used to generate predictions
        targets: training target info, in compressed form
        num_hypotheses: how many outputs to expect
        verbose: print out extra information
        '''
        self.verbose = verbose
        self.saved_model = saved_model
        self.predictor = predictor
        self.idxs = range(min_idx, max_idx, step)
        self.num = len(self.idxs)
        self.features = [f[self.idxs] for f in features]
        self.targets = [np.squeeze(t[self.idxs]) for t in targets]
        self.num_hypotheses = num_hypotheses
        self.directory = os.path.join(model_directory,'debug')
        self.noise_dim = noise_dim
        self.use_noise = use_noise
        if not os.path.exists(self.directory):
            os.makedirs(self.directory)

    def on_epoch_end(self, epoch, logs={}):
        # take the model and print it out
        if self.use_noise:
            z= np.random.random((self.targets[0].shape[0], self.num_hypotheses, self.noise_dim))
            arms, grippers, label, probs, v = self.predictor.predict(
                    self.features[:4] + [z])
        else:
            arms, grippers, label, probs, v = self.predictor.predict(
                    self.features[:4])
        plt.ioff()
        if self.verbose:
            print("============================")
        for j in range(self.num):
            name = os.path.join(self.directory,
                    "predictor_epoch%03d_result%d.png"%(epoch+1,j))
            if self.verbose:
                print("----------------")
                print(name)
                print("max(p(o' | x)) =", np.argmax(probs[j]))
                print("v(x) =", v[j])
            for i in range(self.num_hypotheses):
                if self.verbose:
                    print("Arms = ", arms[j][i])
                    print("Gripper = ", grippers[j][i])
                    print("Label = ", np.argmax(label[j][i]))
            if self.verbose:
                print("Arm/gripper target = ",
                        self.targets[0][j,:7])
                print("Label target = ",
                        np.argmax(self.targets[0][j,7:]))

class ModelSaveCallback(keras.callbacks.Callback):
    def __init__(self, model, interval=5):
        self.saved_model = model
        self.interval = interval
        self.best_val_loss = sys.float_info.max

    def on_epoch_end(self, epoch, logs, *args, **kwargs):
        m = self.saved_model

        # Save our status
        path = m.model_directory
        id = m.unique_id
        with open(os.path.join(path, 'status' + id + '.txt'), 'w+') as f:
            f.write(str(epoch+1))

        if epoch % self.interval == 0:

            if 'val_loss' in logs:
                if logs['val_loss'] <= self.best_val_loss:
                    print('val_loss[{}] better than {}. Saving model.'.format(
                        logs['val_loss'], self.best_val_loss))
                    self.best_val_loss = logs['val_loss']
                    print('Model =', m)
                    print('ModelType =', type(m))
                    self.saved_model.save()
                else:
                    print('val_loss[{}] not improved. Not saving'.format(
                        logs['val_loss']))
            else:
                print('Model =', m)
                print('ModelType =', type(m))
                m.save()


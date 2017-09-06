from __future__ import print_function

from keras import layers
from keras import losses
import keras.backend as K
import tensorflow as tf

def mhp_loss_layer(num_classes, num_hypotheses, y_true, y_pred):
    '''
    This is the original code from Christian, for reference.
    '''
    xsum = tf.zeros([1, 1])
    xmin = tf.ones([1, 1])*1e10
    for i in range(0, num_hypotheses):
        cc = losses.categorical_crossentropy(y_true, tf.slice(y_pred, [0,
            num_classes*i], [1, num_classes]))
        xsum += cc
        xmin = tf.minimum(xmin, cc)

    return 0.05 * xsum / num_hypotheses + 0.90 * xmin

class MhpLoss(object):
    '''
    Defines Christian Rupprecht's multiple-hypothesis loss function. This one
    operates on multiple hypothesis samples. This version is designed for use
    with data of one type of output (e.g. an image).

    ArXiv: https://arxiv.org/pdf/1612.00197.pdf

    BibTex:
    @article{rupprecht2016learning,
      title={Learning in an Uncertain World: Representing Ambiguity Through Multiple Hypotheses},
      author={Rupprecht, Christian and Laina, Iro and Baust, Maximilian and Tombari, Federico and Hager, Gregory D and Navab, Nassir},
      journal={arXiv preprint arXiv:1612.00197},
      year={2016}
    }
    '''

    def __init__(self, num_hypotheses, num_outputs):
        '''
        Set up the MHP loss function.

        Parameters:
        -----------
        num_hypotheses: number of targets to generate (e.g., predict 8 possible
                        future images).
        num_outputs: number of output variables per hypothesis (e.g., 64x64x3
                     for a 64x64 RGB image). Currently deprecated, but may be
                     necessary later on.
        '''
        self.num_hypotheses = num_hypotheses
        self.num_outputs = num_outputs
        #for dim in output_shape:
        #    self.num_outputs *= dim
        #self.output_shape = output_shape
        self.__name__ = "mhp_loss"

        self.avg_weight = 0.05
        self.min_weight = 0.90

    def __call__(self, target, pred):
        '''
        Pred must be of size:
            [batch_size=None, num_samples, traj_length, feature_size]
        Targets must be of size:
            [batch_size=None, traj_length, feature_size]

        You can use the tools in "split" to generate this sort of data (for
        targets). The actual loss function is just the L2 norm between each
        point.
        '''

        # Create tensors to hold outputs
        xsum = tf.zeros([1, 1])
        # Small value to make sure min is never 0 or negative
        xmin = tf.ones([1, 1])*1e10
    
        # Loop and apply MSE for all images
        for i in range(self.num_hypotheses):
            target_image = target[:,0]
            pred_image = pred[:,i]
            cc = losses.mean_squared_error(target_image, pred_image)
            #cc = losses.mean_absolute_error(target_image, pred_image)
            xsum += cc
            xmin = tf.minimum(xmin, cc)

        return (self.avg_weight * xsum / self.num_hypotheses) \
                + (self.min_weight * xmin)

class MhpLossWithShape(object):
    '''
    This version of the MHP loss assumes that it will receive multiple outputs.

    '''
    def __init__(self, num_hypotheses, outputs, weights=None):
        self.num_hypotheses = num_hypotheses
        self.outputs = outputs # these are the sizes of the various outputs
        if weights is None:
            self.weights = [1.] * len(self.outputs)
        else:
            self.weights = weights
        assert len(self.weights) == len(self.outputs)
        self.__name__ = "mhp_loss"

    def __call__(self, target, pred):
        '''
        Pred must be of size:
            [batch_size=None, num_samples, traj_length, feature_size]
        Targets must be of size:
            [batch_size=None, traj_length, feature_size]

        Where:
            feature_size = product(self.outputs)
        i.e., the feature size is the sum of the sizes of all outputs. All
        outputs must be pulled in order.
        '''

        xsum = tf.zeros([1, 1])
        xmin = tf.ones([1, 1])*1e10


        for i in range(self.num_hypotheses):

            target_outputs = _getOutputs(target, self.outputs, 0)
            pred_outputs = _getOutputs(pred, self.outputs, i)
            
            # Hold loss for all outputs here.
            cc = tf.zeros([1,1])
            for wt, target_out, pred_out in zip(self.weights, target_outputs, pred_outputs):
                # loss = feature weight * MSE for this feature
                cc += wt * losses.mean_squared_error(target_out, pred_out)

            xsum += (cc / len(self.outputs))
            xmin = tf.minimum(xmin, cc)

        return (0.05 * xsum / self.num_hypotheses) + (0.90 * xmin)

def _getOutputs(state, outputs, i):
    '''
    Split a single output vector into multiple targets. This is a work-around
    because you can't have a Keras loss function that operates over multiple
    outputs.

    Parameters:
    -----------
    state: vector of data to split
    ouputs: dimensionality of each output to retrieve in order
    '''
    idx = 0
    separated_outputs = []
    for output_dim in outputs:
        # Print statement for debugging: shows ranges for each output, which
        # should match the order of provided data.
        #print("from ", idx, "to", idx+output_dim)
        out = state[:,i,idx:idx+output_dim]
        separated_outputs.append(out)
        idx += output_dim
    return separated_outputs

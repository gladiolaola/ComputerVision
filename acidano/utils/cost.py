#!/usr/bin/env python
# -*- coding: utf8 -*-

import theano
import theano.tensor as T
import numpy as np
import math


def GaussianNLL(y, mu, sig):
    """
    Gaussian negative log-likelihood
    Parameters
    ----------
    y   : TensorVariable
    mu  : FullyConnected (Linear)
    sig : FullyConnected (Softplus)
    """
    # Expression ok :
    #   -log(p(x))
    # with p a gaussian
    # BUT NOT WITH TEST VALUES
    nll = 0.5 * T.sum(T.sqr(y - mu) / sig ** 2 + 2 * T.log(sig) +
                      T.log(2 * np.pi), axis=1)

    # Summed along time (i.e. mini-batch)
    return nll


def gaussian_likelihood_diagonal_variance(t, mu, sig, dim):
    """
    Gaussian Likelihood along first dimension
    Parameters
    ----------
    t   : TensorVariable
    mu  : FullyConnected (Linear)
    sig : FullyConnected (Softplus)
    dim : First dimension of the target vector t
    """
    # First clip sig
    sig_clip = T.clip(sig, 1e-40, 1e40)

    # Since the variance matrix is diagonal, normalization term is easier to compute,
    # and calculus overflow can easily be prevented by first summing by 2*pi and taking square
    sig_time_2pi = T.sqrt(sig_clip * 2 * math.pi)

    #######################
    #######################
    # This is the problem... product goes to 0
    normalization_coeff = T.clip(T.prod(sig_time_2pi, axis=0), 1e-40, 1e40)
    #######################
    #######################

    # Once again, fact that sig is diagonal allows for simplifications :
    # term by term division instead of inverse matrix multiplication
    exp_term = (T.exp(- 0.5 * (t-mu) * (t-mu) / sig_clip).sum(axis=0))
    pdf = exp_term / normalization_coeff
    return pdf


def gaussian_likelihood_diagonal_variance_discard_normalization(t, mu, sig, dim):
    """
    Gaussian Likelihood along first dimension
    Parameters
    ----------
    t   : TensorVariable
    mu  : FullyConnected (Linear)
    sig : FullyConnected (Softplus)
    dim : First dimension of the target vector t
    """
    # Once again, fact that sig is diagonal allows for simplifications :
    # term by term division instead of inverse matrix multiplication
    exp_term = (T.exp(- 0.5 * (t-mu) * (t-mu) / sig).sum(axis=0))
    return exp_term


def gaussian_likelihood_scalar(t, mu, sig):
    """
    1D-Gaussian Likelihood
    Parameters
    ----------
    t   : TensorVariable
    mu  : FullyConnected (Linear)
    sig : FullyConnected (Softplus)
    """
    normalization_coeff = T.sqrt(sig * 2 * math.pi)
    exp_term = T.exp(- 0.5 * (t-mu) * (t-mu) / sig)
    return exp_term / normalization_coeff


def KLGaussianGaussian(mu1, sig1, mu2, sig2):
    """
    Re-parameterized formula for KL
    between Gaussian predicted by encoder and Gaussian dist.
    Parameters
    ----------
    mu1  : FullyConnected (Linear)
    sig1 : FullyConnected (Softplus)
    mu2  : FullyConnected (Linear)
    sig2 : FullyConnected (Softplus)
    """
    kl = T.sum(0.5 * (2 * T.log(sig2)
               - 2 * T.log(sig1)
               + (sig1 ** 2 + (mu1 - mu2) ** 2) / sig2 ** 2
               - 1), axis=1)
    return kl


def weighted_binary_cross_entropy_0(pred, target, class_normalization):
    # Weights correspond to the mean number of positive occurences of the class in the training dataset
    # From theano
    # 
    # RESULTS :
    # Accuracy = 40 %
    # Listening : does not seems to respect harmony
    # Weights are structured with always stripes of negatives units for rarely activated notes.
    return -(class_normalization * target * T.log(pred) + (1.0 - target) * T.log(1.0 - pred))


def weighted_binary_cross_entropy_1(pred, target, mean_notes_activation):
    # Weights correspond to the mean number of positive occurences of the class in the training dataset
    # From :
    # Weighted Multi-label Binary Cross-entropy Criterion
    # https://github.com/Nanne/WeightedMultiLabelBinaryCrossEntropyCriterion
    # https://arxiv.org/pdf/1511.02251.pdf
    # From theano
    #
    # RESULTS :
    # Accuracy = 26%
    # Listening : quite good, a bit too much notes, but harmonically consistent
    # Weights : static biases on output still bias toward negative values, but in a more structured way, i.e. some values around the most likely notes are high (event positives)
    # W is highly structured, but past influence is weaker and less contrasted than piano influence
    match = target * T.log(pred) / T.where(mean_notes_activation == 0, 1e-10, mean_notes_activation)
    not_match = (1.0 - target) * T.log(1.0 - pred) / T.where(mean_notes_activation == 1, 1e-10, (1-mean_notes_activation))
    return -(match + not_match)


def weighted_binary_cross_entropy_2(pred, target):
    # Goal is to equally weight positive and negative units
    # Must sum to 1
    # Inpired from
    # The return of ADABOOST.MH: multi-class Hamming trees
    # https://arxiv.org/pdf/1312.6086.pdf
    # From theano
    # 
    # RESULTS :
    # Accuracy = 19%
    # Listening : bad, mainly silence
    # Weights : Quite good and balance, gaussian centered around 0, even for static biases !
    # The problem is just that the activations of the output units are very low, but the structure seems ok
    DIM = pred.shape[1]
    N_on = T.transpose(T.tile(target.sum(axis=1), (DIM, 1))) + 1
    N_off = T.transpose(T.tile((1-target).sum(axis=1), (DIM, 1))) + 1
    # +1 to avoid zero weighting
    return -(target * T.log(pred) / N_on + (1.0 - target) * T.log(1.0 - pred) / N_off)


def weighted_binary_cross_entropy_3(pred, target, mean_notes_activation):
    # Mix of 1 and 2
    # From theano
    #
    # RESULTS
    # Accuracy = 31%
    # Listening : not good, not harmonic, strange ranges...
    # Weights : static biases strongly biased toward negative values
    # W shows that past is neglected
    BATCH_SIZE = pred.shape[0]
    DIM = pred.shape[1]
    N_on_per_batch = T.transpose(T.tile(target.sum(axis=1), (DIM, 1))) + 1
    N_off_per_batch = T.transpose(T.tile((1-target).sum(axis=1), (DIM, 1))) + 1
    mean_notes_on = T.tile(T.where(mean_notes_activation==0, 1e-10, mean_notes_activation), (BATCH_SIZE, 1))
    mean_notes_off = T.tile(T.where(mean_notes_activation==1, 1e-10, (1-mean_notes_activation)), (BATCH_SIZE, 1))
    # +1 to avoid zero weighting
    return - (N_on_per_batch * target * T.log(pred) / mean_notes_on + N_off_per_batch * (1.0 - target) * T.log(1.0 - pred) / mean_notes_off)


def weighted_binary_cross_entropy_4(pred, target, class_normalization):
    # Mix of 0 and 2
    # From theano
    DIM = pred.shape[1]
    BATCH_SIZE = pred.shape[0]
    N_on_per_batch = (T.transpose(T.tile(target.sum(axis=1), (DIM, 1))) + 1)
    N_off_per_batch = (T.transpose(T.tile((1-target).sum(axis=1), (DIM, 1))) + 1)
    class_norm_tile = T.tile(class_normalization, (BATCH_SIZE, 1))
    return -(class_norm_tile * target * T.log(pred) / N_on_per_batch + (1.0 - target) * T.log(1.0 - pred) / N_off_per_batch)


def bp_mll(pred, target):
    # From : Multi-Label Neural Networks with Applications to
    # Functional Genomics and Text Categorization
    # https://cs.nju.edu.cn/zhouzh/zhouzh.files/publication/tkde06a.pdf
    y_i = pred * target
    not_y_i = pred * (1-target)
    matrices, updates = theano.scan(fn=lambda p, t: T.outer(p, t),
                                    sequences=[y_i, not_y_i])
    cost = matrices.sum(axis=(1,2))
    return cost, updates

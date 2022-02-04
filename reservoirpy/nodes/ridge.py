# Author: Nathan Trouvain at 16/08/2021 <nathan.trouvain@inria.fr>
# Licence: MIT License
# Copyright: Xavier Hinaut (2018) <xavier.hinaut@inria.fr>
from functools import partial

import numpy as np
from scipy import linalg

from ..node import Node
from ..types import global_dtype
from .utils import _initialize_readout, _prepare_inputs_for_learning, readout_forward


def _solve_ridge(XXT, YXT, ridge):
    return linalg.solve(XXT + ridge, YXT.T, assume_a="sym")


def partial_backward(readout: Node, X_batch, Y_batch=None):
    X, Y = _prepare_inputs_for_learning(
        X_batch,
        Y_batch,
        bias=readout.input_bias,
        allow_reshape=True,
    )

    xxt = X.T.dot(X)
    yxt = Y.T.dot(X)

    XXT = readout.get_buffer("XXT")
    YXT = readout.get_buffer("YXT")

    # This is not thread-safe, apparently, using Numpy memmap as buffers
    # ok for parallelization then with a lock (see ESN object)
    XXT += xxt
    YXT += yxt


def backward(readout: Node):
    ridge = readout.ridge
    XXT = readout.get_buffer("XXT")
    YXT = readout.get_buffer("YXT")

    input_dim = readout.input_dim
    if readout.input_bias:
        input_dim += 1

    ridgeid = ridge * np.eye(input_dim, dtype=global_dtype)

    Wout_raw = _solve_ridge(XXT, YXT, ridgeid)

    if readout.input_bias:
        Wout, bias = Wout_raw[1:, :], Wout_raw[0, :][np.newaxis, :]
        readout.set_param("Wout", Wout)
        readout.set_param("bias", bias)
    else:
        readout.set_param("Wout", Wout_raw)


def initialize(readout: Node, x=None, y=None, Wout_init=None):

    _initialize_readout(readout, x, y, bias=readout.input_bias, init_func=Wout_init)


def initialize_buffers(readout):
    # create memmaped buffers for matrices X.X^T and Y.X^T pre-computed
    # in parallel for ridge regression
    # ! only memmap can be used ! Impossible to share Numpy arrays with
    # different processes in r/w mode otherwise (with proper locking)
    input_dim = readout.input_dim
    output_dim = readout.output_dim

    if readout.input_bias:
        input_dim += 1

    readout.create_buffer("XXT", (input_dim, input_dim))
    readout.create_buffer("YXT", (output_dim, input_dim))


class Ridge(Node):
    """A single layer of neurons learning with Tikhonov linear regression.

    Output weights of the layer are computed following:

    .. math::

        W_{out} = \\mathbf{YX}^\\top ~ (\\mathbf{XX}^\\top +
        ridge\\mathbf{Id})^{-1}

    Parameters
    ----------
        output_dim: optional
            Number of neurons in the layer, layer output dimension.
            Can be inferred from data at when training if not set.
        ridge: float, defaults to 0.0
            L2 regularization parameter.
        Wout: np.ndarray, optional
            A mmatrix storing connection weights for the readout.
        input_bias: bool, default to True
            If True, a bias term is learned by the linear regression model.
        name: optional
            Node name, by default None.
    """

    def __init__(
        self,
        output_dim=None,
        ridge=0.0,
        Wout=None,
        input_bias=True,
        name=None,
    ):
        super(Ridge, self).__init__(
            params={"Wout": None, "bias": None},
            hypers={"ridge": ridge, "input_bias": input_bias},
            forward=readout_forward,
            partial_backward=partial_backward,
            backward=backward,
            output_dim=output_dim,
            initializer=partial(initialize, Wout_init=Wout),
            buffers_initializer=initialize_buffers,
            name=name,
        )

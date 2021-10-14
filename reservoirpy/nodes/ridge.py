# Author: Nathan Trouvain at 16/08/2021 <nathan.trouvain@inria.fr>
# Licence: MIT License
# Copyright: Xavier Hinaut (2018) <xavier.hinaut@inria.fr>
import numpy as np

from scipy import linalg

from .utils import (readout_forward, _initialize_readout,
                    _prepare_inputs_for_learning)

from ..node import Node
from ..utils.parallel import get_lock
from ..utils.types import global_dtype


def _solve_ridge(XXT, YXT, ridge):
    return linalg.solve(XXT + ridge, YXT.T, assume_a="sym")


def partial_backward(readout: Node, X_batch, Y_batch=None):
    transient = readout.transient

    X, Y = _prepare_inputs_for_learning(X_batch, Y_batch,
                                        transient=transient,
                                        allow_reshape=True)

    xxt = X.T.dot(X)
    yxt = Y.T.dot(X)

    # Lock the memory map to avoid increment from
    # different processes at the same time (Numpy doesn't like that).
    with get_lock():
        readout.set_buffer("XXT", readout.get_buffer("XXT") + xxt)
        readout.set_buffer("YXT", readout.get_buffer("YXT") + yxt)


def backward(readout: Node, X=None, Y=None):
    ridge = readout.ridge
    XXT = readout.get_buffer("XXT")
    YXT = readout.get_buffer("YXT")

    ridgeid = (ridge * np.eye(readout.input_dim + 1, dtype=global_dtype))

    Wout_raw = _solve_ridge(XXT, YXT, ridgeid)

    Wout, bias = Wout_raw[1:, :], Wout_raw[0, :][np.newaxis, :]

    readout.set_param("Wout", Wout)
    readout.set_param("bias", bias)


def initialize(readout: Node,
               x=None,
               y=None):

    _initialize_readout(readout, x, y)


def initialize_buffers(readout):
    # create memmaped buffers for matrices X.X^T and Y.X^T pre-computed
    # in parallel for ridge regression
    # ! only memmap can be used ! Impossible to share Numpy arrays with
    # different processes in r/w mode otherwise (with proper locking)
    readout.create_buffer("XXT", (readout.input_dim + 1,
                                  readout.input_dim + 1))
    readout.create_buffer("YXT", (readout.output_dim,
                                  readout.input_dim + 1))


class Ridge(Node):

    def __init__(self, output_dim=None, ridge=0.0, transient=0,
                 input_bias=True, name=None):
        super(Ridge, self).__init__(params={"Wout": None, "bias": None},
                                    hypers={"ridge": ridge,
                                            "transient": transient,
                                            "input_bias": input_bias},
                                    forward=readout_forward,
                                    partial_backward=partial_backward,
                                    backward=backward,
                                    output_dim=output_dim,
                                    initializer=initialize,
                                    buffers_initializer=initialize_buffers,
                                    name=name)

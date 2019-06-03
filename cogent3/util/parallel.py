#!/usr/bin/env python

import os
import sys
import time
import math
import threading
import multiprocessing
import concurrent.futures as concurrentfutures
import warnings

from cogent3.util.misc import extend_docstring_from

__author__ = "Sheng Han Moses Koh"
__copyright__ = "Copyright 2007-2016, The Cogent Project"
__credits__ = ["Peter Maxwell", "Sheng Han Moses Koh", "Gavin Huttley"]
__license__ = "GPL"
__version__ = "3.0a2"
__maintainer__ = "Gavin Huttley"
__email__ = "gavin.huttley@anu.edu.au"
__status__ = "Alpha"


if os.environ.get('DONT_USE_MPI', 0):
    MPI = None
else:
    try:
        from mpi4py import MPI
        from mpi4py import futures as MPIfutures
    except ImportError:
        MPI = None
    else:
        COMM = MPI.COMM_WORLD
        size = COMM.Get_attr(MPI.UNIVERSE_SIZE)
        if size == 1:
            MPI = None


def generate_seed(use_mpi, seed=None):
    global random_seed
    if use_mpi:
        rank = COMM.Get_rank()
    else:
        process_name = multiprocessing.current_process().name
        rank = int(process_name[-1])
    if seed is not None:
        random_seed = seed + rank
    else:
        random_seed = int(time.time()) + rank

if MPI is not None:
    if COMM.Get_size() > 1:
        generate_seed(True, seed)
    USING_MPI = True
else:
    USING_MPI = False

# Helping ProcessPoolExecutor map unpicklable functions
_FUNCTIONS = {}


class PicklableAndCallable():

    def __init__(self, key):
        self.key = key
        self.func = None

    def __call__(self, *args, **kw):
        if self.func is None:
            try:
                self.func = _FUNCTIONS[self.key]
            except KeyError:
                raise RuntimeError
        return self.func(*args, **kw)


def imap(f, s, max_workers=None, use_mpi=False, seed=None, if_serial='raise'):
    """
    Parameters
    ----------
    f : callable
        function that operates on values in s
    s : iterable
        series of inputs to f
    max_workers : int or None
        maximum number of workers. Defaults to 1-maximum available.
    use_mpi : bool
        use MPI for parallel execution
    seed : int or None
        seed value for random number generators. Defaults to time.time() on
        master node, time.time() + process rank on worked nodes.
    if_serial : str
        action to take if conditions will result in serial execution. Valid
        values are 'raise', 'ignore', 'warn'. Defaults to 'raise'.

    Returns
    -------
    imap is a generator yielding result of f(s[i]), map returns the result
    series
    """
    if_serial = if_serial.lower()
    assert if_serial in ('ignore', 'raise', 'warn'), \
        f"invalid choice '{if_serial}'"
    # If max_workers is not defined, get number of all processes available
    # minus 1 to leave for master process
    if use_mpi:
        if not USING_MPI:
            raise RuntimeError('Cannot use MPI')

        err_msg = "Execution in serial. For parallel MPI execution, use:\n"\
                  " $ mpirun -n 1 <executable script>"

        if COMM.Get_attr(MPI.UNIVERSE_SIZE) == 1 and if_serial == 'raise':
            raise RuntimeError(err_msg)
        elif COMM.Get_attr(MPI.UNIVERSE_SIZE) == 1 and if_serial == 'warn':
            warnings.warn(UserWarning, msg=err_msg)

        if not max_workers:
            max_workers = COMM.Get_attr(MPI.UNIVERSE_SIZE) - 1

        with MPIfutures.MPIPoolExecutor(max_workers=max_workers,
                                        globals=dict(seed=seed)) as executor:
            for result in executor.map(f, s):
                yield result
    else:
        if not max_workers:
            max_workers = multiprocessing.cpu_count() - 1
        assert max_workers < multiprocessing.cpu_count()
        key = id(f)
        _FUNCTIONS[key] = f
        f = PicklableAndCallable(id(f))
        with concurrentfutures.ProcessPoolExecutor(max_workers,
                                        initializer=generate_seed,
                                        initargs=([False, seed])) as executor:
            for result in executor.map(f, s):
                yield result

@extend_docstring_from(imap)
def map(f, s, max_workers=None, use_mpi=False, seed=None, if_serial='raise'):
    return list(imap(f, s, max_workers, use_mpi, seed, if_serial))

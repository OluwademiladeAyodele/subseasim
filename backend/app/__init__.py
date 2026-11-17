"""SubseaSim backend package.

Single-threaded BLAS / OpenMP
-----------------------------
The dynamic solver factorises many SMALL matrices (~100 x 100) every
simulated second. Multithreaded BLAS (OpenBLAS / MKL default: one thread per
core) makes that far slower, not faster: thread start-up and contention
dominate, and with other processes on the machine it was measured at 63 ms
per step versus 1.9 ms single-threaded - enough to stall the simulation loop
and freeze the live display. These defaults must be set before NumPy/SciPy
are imported, which is why they live here (this package is always imported
first). An explicit environment setting still takes precedence.
"""

import os as _os

for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_var, "1")

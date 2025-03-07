################################################################################
# © Copyright 2022 Zapata Computing Inc.
################################################################################
from decimal import Decimal, getcontext
from math import ceil
from typing import Union

# Assumes gridsynth scaling
SYNTHESIS_SCALING = 4
getcontext().prec = 100


def get_num_t_gates_per_rotation(
    per_gate_synthesis_failure_tolerance: Union[float, Decimal]
) -> int:
    return ceil(
        SYNTHESIS_SCALING
        * (1 / Decimal(per_gate_synthesis_failure_tolerance)).log10()
        / Decimal(2).log10()
    )

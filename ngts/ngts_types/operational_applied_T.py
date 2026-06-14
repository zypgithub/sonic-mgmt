from typing import TypedDict

from ngts.nvos_constants import constants_nvos as consts_nv

OperationalAppliedT = TypedDict('OperationalAppliedT', {
    consts_nv.ConfState.OPERATIONAL: dict[str, str],
    consts_nv.ConfState.APPLIED: dict[str, str],
})

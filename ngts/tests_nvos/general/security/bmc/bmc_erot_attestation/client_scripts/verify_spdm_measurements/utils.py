import logging
import sys
from contextlib import contextmanager

LOG_PREFIX = 'VerifySpdmMeasurementsScript'


def log(msg):
    msg = f'[{LOG_PREFIX}] {msg}'
    if 'pytest' in sys.modules:
        logging.info(msg)
    else:
        print(msg)


@contextmanager
def step(name: str):
    # print(f"Starting step: {name}")
    try:
        yield
        log(f"Step '{name}': OK")
    except Exception as e:
        log(f"Step '{name}': FAIL")
        raise

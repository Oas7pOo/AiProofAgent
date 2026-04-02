import logging
import sys

def get_logger(name="AiProofAgent"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
        ch.setFormatter(fmt)
        logger.addHandler(ch)
    logger.propagate = False
    return logger


def setup_root_logger(level=logging.INFO):
    logger = get_logger("AiProofAgent")
    logger.setLevel(level)
    for h in logger.handlers:
        h.setLevel(level)
    return logger

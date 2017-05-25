import logging
import os.path

import common
import faultloc


def start(src):
    assert os.path.isfile(src), badSrc
    assert common.isCompile(src), goodSrc

    #fault localization
    suspStmts = faultloc.analyze(src)
    
    #cegar loop


if __name__ == "__main__":
    import argparse
    aparser = argparse.ArgumentParser("CETI2")
    aparser.add_argument("badSrc", help="bad src")

    
    aparser.add_argument("--seed", "-seed",
                         type=float,
                         help="use this seed")

    logging.basicConfig(level=logging.DEBUG)
    
    from time import time
    args = aparser.parse_args()
    
    import settings
    logging.basicConfig(level=settings.loggingLevel)

    if __debug__: logging.warning("DEBUG MODE ON. Can be slow !")
    seed = round(time(), 2) if args.seed is None else float(args.seed)

    #Run it
    st = time()
    start(args.badSrc)
    logging.info("time {}s".format(time() - st))
    


#import logging
import os.path
import logging
import common as CM

if __name__ == "__main__":
    import argparse
    aparser = argparse.ArgumentParser("CETI2")
    aparser.add_argument("badSrc", help="bad src")

    #0 Error #1 Warn #2 Info #3 Debug #4 Detail
    aparser.add_argument("--log", "-log",
                         help="set logging info",
                         type=int,
                         choices=range(5),
                         default = 2)
    
    aparser.add_argument("--seed", "-seed",
                         type=float,
                         help="use this seed")

    
    from time import time
    args = aparser.parse_args()

    import settings
    settings.loggingLevel = CM.getLogLevel(args.log)
    logger = CM.getLogger(__name__, settings.loggingLevel)
    
    if __debug__:
        logger.warning("DEBUG MODE ON. Can be slow !")
        
    seed = round(time(), 2) if args.seed is None else float(args.seed)

    import alg
    
    #Run it
    st = time()
    alg.start(args.badSrc)
    logger.info("time {}s".format(time() - st))
    


import logging
import os.path

#settings
logger = None


# common #
import subprocess as sp
def vcmd(cmd, inp=None, shell=True):
    proc = sp.Popen(cmd,shell=shell,stdin=sp.PIPE,stdout=sp.PIPE,stderr=sp.PIPE)
    return proc.communicate(input=inp)

def isCompile(src):
    cmd = "gcc {} -o {}.out".format(src, src)
    logging.debug(cmd)
    outMsg, errMsg = vcmd(cmd)
    return not errMsg

def faultloc(goodSrc, badSrc):
    mergedSrc = merge(goodSrc, badSrc)
    cexs = checkEquiv(mergeSrc)
    if not cexs:
        logging.warn("no cexs showing diff btw programs")
        exit(1) 



def start(goodSrc, badSrc):
    assert os.path.isfile(goodSrc), goodSrc
    assert os.path.isfile(badSrc), badSrc
    assert isCompile(goodSrc), goodSrc
    assert isCompile(badSrc), badSrc


    #fault localization
    suspStmts = fautloc(goodSrc, badSrc)
    
    #cegar loop

    


if __name__ == "__main__":
    import argparse
    aparser = argparse.ArgumentParser("CETI2")
    aparser.add_argument("goodSrc", help="good src")    
    aparser.add_argument("badSrc", help="bad src")

    
    aparser.add_argument("--seed", "-seed",
                         type=float,
                         help="use this seed")

    logging.basicConfig(level=logging.DEBUG)
    
    from time import time
    args = aparser.parse_args()
    
    if __debug__: logging.warning("DEBUG MODE ON. Can be slow !")
    seed = round(time(), 2) if args.seed is None else float(args.seed)
    
    #Run it
    st = time()
    start(args.goodSrc, args.badSrc)
    logging.info("time {}s".format(time() - st))
    


import logging
import os.path

import settings
import common


logging.basicConfig(level=settings.loggingLevel)

def analyze(src):
    #instrument
    covSrc = "{}.cov.c".format(src)
    cmd = "./coverage {} {}".format(src, covSrc)
    outMsg, errMsg = common.vcmd(cmd)
    assert not errMsg, errMsg
    assert os.path.isfile(covSrc)

    #compile
    covExe = "{}.exe".format(covSrc)
    cmd = "gcc {} -o {}".format(covSrc, covExe)
    _, errMsg = common.vcmd(cmd)
    assert "error" not in errMsg, errMsg
    assert os.path.isfile(covExe)
    

    # cexs = check(src)
    # if not cexs:
    #     logging.warn("no cexs showing diff btw programs")
    #     exit(1) 

    goodInps = set([(3,3,5), (1,2,3), (3,2,1), (5,5,5), (5, 3 ,4)])
    badInps = set([(2,1,3)])

    pathFile = "{}.path".format(covSrc)
    goodSids, badSids = collectCov(covExe, pathFile, goodInps, badInps)

    goodNRuns, goodFreqs = analyzeCov(goodSids)
    print goodNRuns, goodFreqs

    badNRuns, badFreqs = analyzeCov(badSids)    
    print badNRuns, badFreqs

def collectCov(covExe, pathFile, goodInps, badInps):
    assert os.path.isfile(covExe), covExe
    assert isinstance(goodInps, set) and goodInps, goodInps
    assert isinstance(badInps, set) and badInps, badInps


    def run(inps):
        if os.path.isfile(pathFile):
            os.remove(pathFile)
            
        inpStrs = [" ".join(map(str, inp)) for inp in inps]
        cmds = ["{} {}".format(covExe, inpStr) for inpStr in inpStrs]
        for cmd in cmds:
            outMsg, errMsg = common.vcmd(cmd)
            assert not errMsg

        assert os.path.isfile(pathFile)
        sids = [int(sid) for sid in common.iread(pathFile) if sid]
        return sids

    goodSids = run(goodInps)
    badSids = run(badInps)
    
    return goodSids, badSids

def analyzeCov(sids):
    assert all(isinstance(sid, int) for sid in sids) and sids, sids

    import itertools
    gs = itertools.groupby(sids, key=lambda x: x != 0)    
    ls = (l for k,l in gs if k)

    from collections import Counter
    freqs = Counter()
    
    nruns = 0
    for l in ls:
        nruns += 1
        for sid in l:
            freqs[sid] += 1   

    return nruns, freqs
    
    
    
analyze("programs/MedianBad1.c")    


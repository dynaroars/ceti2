import logging
import os.path
from collections import Counter
import math

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

    goodNRuns, goodFreqs = analyzeCovs(goodSids)
    print goodNRuns, goodFreqs
    assert goodNRuns == len(goodInps)

    badNRuns, badFreqs = analyzeCovs(badSids)
    assert badNRuns == len(badInps)
    print badNRuns, badFreqs

    sscores = analyzeFreqs(goodNRuns, goodFreqs, badNRuns, badFreqs)

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

def analyzeCovs(sids):
    assert all(isinstance(sid, int) for sid in sids) and sids, sids
    freqs = Counter()
    nruns = 0
    
    import itertools
    for k, g in itertools.groupby(sids, key=lambda x: x != 0):
        if not k: continue
        nruns += 1
        for sid in g:
            freqs[sid] += 1   

    return nruns, freqs
    
def analyzeFreqs(goodNRuns, goodFreqs, badNRuns, badFreqs):
    assert goodNRuns >= 1, goodNRuns
    assert isinstance(goodFreqs, Counter), goodFreqs
    
    assert badNRuns >= 1, badNRuns
    assert isinstance(badFreqs, Counter), badFreqs

    sids = set(list(goodFreqs) + list(badFreqs))

    f = lambda sid: algTarantula(goodNRuns, goodFreqs[sid], badNRuns, badFreqs[sid])
    scores = Counter({sid: f(sid) for sid in sids})
    #print scores.most_common(10)
    print scores


    f = lambda sid: algOchiai(goodNRuns, goodFreqs[sid], badNRuns, badFreqs[sid])
    scores = Counter({sid: f(sid) for sid in sids})
    #print scores.most_common(10)
    print scores
    
    return scores
    

def algTarantula(goodNRuns, goodOccurs, badNRuns, badOccurs):
    a = float(badOccurs) / badNRuns
    b = float(goodOccurs) / goodNRuns
    c = a + b
    return a / c if c else 0.0

def algOchiai(goodNruns, goodOccurs, badNRuns, badOccurs):
    c = math.sqrt(badOccurs * goodOccurs)
    return badNRuns / c if c else 0.0
    
analyze("programs/MedianBad1.c")    


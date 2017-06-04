import logging
import os.path
import subprocess as sp

import settings
import common as CM
logger = CM.getLogger(__name__, settings.loggingLevel)

import faultloc

def compile(src):
    assert os.path.isfile(src), src    
    #compile file with llvm                        
    includePath = os.path.join(os.path.expandvars("$KLEE"), "klee/include")
    clangOpts =  "-emit-llvm -c"
    obj = "{}.o".format(src)
    cmd = ("clang -I {} {} {} -o {}"
           .format(includePath, clangOpts, src, obj))
    logger.debug("$ {}".format(cmd))

    outMsg, errMsg = CM.vcmd(cmd)
    assert not outMsg, outMsg
    assert "clang" not in errMsg and "error" not in errMsg, errMsg
    if errMsg:
        logger.debug(errMsg)
    return obj

def execKlee(obj, timeout, outdir):
    assert os.path.isfile(obj), obj
    assert timeout >= 1, timeout
    assert isinstance(outdir, str), outdir
    #timeout = settings.solver_timeout
    kleeOpts = ("-allow-external-sym-calls "
                "-solver-backend=z3 "
                "-max-solver-time={}. "
                "-max-time={}. "
                "-no-output "
                "-output-dir={} "
                .format(timeout, timeout, outdir))
    cmd = "klee {} {}".format(kleeOpts, obj).strip()
    logger.debug("$ {}".format(cmd))
    
    proc = sp.Popen(cmd,shell=True,stdout=sp.PIPE, stderr=sp.STDOUT)
    outMsg, errMsg = proc.communicate()
    assert not errMsg, errMsg
    return outMsg

def parseGBInps(ss):
    """
    Obtain good/bad inputs

    PASS (rb = rc = 296) with input: x 297, y 296, z -211
    PASS (rb = rc = -211) with input: x -212, y -211, z -210
    PASS (rb = rc = -257) with input: x -257, y -210, z -258
    PASS (rb = rc = 0) with input: x 0, y 0, z 0
    PASS (rb = rc = -211) with input: x 0, y -212, z -211
    PASS (rb = rc = -300) with input: x -300, y -300, z -195
    FAIL (rb -211, rc 32) with input: x 32, y -211, z 35
    """

    def parse(s):
        s = s.split(":")[1]  #x 297, y 296, z -211
        s = [s_.split()[1] for s_ in s.split(',')] #[297, 296, -211]
        s = tuple(map(int, s))
        return s

    assert ss, ss

    ignoresDone = ['KLEE: done: total instructions',
                   'KLEE: done: completed paths',
                   'KLEE: done: generated tests']
    
    ignoresRun = [ 
        'KLEE: WARNING: undefined reference to function: printf',
        'KLEE: WARNING ONCE: calling external: printf',
        'KLEE: ERROR: ASSERTION FAIL: 0',
        'KLEE: ERROR: (location information missing) ASSERTION FAIL: 0'
    ]
    
    ignoresMiscs = ['KLEE: NOTE: now ignoring this error at this location',
                    'GOAL: ']        

    ss = [s for s in ss.split('\n') if s]
    
    gInps = set(parse(s) for s in ss if "PASS" in s)
    bInps = set(parse(s) for s in ss if "FAIL" in s)

    return gInps, bInps
    

def start(src):
    assert os.path.isfile(src), src
    assert CM.isCompile(src), src

    logger.info("analyzing {}".format(src))

    import tempfile
    tmpdir = tempfile.mkdtemp(dir=settings.tmpdir, prefix="CETI2_")

    import shutil
    mysrc = os.path.join(tmpdir, os.path.basename(src))
    shutil.copyfile(src, mysrc)
    assert os.path.isfile(mysrc), mysrc
    
    
    logger.info("preproc and save ast: {}".format(mysrc))
    preprocSrc = "{}.preproc.c".format(mysrc)
    astFile = "{}.ast".format(mysrc)

    cmd = "./preproc.exe {} {} {} {}".format(
        mysrc, settings.mainQ, settings.correctQ, preprocSrc, astFile)
    logger.debug(cmd)
    
    outMsg, errMsg = CM.vcmd(cmd)
    assert not errMsg, errMsg
    logger.debug(outMsg)    
    assert os.path.isfile(preprocSrc), preprocSrc
    assert os.path.isfile(astFile), astFile

    logger.info("get good/bad inps")
    flSrc = "{}.fl.c".format(mysrc)
    cmd = "./instr.exe {} {} {}".format(flSrc, astFile, settings.maxV)
    logger.debug(cmd)
    outMsg, errMsg = CM.vcmd(cmd)
    assert not errMsg, errMsg
    logger.debug(outMsg)    
    assert os.path.isfile(flSrc), flSrc
    
    obj = compile(flSrc)
    hs = str(hash(flSrc)).replace("-", "_")
    outdir = os.path.join(tmpdir, hs)
    outMsg = execKlee(obj, settings.timeout, outdir)
    goodInps, badInps = parseGBInps(outMsg)

    #write inps to files
    strOfInps = lambda inps: " ".join(map(str, inps))
    strOfInpss = lambda inpss: "\n".join(map(strOfInps, inpss))

    goodInpsFile = os.path.join(tmpdir, "good.inps")
    CM.vwrite(goodInpsFile, strOfInps(goodInps))

    badInpsFile = os.path.join(tmpdir, "bad.inps")
    CM.vwrite(badInpsFile, strOfInps(badInps))
    
    
    logger.info("fault localization")
    #use statistical debugging to find susp stmts
    covSrc = "{}.cov.c".format(mysrc)
    cmd = "./coverage.exe {} {}".format(covSrc, astFile)
    logger.debug(cmd)
    outMsg, errMsg = CM.vcmd(cmd)
    assert not errMsg, errMsg
    logger.debug(outMsg)    
    assert os.path.isfile(covSrc), covSrc

    suspStmts = faultloc.analyze(
        covSrc, goodInps, badInps, settings.faultlocAlg, tmpdir)

    sids = [sid for sid, _ in suspStmts.most_common(3)]
    ssids ='"{}"'.format(" ".join(map(str, sids)))
    cmd = "./spy.exe {} {} {} {}".format(
        astFile, ssids, settings.tplLevel, settings.maxV)
    logger.debug(cmd)
    outMsg, errMsg = CM.vcmd(cmd)
    logger.debug(errMsg)
    logger.debug(outMsg)    
    CM.pause()
    
    return tmpdir


#print goodInps
#print badInps
# goodInps = set([(3,3,5), (1,2,3), (3,2,1), (5,5,5), (5, 3 ,4)])
# badInps = set([(2,1,3)])
    

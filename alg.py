import logging
import os.path
import subprocess as sp
import settings
logging.basicConfig(level=settings.loggingLevel)

import common as CM
import faultloc

def compile(src):
    assert os.path.isfile(src), src    
    #compile file with llvm                        
    includePath = os.path.join(os.path.expandvars("$KLEE"), "klee/include")
    clangOpts =  "-emit-llvm -c"
    obj = "{}.o".format(src)
    cmd = ("clang -I {} {} {} -o {}"
           .format(includePath, clangOpts, src, obj))
    logging.debug("$ {}".format(cmd))

    outMsg, errMsg = CM.vcmd(cmd)
    assert not outMsg, outMsg
    assert "clang" not in errMsg and "error" not in errMsg, errMsg
    if errMsg:
        logging.debug(errMsg)
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
    logging.debug("$ {}".format(cmd))
    
    proc = sp.Popen(cmd,shell=True,stdout=sp.PIPE, stderr=sp.STDOUT)
    outMsg, errMsg = proc.communicate()
    assert not errMsg, errMsg
    return outMsg


def start(src):
    assert os.path.isfile(src), src
    assert CM.isCompile(src), src

    logging.debug("analyzing {}".format(src))

    import tempfile
    tmpdir = tempfile.mkdtemp(dir=settings.tmpdir, prefix="CETI2_")
    tname = os.path.join(tmpdir, os.path.basename(src))
    
    #preproc and save ast
    preprocSrc = "{}.preproc.c".format(tname)
    astFile = "{}.ast".format(tname)

    cmd = "./preproc {} {} {} {}".format(
        src, settings.mainQ, preprocSrc, astFile)
    logging.debug(cmd)
    outMsg, errMsg = CM.vcmd(cmd)
    assert not errMsg, errMsg
    logging.debug(outMsg)    
    assert os.path.isfile(preprocSrc), preprocSrc
    assert os.path.isfile(astFile), astFile


    #use KLEE to get good/bad inps
    flSrc = "{}.fl.c".format(tname)
    cmd = "./instrFL {} {}".format(flSrc, astFile)
    logging.debug(cmd)
    outMsg, errMsg = CM.vcmd(cmd)
    assert not errMsg, errMsg
    logging.debug(outMsg)    
    assert os.path.isfile(flSrc), flSrc

    obj = compile(flSrc)
    outdir = os.path.join(tmpdir, str(hash(flSrc)))
    outMsg = execKlee(obj, settings.timeout, outdir)
    
    goodInps = set([(3,3,5), (1,2,3), (3,2,1), (5,5,5), (5, 3 ,4)])
    badInps = set([(2,1,3)])
    
    
    #fault localization

    
    
    #use statistical debugging to find susp stmts
    covSrc = "{}.cov.c".format(tname)
    cmd = "./coverage {} {}".format(covSrc, astFile)
    logging.debug(cmd)
    outMsg, errMsg = CM.vcmd(cmd)
    assert not errMsg, errMsg
    logging.debug(outMsg)    
    assert os.path.isfile(covSrc), covSrc

    suspStmts = faultloc.analyze(
        covSrc, goodInps, badInps, settings.faultlocAlg, tmpdir)
    
    #cegar loop

    return tmpdir

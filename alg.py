import logging
import os.path

import settings
logging.basicConfig(level=settings.loggingLevel)

import common
import faultloc

def start(src):
    assert os.path.isfile(src), src
    assert common.isCompile(src), src

    logging.debug("analyzing {}".format(src))

    import tempfile
    tmpdir = tempfile.mkdtemp(dir=settings.tmpdir, prefix="CETI2_")
    tname = os.path.join(tmpdir, os.path.basename(src))
    
    #preproc and save ast
    preprocSrc = "{}.preproc.c".format(tname)
    astFile = "{}.ast".format(tname)

    cmd = "./preproc {} {} {}".format(src, preprocSrc, astFile)
    logging.debug(cmd)
    outMsg, errMsg = common.vcmd(cmd)
    assert not errMsg, errMsg
    logging.debug(outMsg)    
    assert os.path.isfile(preprocSrc), preprocSrc
    assert os.path.isfile(astFile), astFile
    
    
    #fault localization
    covSrc = "{}.cov.c".format(tname)
    cmd = "./coverage {} {}".format(covSrc, astFile)
    logging.debug(cmd)
    outMsg, errMsg = common.vcmd(cmd)
    assert not errMsg, errMsg
    logging.debug(outMsg)    
    assert os.path.isfile(covSrc), covSrc

    
    
    #suspStmts = faultloc.analyze(src, settings.faultlocAlg, tmpdir)
    
    #cegar loop

    return tmpdir

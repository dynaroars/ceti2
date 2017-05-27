import logging
import os.path

import settings
logging.basicConfig(level=settings.loggingLevel)

import common
import faultloc

def start(src):
    assert os.path.isfile(src), badSrc
    assert common.isCompile(src), goodSrc

    logging.debug("analyzing {}".format(src))

    import tempfile
    tmpdir = tempfile.mkdtemp(dir=settings.tmpdir, prefix="CETI2_")
    #preproc and save ast
    
    #fault localization
    suspStmts = faultloc.analyze(src, settings.faultlocAlg, tmpdir)
    
    #cegar loop

    return tmpdir

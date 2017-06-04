import logging

import subprocess as sp
def vcmd(cmd, inp=None, shell=True):
    proc = sp.Popen(cmd,shell=shell,stdin=sp.PIPE,
                    stdout=sp.PIPE,stderr=sp.PIPE)
    return proc.communicate(input=inp)

def vwrite(filename, contents, mode='w'):
    with open(filename, mode) as fh:
        fh.write(contents)

def isCompile(src):
    cmd = "gcc {} -o {}.exe".format(src, src)
    outMsg, errMsg = vcmd(cmd)
    return not errMsg

def iread(filename):
    with open(filename, 'r') as fh:
        for line in fh:
            yield line
            
def pause(s=None):
    msg = "Press any key to continue ..." if s is None else s
    try: #python2
        raw_input(msg)
    except NameError:
        input(msg)


def getLogger(name, level):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(level)
    formatter = logging.Formatter("%(name)s:%(levelname)s:%(message)s")
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger

def getLogLevel(level):
    """
    0 => CRITICAL 50
    1 => ERROR 40
    2 => WARNING 30
    3 => INFO 20
    4 => DEBUG 10
    """
    assert level in set(range(5))
    if level == 0:
        return logging.CRITICAL
    elif level == 1:
        return logging.ERROR
    elif level == 2:
        return logging.WARNING
    elif level == 3:
        return logging.INFO
    else:
        return logging.DEBUG



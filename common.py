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
    if 'error:' in errMsg:
        print errMsg
        return False
    else:
        return True

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





#parallel
def getWorkloads(tasks,max_nprocesses,chunksiz):
    """
    >>> wls = getWorkloads(range(12),7,1); wls
    [[0, 1], [2, 3], [4, 5], [6, 7], [8, 9], [10, 11]]


    >>> wls = getWorkloads(range(12),5,2); wls
    [[0, 1], [2, 3], [4, 5], [6, 7], [8, 9, 10, 11]]

    >>> wls = getWorkloads(range(20),7,2); wls
    [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10, 11], [12, 13, 14], [15, 16, 17], [18, 19]]


    >>> wls = getWorkloads(range(20),20,2); wls
    [[0, 1], [2, 3], [4, 5], [6, 7], [8, 9], [10, 11], [12, 13], [14, 15], [16, 17], [18, 19]]
    """

    if __debug__:
        assert len(tasks) >= 1, tasks
        assert max_nprocesses >= 1, max_nprocesses
        assert chunksiz >= 1, chunksiz

    #determine # of processes
    ntasks = len(tasks)
    nprocesses = int(round(ntasks/float(chunksiz)))
    if nprocesses > max_nprocesses:
        nprocesses = max_nprocesses


    #determine workloads 
    cs = int(round(ntasks/float(nprocesses)))
    workloads = []
    for i in range(nprocesses):
        s = i*cs
        e = s+cs if i < nprocesses-1 else ntasks
        wl = tasks[s:e]
        if wl:  #could be 0, e.g., getWorkloads(range(12),7,1)
            workloads.append(wl)

    return workloads

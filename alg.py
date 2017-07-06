import logging
import os.path
import subprocess as sp

import settings
import common as CM
logger = CM.getLogger(__name__, settings.loggingLevel)

import faultloc

class SRun(object):

    @staticmethod
    def compile(src):
        assert os.path.isfile(src), src    
        #compile file with llvm                        
        includePath = os.path.join(os.path.expandvars("$KLEE"), "klee/include")
        clangOpts =  "-emit-llvm -c"
        obj = "{}.o".format(src)
        cmd = ("clang -I {} {} {} -o {}"
               .format(includePath, clangOpts, src, obj))
        logger.debug("$ {}".format(cmd))

        proc = sp.Popen(cmd, shell=True,
                        stdin=sp.PIPE, stdout=sp.PIPE,stderr=sp.PIPE)
        outMsg, errMsg = proc.communicate()

        assert not outMsg, outMsg
        assert "clang" not in errMsg and "error" not in errMsg, errMsg
        if errMsg:
            logger.debug(errMsg)
        return obj

    @staticmethod
    def execKlee(obj, timeout, outdir, opts=[]):
        assert os.path.isfile(obj), obj
        assert timeout >= 1, timeout
        assert isinstance(outdir, str), outdir
        #timeout = settings.solver_timeout
        kleeOpts = ("-allow-external-sym-calls "
                    "-solver-backend=z3 "
                    "-max-solver-time={}. "
                    "-max-time={}. "
                    "-output-dir={} "
                    .format(timeout, timeout, outdir))
        if opts:
            kleeOpts += ' '.join(map(str, opts))
            
        cmd = "klee {} {}".format(kleeOpts, obj).strip()
        logger.debug("$ {}".format(cmd))

        proc = sp.Popen(cmd, shell=True, stdout=sp.PIPE, stderr=sp.STDOUT)
        return proc
    
    @staticmethod
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
    

class Worker(object):
    def __init__(self, wid, src, inpsFile, sid, cid, myid, idxs):
        assert wid >= 0, wid
        assert isinstance(src, str) and os.path.isfile(src), src
        
        self.wid = wid
        self.src = src
        self.inpsFile = inpsFile
        self.sid = sid
        self.cid = cid #template id
        self.myid = myid
        self.idxs = idxs

        self.sidxs = " ".join(map(str,idxs))

    def transform(self):
        #call ocaml prog to transform file

        xinfo = "t{}_z{}_c{}".format(self.cid, len(self.idxs), self.myid)
        logger.debug('worker {}: transform {} sid {} tpl {} xinfo {} idxs {} ***'
                     .format(self.wid, self.src, self.sid,
                             self.cid, xinfo, self.idxs))

        cmd = ('./modify.exe {} {} {} {} "{}" {} {}'
               .format(self.src, self.inpsFile,
                       self.sid, self.cid, self.sidxs, xinfo, settings.maxV))
                       
        logger.debug("$ {}".format(cmd))
        proc = sp.Popen(cmd,shell=True,stdin=sp.PIPE,stdout=sp.PIPE,stderr=sp.PIPE)
        rs,rsErr = proc.communicate()

        #assert not rs, rs
        logger.debug(rsErr[:-1] if rsErr.endswith("\n") else rs_err)

        if "error" in rsErr or "success" not in rsErr:
            logger.error("worker {}: transform failed '{}' !".format(self.wid, cmd))
            logger.error(rsErr)
            raise AssertionError

        #obtained the created result
        #Alert: Transform success: ## '/tmp/cece_4b2065/q.bug2.c.s1.t5_z3_c1.ceti.c' ##  __cil_tmp4 = (x || y) || z; ## __cil_tmp4 = (x || y) && z;
        
        rsFile, oldStmt, newStmt = "", "", ""

        for line in rsErr.split("\n"):
            if "success:" in line: 
                line = line.split("##")
                assert len(line) == 4, len(line) #must has 4 parts
                line = [l.strip() for l in line[1:]]
                rsFile = line[0][1:][:-1] #remove ' ' from filename
                oldStmt = line[1]
                newStmt = line[2]
                break

        return rsFile, oldStmt, newStmt


    #compile transformed file and run run klee on it
    def klee (self, src):
        logger.debug("worker {}: run klee on {} ***".format(self.wid, src))

        #compile file with llvm
        obj = SRun.compile(src)

        timeout = 10
        outdir = "{}-klee-out".format(obj)
        assert not os.path.exists(outdir) #shutil.rmtree(outdir)
        proc = SRun.execKlee(obj, timeout, outdir)

        ignores_done = ['KLEE: done: total instructions',
                        'KLEE: done: completed paths',
                        'KLEE: done: generated tests']

        ignores_run = [ 
            'KLEE: WARNING: undefined reference to function: printf',
            'KLEE: WARNING ONCE: calling external: printf',
            'KLEE: ERROR: ASSERTION FAIL: 0',
            'KLEE: ERROR: (location information missing) ASSERTION FAIL: 0'
            ]
        import sys
        while proc.poll() is None:
            line = proc.stdout.readline()
            line = line.strip()
            if line:
                sys.stdout.flush()
                if all(x not in line for x in ignores_run + ignores_done):
                    logger.debug('worker {}: stdout: {}'.format(self.wid,line))

                if 'KLEE: HaltTimer invoked' in line:
                    logger.info('worker {}: stdout: {}, timeout {}'
                                .format(self.wid, src, timeout))

                if "KLEE: ERROR" in line and "ASSERTION FAIL: 0" in line: 
                    logger.info('worker {}: found fix for {}'.format(self.wid, src))
                    break

        rs,rsErr = proc.communicate()

        assert not rsErr, rsErr

        ignores_miscs = ['KLEE: NOTE: now ignoring this error at this location',
                         'GOAL: ']

        if rs:
            for line in rs.split('\n'):
                if line:
                    if all(x not in line for x in ignores_done + ignores_miscs):
                        logger.debug('rs: {}'.format(line))

                    #GOAL: uk_0 0, uk_1 0, uk_2 1
                    if 'GOAL' in line:
                        s = line[line.find(':')+1:].strip()
                        s = '{}'.format(s if s else "no uks")
                        return s

        return None
        
    def run(self):
        r = self.transform()
        assert len(r) == 3
        src, oldStmt, newStmt = r

        if src : #transform success
            r = self.klee(src)
            if r:
                return "{}: {} ===> {} ===> {}".format(src, oldStmt, newStmt, r)
        return None


    @classmethod
    def wprocess(cls, wid, src, inpsFile, tasks, V, Q):
        assert wid >= 0, wid
        assert tasks, tasks
        rs = []

        tasks = sorted(tasks,
                       key=lambda(sid, cid, myid, mylist): (cid, len(mylist)))
        print 'mytasks', tasks
        #break after finding a fix
        #noparallel
        #for src, sids, cid, idxs in tasks:

        if not Q: #no parallel
            for sid, cid, myid, idxs in tasks:
                w = cls(wid, src, inpsFile, sid, cid, myid, idxs)
                r = w.run()
                if r: 
                    logger.debug("worker {}: sol found, break !".format(wid))
                    print r
                    rs.append(r)
                    break
            return rs


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

    cmd = "./preproc.exe {} {} {} {} {}".format(
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
    
    obj = SRun.compile(flSrc)
    hs = str(hash(flSrc)).replace("-", "_")
    outdir = os.path.join(tmpdir, hs)
    proc = SRun.execKlee(obj, settings.timeout, outdir, opts = ["-no-output"])
    outMsg, errMsg = proc.communicate()
    assert not errMsg, errMsg

    goodInps, badInps = SRun.parseGBInps(outMsg)
    
    #write inps to files
    def _f(inps, s):
        contents = "\n".join(map(lambda s: " ".join(map(str, s)), inps))
        inpsFile = os.path.join(tmpdir, "{}.inps".format(s))
        CM.vwrite(inpsFile, contents)
        logger.debug("write: {}".format(inpsFile))
        return inpsFile 
    _ = _f(goodInps, "good")
    _ = _f(badInps, "bad")

    inpsFile = _f(list(goodInps) + list(badInps), "allInps")
    
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

    clist = outMsg.split('\n')[-1]
    clist = [c.strip() for c in clist.split(";")]
    clist = [c[1:][:-1] for c in clist] #remove ( )
    clist = [map(int, c.split(',')) for c in clist] 
    tasks = createTasks(clist)
    logger.debug("tasks {}".format(len(tasks)))

    Worker.wprocess(0, astFile, inpsFile, tasks,V=None,Q=None)
    
    return tmpdir


def createTasks(clist):
    tasks = []
    for sid, cid, n in clist:
        rs = getData(cid, n)
        rs = [(sid, cid) + r for r in rs]
        tasks.extend(rs)

    from random import shuffle
    shuffle(tasks)
    return tasks


CID_CONSTS = 1
CID_OPS_PR = 2
CID_VS = 3
def getData(cid, n):
    "return [myid, mylist]"
    import itertools
    rs = []

    #n consts
    if cid == CID_CONSTS:
        rs.append((0, [n]))
    elif cid == CID_OPS_PR:
        for i in range(n):
            rs.append((i, [i+1]))
    #n vars
    elif cid == CID_VS:
        maxCombSiz = 2
        for siz in range(maxCombSiz + 1):
            cs = itertools.combinations(range(n), siz)
            for i,c in enumerate(cs):
                rs.append((i, list(c)))
                
    else:
        raise AssertionError("unknown CID {}".format(cid))
    
    return rs
    
#print goodInps
#print badInps
# goodInps = set([(3,3,5), (1,2,3), (3,2,1), (5,5,5), (5, 3 ,4)])
# badInps = set([(2,1,3)])
    

import logging
import os.path
import subprocess as sp
import shutil
import settings
import common as CM
logger = CM.getLogger(__name__, settings.loggingLevel)

import faultloc

class SRun(object):
    @staticmethod
    def compile(src):
        assert os.path.isfile(src), src
        exeFile = "{}.exe".format(src)
        cmd =("clang {} -o {}".format(src, exeFile))
        outMsg, errMsg = CM.vcmd(cmd)
        assert "Error: " not in errMsg, errMsg
        assert not outMsg, outMsg
        assert os.path.isfile(exeFile)
        
        return exeFile
    
    @staticmethod
    def compileKlee(src):
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
    def __init__(self, wid, src, labelSrc, inpsFile, sid, cid, myid, idxs):
        assert wid >= 0, wid
        assert isinstance(src, str) and os.path.isfile(src), src
        assert isinstance(labelSrc, str) and os.path.isfile(labelSrc), src
        
        self.wid = wid
        self.src = src
        self.inpsFile = inpsFile
        self.sid = sid
        self.cid = cid #template id
        self.myid = myid
        self.idxs = idxs

        self.sidxs = " ".join(map(str,idxs))
        self.labelSrc = labelSrc


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

    
    def klee(self, src):
        #compile transformed file and run run klee on it
        
        logger.debug("worker {}: run klee on {} ***".format(self.wid, src))

        #compile file with llvm
        obj = SRun.compileKlee(src)
        timeout = settings.timeout
        outdir = "{}-klee-out".format(obj)
        if os.path.exists(outdir): shutil.rmtree(outdir)
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

    def repair(self, oldStmt, newStmt, uks):
        #/var/tmp/CETI2_xkj_Bm/MedianBad1.c.s2.t3_z1_c0.ceti.c: m = y; ===> m = uk_0 + uk_1 * x; ===> uk_0 0, uk_1 1
        assert isinstance(oldStmt, str) and oldStmt, oldStmt
        assert isinstance(newStmt, str) and newStmt, newStmt
        assert isinstance(uks, str) and uks, uks


        uksd = dict(ukv.split() for ukv in uks.split(','))
        label = "repairStmt{}:".format(self.sid)
        contents = []
        for l in CM.iread(self.labelSrc):
            l = l.strip()
            if contents and label in contents[-1]:
                assert oldStmt in l
                l = newStmt
                for uk in uksd:
                    l = l.replace(uk, uksd[uk])
                l = l + "// was: {}".format(oldStmt)
            contents.append(l)
        contents = '\n'.join(contents)        
        repairSrc = "{}_repair_{}_{}_{}_{}.c".format(
            self.labelSrc, self.wid, self.cid, self.myid,
            "_".join(map(str, self.idxs)))
        CM.vwrite(repairSrc, contents)
        CM.vcmd("astyle -Y {}".format(repairSrc))
        return repairSrc

    
    def run(self):
        rs = self.transform()
        assert len(rs) == 3
        src, oldStmt, newStmt = rs

        if src : #transform success
            uks = self.klee(src)
            if uks:                
                logger.debug("{}: {} ===> {} ===> {}".format(
                    src, oldStmt, newStmt, uks))
                repairSrc = self.repair(oldStmt, newStmt, uks)
                return repairSrc
            
        return None


    @classmethod
    def wprocess(cls, wid, src, labelSrc, inpsFile, tasks, V, Q):
        assert wid >= 0, wid
        assert tasks, tasks

        tasks = sorted(tasks,
                       key=lambda(sid, cid, myid, mylist): (cid, len(mylist)))

        #break after finding a fix
        #noparallel
        #for src, sids, cid, idxs in tasks:
        rs = []
        if not Q: #no parallel
            for sid, cid, myid, idxs in tasks:
                w = cls(wid, src, labelSrc, inpsFile, sid, cid, myid, idxs)
                r = w.run()
                if r: 
                    logger.debug("worker {}: sol found, break !".format(wid))
                    rs.append(r)
                    break

            return rs
        else:
            for sid, cid, myid, idxs in tasks:
                if V.value > 0:
                    logger.debug("worker {}: sol found, break !".format(wid))
                    break
                else:
                    w = cls(wid, src, labelSrc, inpsFile, sid, cid, myid, idxs)
                    r = w.run()
                    if r: 
                        logger.debug("worker {}: sol found, break !".format(wid))
                        rs.append(r)
                        V.value = V.value + 1

            Q.put(rs)
            return None

class Repair(object):
    def __init__(self, src):

        import tempfile
        self.tmpdir = tempfile.mkdtemp(dir=settings.tmpdir, prefix="CETI2_")

        tsrc = os.path.join(self.tmpdir, os.path.basename(src))
        shutil.copyfile(src, tsrc)
        assert os.path.isfile(tsrc), mysrc

        self.src = tsrc
        
    def start(self):
        #orig stuff
        origSrc = self.src
        origAstFile, goodInps, badInps = self.check(origSrc)
        print goodInps
        print badInps
        origExeFile = SRun.compile(origSrc)
        origCovSrc = self.cov(origSrc, origAstFile)

        if not badInps:
            logger.info("no bad tests: {} seems correct!".format(origSrc))
            return
        
        candSrc = origSrc
        currIter = 0
        while True:
            currIter += 1
            print len(goodInps), len(badInps)
            suspStmts = self.getSuspStmts(
                origCovSrc, settings.topN, goodInps, badInps)
            assert suspStmts, suspStmts
            inpsFile = self.writeInps(goodInps | badInps, "allInps")
            
            candSrcs = self.repair(origSrc, origAstFile, inpsFile, suspStmts)
            if not candSrcs:
                logger.info("no repair found. Stop!")
                break

            logger.info("*** iter {}, candidates {}, goods {}, bads {}"
                        .format(currIter, len(candSrcs),
                                len(goodInps), len(badInps)))
            repairSrc, goods, bads = self.mcheck(candSrcs)
            if repairSrc:
                logger.info("{} seems correct!".format(repairSrc))
                break
            goods, bads = self.checkGBInps(origExeFile, goods | bads)
            if goods:
                for inp in goods: goodInps.add(inp)
            if bads:
                for inp in bads: badInps.add(inp)            

        logger.info("iters: {}, repair found: {}"
                    .format(currIter, repairSrc is not None))


    def writeInps(self, inps, fname):
        contents = "\n".join(map(lambda s: " ".join(map(str, s)), inps))
        inpsFile = os.path.join(self.tmpdir, "{}.inps".format(fname))
        CM.vwrite(inpsFile, contents)
        logger.debug("write: {}".format(inpsFile))
        return inpsFile         

    ### CHECK ###
    def preproc(self, src):
        logger.info("preproc and save ast: {}".format(src))
        preprocSrc = "{}.preproc.c".format(src)  #/a.preproc.c
        astFile = "{}.ast".format(src)   #/a.ast

        cmd = "./preproc.exe {} {} {} {} {}".format(
            src, settings.mainQ, settings.correctQ, preprocSrc, astFile)
        logger.debug(cmd)

        outMsg, errMsg = CM.vcmd(cmd)
        assert not errMsg, errMsg
        logger.debug(outMsg)    
        assert os.path.isfile(preprocSrc), preprocSrc
        assert os.path.isfile(astFile), astFile

        return preprocSrc, astFile

    def instr(self, src, astFile):
        flSrc = "{}.fl.c".format(src)
        logger.info("get good/bad inps: {}".format(flSrc))
        cmd = "./instr.exe {} {} {}".format(flSrc, astFile, settings.maxV)
        logger.debug(cmd)
        outMsg, errMsg = CM.vcmd(cmd)
        assert not errMsg, errMsg
        logger.debug(outMsg)    
        assert os.path.isfile(flSrc), flSrc
        return flSrc

    def getGBInps(self, flSrc):
        "Get good/bad inps from KLEE"
        obj = SRun.compileKlee(flSrc)
        hs = str(hash(flSrc)).replace("-", "_")
        outdir = os.path.join(self.tmpdir, hs)
        proc = SRun.execKlee(obj, settings.timeout, outdir, opts = ["-no-output"])
        outMsg, errMsg = proc.communicate()
        assert not errMsg, errMsg

        goodInps, badInps = SRun.parseGBInps(outMsg)
        return goodInps, badInps

    def checkGBInps(self, exeFile, inps):
        """
        Determine which inp is good/bad wrt to src
        """
        def check(inp):
            cmd = "{} {}".format(exeFile, ' '.join(map(str, inp)))
            outMsg, errMsg = CM.vcmd(cmd)
            assert not errMsg
            return "PASS" in outMsg

        goods, bads = set(), set()
        for inp in inps:
            if check(inp): goods.add(inp)
            else: bads.add(inp)
        return goods, bads

        
    def check(self, src):
        """
        Return good and bad inps.
        if not bad inps then program passes, otherwise program fails
        """
        logger.info("check {}".format(src))
        _, astFile = self.preproc(src)
        flSrc = self.instr(src, astFile)
        goodInps, badInps = self.getGBInps(flSrc)
        return astFile, goodInps, badInps

    def mcheck(self, srcs):
        goodInps, badInps = set(), set()
        for src in srcs:
            _, goodInps_, badInps_ = self.check(src)
            if not badInps_:
                return src, None, None
            else:
                for inp in goodInps_: goodInps.add(inp)
                for inp in badInps_: badInps.add(inp)  #block invalid candidates
        return None, goodInps, badInps
            
            
    ### Fault Loc ###
    def getSuspStmts(self, covSrc, n, goodInps, badInps):
        suspStmts = faultloc.analyze(
            covSrc, goodInps, badInps, settings.faultlocAlg, self.tmpdir)
        suspStmts = [sid for sid, score_ in suspStmts.most_common(n)]
        return suspStmts
    
    def cov(self, src, astFile):
        """
        Create file with cov info (i.e., printf stmts)
        """
        covSrc = "{}.cov.c".format(src)
        logger.info("fault localization: {}".format(covSrc))
        cmd = "./coverage.exe {} {}".format(covSrc, astFile)        
        logger.debug(cmd)
        outMsg, errMsg = CM.vcmd(cmd)
        assert not errMsg, errMsg
        logger.debug(outMsg)    
        assert os.path.isfile(covSrc), covSrc
        return covSrc


    ### Repair ###
    def repair(self, src, astFile, inpsFile, suspStmts, doParallel=True):
        labelSrc, tasks = self.spy(src, astFile, suspStmts)
        
        if doParallel:
            from multiprocessing import (Process, Queue, Value,
                                         current_process, cpu_count)
            Q = Queue()
            V = Value("i",0)

            workloads = CM.getWorkloads(
                tasks, max_nprocesses=cpu_count(), chunksiz=2)
            logger.info("workloads {}: {}"
                        .format(len(workloads), map(len,workloads)))

            workers = [Process(target=Worker.wprocess,
                               args=(i, astFile, labelSrc, inpsFile, wl, V, Q))
                       for i,wl in enumerate(workloads)]

            for w in workers: w.start()
            wrs = []
            for i,_ in enumerate(workers):
                wrs.extend(Q.get())            
        else:
            wrs = Worker.wprocess(0, astFile, labelSrc, inpsFile, tasks,
                                  V=None,Q=None)

        repairSrcs = [r for r in wrs if r]
        logger.info("found {} candidate sols".format(len(repairSrcs)))
        return repairSrcs
    

    def spy(self, src, astFile, sids):
        ssids ='"{}"'.format(" ".join(map(str, sids)))
        labelSrc = "{}.label.c".format(src)        
        cmd = "./spy.exe {} {} {} {} {}".format(
            astFile, labelSrc, ssids, settings.tplLevel, settings.maxV)
        logger.debug(cmd)
        outMsg, errMsg = CM.vcmd(cmd)
        assert os.path.isfile(labelSrc), labelSrc
        logger.debug(outMsg)
        logger.debug(errMsg)
        
        #compute tasks
        clist = outMsg.split('\n')[-1]
        clist = [c.strip() for c in clist.split(";")]
        clist = [c[1:][:-1] for c in clist] #remove ( )
        clist = [map(int, c.split(',')) for c in clist]
        
        tasks = []
        for sid, cid, n in clist:
            rs = self.getData(cid, n)
            rs = [(sid, cid) + r for r in rs]
            tasks.extend(rs)

        from random import shuffle
        shuffle(tasks)
        logger.debug("tasks {}".format(len(tasks)))
        
        return labelSrc, tasks

    @classmethod
    def getData(cls, cid, n):
        "return [myid, mylist]"
        import itertools

        CID_CONSTS = 1
        CID_OPS_PR = 2
        CID_VS = 3
        
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
    

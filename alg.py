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

    
    def klee (self, src):
        #compile transformed file and run run klee on it
        
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

    def repair(self, oldStmt, newStmt, uks):
        #/var/tmp/CETI2_xkj_Bm/MedianBad1.c.s2.t3_z1_c0.ceti.c: m = y; ===> m = uk_0 + uk_1 * x; ===> uk_0 0, uk_1 1
        assert isinstance(oldStmt, str) and oldStmt, oldStmt
        assert isinstance(newStmt, str) and newStmt, newStmt
        assert isinstance(uks, str) and uks, uks


        uksd = dict(ukv.split() for ukv in uks.split(','))
        label = "repairStmt{}:".format(self.sid)
        print self.labelSrc
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
        repairSrc = "{}_repair_{}_{}_{}_{}.c".format(self.labelSrc,self.wid,self.cid,self.myid,self.sidxs)
        CM.vwrite(repairSrc, contents)
        CM.vcmd("astyle -Y {}".format(repairSrc))
        
        print repairSrc
        return repairSrc

    
    def run(self):
        rs = self.transform()
        assert len(rs) == 3
        src, oldStmt, newStmt = rs

        if src : #transform success
            uks = self.klee(src)
            if uks:                
                print "{}: {} ===> {} ===> {}".format(src, oldStmt, newStmt, uks)
                repairSrc = self.repair(oldStmt, newStmt, uks)
                return repairSrc
            
        return None


    @classmethod
    def wprocess(cls, wid, src, labelSrc, inpsFile, tasks, V, Q):
        assert wid >= 0, wid
        assert tasks, tasks
        rs = []

        tasks = sorted(tasks,
                       key=lambda(sid, cid, myid, mylist): (cid, len(mylist)))

        #break after finding a fix
        #noparallel
        #for src, sids, cid, idxs in tasks:

        if not Q: #no parallel
            for sid, cid, myid, idxs in tasks:
                w = cls(wid, src, labelSrc, inpsFile, sid, cid, myid, idxs)
                r = w.run()
                if r: 
                    logger.debug("worker {}: sol found, break !".format(wid))
                    rs.append(r)
                    break

        return rs


class Repair(object):
    def __init__(self, src):
        assert os.path.isfile(src), src
        assert CM.isCompile(src), src
        
        self.src = src
        
        import tempfile
        self.tmpdir = tempfile.mkdtemp(dir=settings.tmpdir, prefix="CETI2_")

        self.mysrc = os.path.join(self.tmpdir, os.path.basename(self.src))
        shutil.copyfile(self.src, self.mysrc)
        assert os.path.isfile(self.mysrc), self.mysrc

    def preproc(self):
        logger.info("preproc and save ast: {}".format(self.mysrc))
        preprocSrc = "{}.preproc.c".format(self.mysrc)  #/a.preproc.c
        astFile = "{}.ast".format(self.mysrc)   #/a.ast

        cmd = "./preproc.exe {} {} {} {} {}".format(
            self.mysrc, settings.mainQ, settings.correctQ, preprocSrc, astFile)
        logger.debug(cmd)

        outMsg, errMsg = CM.vcmd(cmd)
        assert not errMsg, errMsg
        logger.debug(outMsg)    
        assert os.path.isfile(preprocSrc), preprocSrc
        assert os.path.isfile(astFile), astFile

        return preprocSrc, astFile

    def instr(self, astFile):
        flSrc = "{}.fl.c".format(self.mysrc)
        logger.info("get good/bad inps: {}".format(flSrc))
        cmd = "./instr.exe {} {} {}".format(flSrc, astFile, settings.maxV)
        logger.debug(cmd)
        outMsg, errMsg = CM.vcmd(cmd)
        assert not errMsg, errMsg
        logger.debug(outMsg)    
        assert os.path.isfile(flSrc), flSrc
        return flSrc

    def getGBInps(self, flSrc):
        #run klee to get good/bad inps
        obj = SRun.compile(flSrc)
        hs = str(hash(flSrc)).replace("-", "_")
        outdir = os.path.join(self.tmpdir, hs)
        proc = SRun.execKlee(obj, settings.timeout, outdir, opts = ["-no-output"])
        outMsg, errMsg = proc.communicate()
        assert not errMsg, errMsg

        goodInps, badInps = SRun.parseGBInps(outMsg)

        #write inps to files   #good.inps , bad.inps
        def _f(inps, s):
            contents = "\n".join(map(lambda s: " ".join(map(str, s)), inps))
            inpsFile = os.path.join(self.tmpdir, "{}.inps".format(s))
            CM.vwrite(inpsFile, contents)
            logger.debug("write: {}".format(inpsFile))
            return inpsFile 

        inpsFile = _f(list(goodInps) + list(badInps), "allInps")
        return goodInps, badInps, inpsFile

    def cov(self, astFile):
        """
        Create file with cov info (i.e., printf stmts)
        """
        covSrc = "{}.cov.c".format(self.mysrc)
        logger.info("fault localization: {}".format(covSrc))
        cmd = "./coverage.exe {} {}".format(covSrc, astFile)        
        logger.debug(cmd)
        outMsg, errMsg = CM.vcmd(cmd)
        assert not errMsg, errMsg
        logger.debug(outMsg)    
        assert os.path.isfile(covSrc), covSrc
        return covSrc

    def spy(self, astFile, sids):
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
        
        tasks = []
        for sid, cid, n in clist:
            rs = self.getData(cid, n)
            rs = [(sid, cid) + r for r in rs]
            tasks.extend(rs)

        from random import shuffle
        shuffle(tasks)
        logger.debug("tasks {}".format(len(tasks)))
        return tasks

    def label(self, astFile, sids):
        
        ssids ='"{}"'.format(" ".join(map(str, sids)))
        labelSrc = "{}.label.c".format(self.mysrc)

        logger.info("create labels for {} sids {}: {}".format(len(sids), ssids, labelSrc))
        cmd = "./label.exe {} {} {}".format(astFile, ssids, labelSrc)
        logger.debug(cmd)
        outMsg, errMsg = CM.vcmd(cmd)
        assert not errMsg, errMsg
        assert os.path.isfile(labelSrc), labelSrc
        return labelSrc
    
    def start(self):
        logger.info("analyzing {}".format(self.src))
        preprocSrc, astFile = self.preproc()
        flSrc = self.instr(astFile)
        goodInps, badInps, inpsFile = self.getGBInps(flSrc)
        
        covSrc = self.cov(astFile)
        suspStmts = faultloc.analyze(
            covSrc, goodInps, badInps, settings.faultlocAlg, self.tmpdir)
        sids = [sid for sid, _ in suspStmts.most_common(settings.topN)]
        labelSrc = self.label(astFile, sids)        
        tasks = self.spy(astFile, sids)

        
        Worker.wprocess(0, astFile, labelSrc, inpsFile, tasks,V=None,Q=None)
        

        return self.tmpdir



    CID_CONSTS = 1
    CID_OPS_PR = 2
    CID_VS = 3

    @classmethod
    def getData(cls, cid, n):
        "return [myid, mylist]"
        import itertools
        rs = []

        #n consts
        if cid == cls.CID_CONSTS:
            rs.append((0, [n]))
        elif cid == cls.CID_OPS_PR:
            for i in range(n):
                rs.append((i, [i+1]))
        #n vars
        elif cid == cls.CID_VS:
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
    

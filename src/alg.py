import pdb
import pathlib

import faultloc
import os.path
import subprocess as sp
import shutil
import settings
import common as CM

DBG = pdb.set_trace
logger = CM.getLogger(__name__, settings.loggingLevel)


def ccompile(src):
    assert os.path.isfile(src), src
    exeFile = "{}.exe".format(src)
    cmd = ("clang {} -o {}".format(src, exeFile))
    out_msg, err_msg = CM.vcmd(cmd)
    assert "Error: " not in err_msg, err_msg
    assert not out_msg, out_msg
    assert os.path.isfile(exeFile)
    return exeFile


class KLEE:

    @classmethod
    def get_good_bad_inps(cls, fl_src, tmpdir):
        "Get good/bad inps from KLEE"
        assert fl_src.is_file(), fl_src
        assert tmpdir.is_dir(), fl_src

        obj = cls.klcompile(fl_src)
        hs = str(hash(fl_src)).replace("-", "_")
        outdir = os.path.join(tmpdir, hs)
        proc = cls.klexec(obj, settings.timeout, outdir, opts=[])
        out_msg, err_msg = CM.decode_byte(proc.communicate())
        assert not err_msg, err_msg

        good_inps, bad_inps = cls.parse_inps(out_msg)
        return good_inps, bad_inps

    @classmethod
    def parse_inps(cls, ss):
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
            s = s.split(":")[1]  # x 297, y 296, z -211
            s = [s_.split()[1] for s_ in s.split(',')]  # [297, 296, -211]
            s = tuple(map(int, s))
            return s

        assert ss, ss

        ss = [s for s in ss.split('\n') if s]

        g_inps = set(parse(s) for s in ss if "PASS" in s)
        b_inps = set(parse(s) for s in ss if "FAIL" in s)

        return g_inps, b_inps

    @classmethod
    def klcompile(cls, src):
        assert os.path.isfile(src), src

        # compile file with llvm
        include = settings.KLEE_SRC / "include"
        assert include.is_dir(), include

        opts = "-emit-llvm -c"
        obj = src.with_suffix('.o')
        cmd = ("clang -I {} {} {} -o {}".format(include, opts, src, obj))

        logger.debug("$ {}".format(cmd))

        out_msg, err_msg = CM.decode_byte(CM.vcmd(cmd))
        assert not out_msg, out_msg

        assert "clang" not in err_msg and \
            "error" not in err_msg, (cmd, err_msg)

        if err_msg:
            logger.debug(err_msg)

        assert obj.is_file()

        return obj

    @classmethod
    def klexec(cls, obj, timeout, outdir, opts=[]):
        assert os.path.isfile(obj), obj
        assert timeout >= 1, timeout
        assert isinstance(outdir, str), outdir
        kleeOpts = (
            "-external-calls=all "
            "-solver-backend=z3 "
            "-max-solver-time={} "
            "-max-time={} "
            "-output-dir={} "
            .format(timeout, timeout, outdir))
        if opts:
            kleeOpts += ' '.join(map(str, opts))

        klee_exe = os.path.join(settings.KLEE_BUILD, 'bin', 'klee')
        cmd = "{} {} {}".format(klee_exe, kleeOpts, obj).strip()
        logger.debug("$ {}".format(cmd))

        proc = CM.vcmd(cmd, stderr=sp.STDOUT, do_communicate=False)
        return proc

    @classmethod
    def klrun(cls, src, wid):
        # compile transformed file and run run klee on it

        logger.debug("worker {}: run klee on {} ***".format(wid, src))

        # compile file with llvm
        obj = KLEE.klcompile(src)
        timeout = settings.timeout
        outdir = "{}-klee-out".format(obj)
        if os.path.exists(outdir):
            shutil.rmtree(outdir)
        proc = KLEE.klexec(obj, timeout, outdir)

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
                    logger.debug('worker {}: stdout: {}'.format(wid, line))

                if 'KLEE: HaltTimer invoked' in line:
                    logger.info('worker {}: stdout: {}, timeout {}'
                                .format(wid, src, timeout))

                if "KLEE: ERROR" in line and "ASSERTION FAIL: 0" in line:
                    logger.info('worker {}: found fix for {}'.format(wid, src))
                    break

        rs, rsErr = proc.communicate()

        assert not rsErr, rsErr

        ignores_miscs = ['KLEE: NOTE: now ignoring this error at this location',
                         'GOAL: ']

        if rs:
            for line in rs.split('\n'):
                if line:
                    if all(x not in line for x in ignores_done + ignores_miscs):
                        logger.debug('rs: {}'.format(line))

                    # GOAL: uk_0 0, uk_1 0, uk_2 1
                    if 'GOAL' in line:
                        s = line[line.find(':')+1:].strip()
                        s = '{}'.format(s if s else "no uks")
                        return s

        return None


class CIL:

    @classmethod
    def preproc(cls, src):
        assert src.is_file(), src

        logger.info("preprocess and obtain AST from {}".format(src))
        preproc_src = src.with_suffix('.preproc.c')  # /a.preproc.c
        ast_file = src.with_suffix('.ast')  # /a.ast

        cmd = "./preproc.exe {} {} {} {} {}"
        cmd = cmd.format(src, settings.mainQ,
                         settings.correctQ, preproc_src, ast_file)
        logger.debug(cmd)

        out_msg, err_msg = CM.vcmd(cmd)
        assert not err_msg, err_msg
        logger.debug(out_msg)
        assert preproc_src.is_file(), preproc_src
        assert ast_file.is_file(), ast_file
        return preproc_src, ast_file

    @classmethod
    def cov(cls, src, ast_file):
        """
        Create file with cov info (i.e., printf stmts)
        """
        assert src.is_file(), src
        assert ast_file.is_file(), src

        covSrc = "{}.cov.c".format(src)
        logger.info("fault localization: {}".format(covSrc))
        cmd = "./coverage.exe {} {}".format(covSrc, ast_file)
        logger.debug(cmd)
        out_msg, err_msg = CM.vcmd(cmd)
        assert not err_msg, err_msg
        logger.debug(out_msg)
        assert os.path.isfile(covSrc), covSrc
        return covSrc

    @classmethod
    def instr(self, src, ast_file):
        assert src.is_file(), src
        assert ast_file.is_file(), src

        fl_src = src.with_suffix('.fl.c')
        logger.info("get good/bad inps from {}".format(fl_src))
        cmd = "./instr.exe {} {} {}".format(fl_src, ast_file, settings.maxV)
        logger.debug(cmd)

        out_msg, err_msg = CM.vcmd(cmd)
        assert not err_msg, err_msg
        logger.debug(out_msg)
        assert os.path.isfile(fl_src), fl_src
        return fl_src

    @classmethod
    def spy(cls, src, ast_file, sids):
        ssids = '"{}"'.format(" ".join(map(str, sids)))
        labelSrc = "{}.label.c".format(src)
        cmd = "./spy.exe {} {} {} {} {}".format(
            ast_file, labelSrc, ssids, settings.tplLevel, settings.maxV)
        logger.debug(cmd)
        out_msg, err_msg = CM.decode_byte(CM.vcmd(cmd))
        assert os.path.isfile(labelSrc), labelSrc
        logger.debug(out_msg)
        logger.debug(err_msg)

        # compute tasks
        clist = out_msg.split('\n')[-1]
        clist = [c.strip() for c in clist.split(";")]
        clist = [c[1:][:-1] for c in clist]  # remove ( )
        clist = [map(int, c.split(',')) for c in clist]

        tasks = []
        for sid, cid, n in clist:
            rs = cls.getData(cid, n)
            rs = [(sid, cid) + r for r in rs]
            tasks.extend(rs)

        from random import shuffle
        shuffle(tasks)
        logger.debug("tasks {}".format(len(tasks)))

        return labelSrc, tasks

    @classmethod
    def transform(cls, src, inpsFile, wid, sid, cid, myid, idxs):
        # call ocaml prog to transform file

        xinfo = "t{}_z{}_c{}".format(cid, len(idxs), myid)
        logger.debug('worker {}: transform {} sid {} tpl {} xinfo {} idxs {} ***'
                     .format(wid, src, sid,
                             cid, xinfo, idxs))

        cmd = ('./modify.exe {} {} {} {} "{}" {} {}'
               .format(src, inpsFile,
                       sid, cid, " ".join(map(str, idxs)),
                       xinfo, settings.maxV))

        logger.debug("$ {}".format(cmd))
        proc = sp.Popen(cmd, shell=True, stdin=sp.PIPE,
                        stdout=sp.PIPE, stderr=sp.PIPE)
        rs, rsErr = proc.communicate()

        # assert not rs, rs
        logger.debug(rsErr[:-1] if rsErr.endswith("\n") else rs_err)

        if "error" in rsErr or "success" not in rsErr:
            logger.error("worker {}: transform failed '{}' !".format(wid, cmd))
            logger.error(rsErr)
            raise AssertionError

        # obtained the created result
        # Alert: Transform success: ## '/tmp/cece_4b2065/q.bug2.c.s1.t5_z3_c1.ceti.c' ##  __cil_tmp4 = (x || y) || z; ## __cil_tmp4 = (x || y) && z;

        rsFile, oldStmt, newStmt = "", "", ""

        for line in rsErr.split("\n"):
            if "success:" in line:
                line = line.split("##")
                assert len(line) == 4, len(line)  # must has 4 parts
                line = [l.strip() for l in line[1:]]
                rsFile = line[0][1:][:-1]  # remove ' ' from filename
                oldStmt = line[1]
                newStmt = line[2]
                break

        return rsFile, oldStmt, newStmt

    @classmethod
    def getData(cls, cid, n):
        "return [myid, mylist]"
        import itertools

        CID_CONSTS = 1
        CID_OPS_PR = 2
        CID_VS = 3

        rs = []

        # n consts
        if cid == CID_CONSTS:
            rs.append((0, [n]))
        elif cid == CID_OPS_PR:
            for i in range(n):
                rs.append((i, [i+1]))
        # n vars
        elif cid == CID_VS:
            maxCombSiz = 2
            for siz in range(maxCombSiz + 1):
                cs = itertools.combinations(range(n), siz)
                for i, c in enumerate(cs):
                    rs.append((i, list(c)))

        else:
            raise AssertionError("unknown CID {}".format(cid))

        return rs


class Src:
    def __init__(self, src):
        assert src.is_file()

        self.src = src

    @property
    def exeFile(self):
        try:
            return self._exeFile
        except AttributeError:
            self._exeFile = ccompile(self.src)
            return self._exeFile

    @property
    def ast_file(self):
        try:
            return self._ast_file
        except AttributeError:
            _, self._ast_file = CIL.preproc(self.src)
            return self._ast_file

    @property
    def covSrc(self):
        try:
            return self._covSrc
        except AttributeError:
            self._covSrc = CIL.cov(self.src, self.ast_file)
            return self._covSrc

    def get_good_bad_inps(self, tmpdir):
        """
        Return good and bad inps.
        if not bad inps then program passes, otherwise program fails
        """
        assert tmpdir.is_dir(), tmpdir

        logger.info("get good/bad inps from '{}'".format(self.src))
        fl_src = CIL.instr(self.src, self.ast_file)
        good_inps, bad_inps = KLEE.get_good_bad_inps(fl_src, tmpdir)
        return good_inps, bad_inps

    def check_inps(self, inps):
        """
        Determine which inp is good/bad wrt to src
        """
        assert inps, inps

        def check(inp):
            cmd = "{} {}".format(self.exeFile, ' '.join(map(str, inp)))
            out_msg, err_msg = CM.vcmd(cmd)
            assert not err_msg
            return "PASS" in out_msg

        goods, bads = set(), set()
        for inp in inps:
            if check(inp):
                goods.add(inp)
            else:
                bads.add(inp)
        return goods, bads

    def repair(self, inpsFile, suspStmts, doParallel=True):
        labelSrc, tasks = CIL.spy(self.src, self.ast_file, suspStmts)

        if doParallel:
            from multiprocessing import (Process, Queue, Value, cpu_count)
            Q = Queue()
            V = Value("i", 0)

            workloads = CM.getWorkloads(
                tasks, max_nprocesses=cpu_count(), chunksiz=2)
            logger.info("workloads {}: {}"
                        .format(len(workloads), map(len, workloads)))

            workers = [Process(target=Worker.wprocess,
                               args=(i, self.ast_file, labelSrc, inpsFile,
                                     wl, V, Q))
                       for i, wl in enumerate(workloads)]

            for w in workers:
                w.start()
            wrs = []
            for i, _ in enumerate(workers):
                wrs.extend(Q.get())
        else:
            wrs = Worker.wprocess(0, self.ast_file, labelSrc, inpsFile, tasks,
                                  V=None, Q=None)

        repairSrcs = [Src(r) for r in wrs if r]
        logger.info("found {} candidate sols".format(len(repairSrcs)))
        return repairSrcs

    @classmethod
    def check(cls, srcs, tmpdir):
        good_inps, bad_inps = set(), set()
        for src in srcs:
            good_inps_, bad_inps_ = src.get_good_bad_inps(tmpdir)
            if not bad_inps_:
                return src, None, None
            else:
                for inp in good_inps_:
                    good_inps.add(inp)
                for inp in bad_inps_:
                    bad_inps.add(inp)
        return None, good_inps, bad_inps


class Worker:
    def __init__(self, wid, src, labelSrc, inpsFile, sid, cid, myid, idxs):
        assert wid >= 0, wid
        assert isinstance(src, str) and os.path.isfile(src), src
        assert isinstance(labelSrc, str) and os.path.isfile(labelSrc), src

        self.wid = wid
        self.src = src
        self.inpsFile = inpsFile
        self.sid = sid
        self.cid = cid  # template id
        self.myid = myid
        self.idxs = idxs

        self.labelSrc = labelSrc

    def repair(self, oldStmt, newStmt, uks):
        # /var/tmp/CETI2_xkj_Bm/MedianBad1.c.s2.t3_z1_c0.ceti.c: m = y; ===> m = uk_0 + uk_1 * x; ===> uk_0 0, uk_1 1
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
        rs = CIL.transform(self.src, self.inpsFile, self.wid, self.sid,
                           self.cid, self.myid, self.idxs)
        assert len(rs) == 3
        src, oldStmt, newStmt = rs

        if src:  # transform success
            uks = KLEE.klrun(src, self.wid)
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

        def mysort(x):
            sid, cid, myid, mylist = x
            return (cid, len(mylist))

        tasks = sorted(tasks, key=lambda x: mysort(x))

        # break after finding a fix
        # noparallel
        # for src, sids, cid, idxs in tasks:
        rs = []
        if not Q:  # no parallel
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
                        logger.debug(
                            "worker {}: sol found, break !".format(wid))
                        rs.append(r)
                        V.value = V.value + 1

            Q.put(rs)
            return None


class Repair:
    def __init__(self, src):
        assert src.is_file(), src

        # make a copy and work with that
        import tempfile
        self.tmpdir = pathlib.Path(tempfile.mkdtemp(
            dir=settings.tmpdir, prefix="CETI2_"))
        tsrc = self.tmpdir / src.name
        shutil.copyfile(src, tsrc)
        assert tsrc.is_file()
        self.src = tsrc

    def start(self):
        orig_src = Src(self.src)
        good_inps, bad_inps = orig_src.get_good_bad_inps(self.tmpdir)

        if not bad_inps:
            logger.info("no bad tests: {} seems correct!".format(orig_src.src))
            return

        currIter = 0
        while True:
            currIter += 1
            suspStmts = self.getSuspStmts(
                orig_src, settings.topN, good_inps, bad_inps)
            assert suspStmts, suspStmts
            logger.info("suspstmts ({}): {}"
                        .format(len(suspStmts), ','.join(map(str, suspStmts))))
            inpsFile = self.write_inps(good_inps | bad_inps, "all_inps")

            candSrcs = orig_src.repair(inpsFile, suspStmts)
            if not candSrcs:
                logger.info("no repair found. Stop!")
                break

            logger.info("*** iter {}, candidates {}, goods {}, bads {}"
                        .format(currIter, len(candSrcs),
                                len(good_inps), len(bad_inps)))
            repairSrc, goods, bads = Src.check(candSrcs, self.tmpdir)
            if repairSrc:
                logger.info("candidate repair: {}".format(repairSrc.src))
                break
            goods, bads = orig_src.check_inps(goods | bads)
            if goods:
                for inp in goods:
                    good_inps.add(inp)
            if bads:
                for inp in bads:
                    bad_inps.add(inp)

        logger.info("iters: {}, repair found: {}"
                    .format(currIter, repairSrc is not None))

    def write_inps(self, inps, fname):
        contents = "\n".join(map(lambda s: " ".join(map(str, s)), inps))
        inpsFile = os.path.join(self.tmpdir, "{}.inps".format(fname))
        CM.vwrite(inpsFile, contents)
        logger.debug("write: {}".format(inpsFile))
        return inpsFile

    def getSuspStmts(self, src, n, good_inps, bad_inps):
        suspStmts = faultloc.analyze(
            src.covSrc, good_inps, bad_inps, settings.faultlocAlg, self.tmpdir)
        suspStmts = [sid for sid, score_ in suspStmts.most_common(n)]
        return suspStmts

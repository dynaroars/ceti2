import pdb
import pathlib
import subprocess as sp
import shutil

import settings
import common as CM

from faultloc import FaultLoc

DBG = pdb.set_trace
mlog = CM.getLogger(__name__, settings.loggingLevel)


def ccompile(src):
    assert src.is_file(), src
    exe_file = src.with_suffix('.exe')
    cmd = ("clang {} -o {}".format(src, exe_file))
    out_msg, err_msg = CM.vcmd(cmd)
    assert "Error: " not in err_msg, err_msg
    assert not out_msg, out_msg
    assert exe_file.is_file()
    return exe_file


class KLEE:

    @classmethod
    def get_good_bad_inps(cls, fl_src, tmpdir):
        "Get good/bad inps from KLEE"
        assert fl_src.is_file(), fl_src
        assert tmpdir.is_dir(), fl_src

        obj = cls.kl_compile(fl_src)
        hs = str(hash(fl_src)).replace("-", "_")
        outdir = tmpdir / hs
        proc = cls.kl_exec(obj, settings.timeout, outdir, opts=[])
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
        assert isinstance(ss, str) and ss, ss

        def parse(s):
            s = s.split(":")[1]  # x 297, y 296, z -211
            # [297, 296, -211]
            s = tuple(int(x.split()[1]) for x in s.split(','))
            return s

        ss = [s for s in ss.splitlines() if s]
        g_inps = set(parse(s) for s in ss if "PASS" in s)
        b_inps = set(parse(s) for s in ss if "FAIL" in s)

        return g_inps, b_inps

    @classmethod
    def kl_compile(cls, src):
        assert src.is_file(), src

        # compile file with llvm
        include = settings.KLEE_SRC / "include"
        assert include.is_dir(), include

        opts = "-emit-llvm -c"
        obj = src.with_suffix('.o')
        cmd = "clang -I {} {} {} -o {}".format(include, opts, src, obj)

        mlog.debug("$ {}".format(cmd))

        out_msg, err_msg = CM.vcmd(cmd)
        assert not out_msg, out_msg

        assert "clang" not in err_msg and \
            "error" not in err_msg, (cmd, err_msg)

        if err_msg:
            mlog.debug(err_msg)

        assert obj.is_file(), obj

        return obj

    @classmethod
    def kl_exec(cls, obj, timeout, outdir, opts=[]):
        assert obj.is_file(), obj
        assert timeout >= 1, timeout
        assert isinstance(outdir, pathlib.Path), outdir

        kl_opts = settings.KLEE_OPTS.format(timeout, timeout, outdir)
        if opts:
            kl_opts += ' '.join(map(str, opts))

        cmd = "{} {} {}".format(settings.KLEE_EXE, kl_opts, obj).strip()
        mlog.debug("$ {}".format(cmd))

        proc = CM.vcmd(cmd, stderr=sp.STDOUT, do_communicate=False)
        return proc

    @classmethod
    def klrun(cls, src, wid):
        assert src.is_file(), src

        # compile transformed file and run run klee on it

        mlog.debug("worker {}: run klee on {} ***".format(wid, src))

        # compile file with llvm
        obj = KLEE.kl_compile(src)
        assert obj.is_file, obj

        timeout = settings.timeout
        outdir = obj.with_name(obj.name + "-klee-out")
        if outdir.is_dir():
            shutil.rmtree(outdir)

        proc = KLEE.kl_exec(obj, timeout, outdir)

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
            line = proc.stdout.readline().decode('utf-8')
            line = line.strip()
            if line:
                sys.stdout.flush()
                if all(x not in line for x in ignores_run + ignores_done):
                    mlog.debug('worker {}: stdout: {}'.format(wid, line))

                if 'KLEE: HaltTimer invoked' in line:
                    mlog.info('worker {}: stdout: {}, timeout {}'
                              .format(wid, src, timeout))

                if "KLEE: ERROR" in line and "ASSERTION FAIL: 0" in line:
                    mlog.info('worker {}: found fix for {}'.format(wid, src))
                    break

        rs, rsErr = CM.decode_byte(proc.communicate())

        assert not rsErr, rsErr

        ignores_miscs = ['KLEE: NOTE: now ignoring this error at this location',
                         'GOAL: ']

        if rs:
            for line in rs.splitlines():
                if line:
                    if all(x not in line for x in ignores_done + ignores_miscs):
                        mlog.debug('rs: {}'.format(line))

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

        mlog.info("preprocess and get AST from '{}'".format(src))
        preproc_src = src.with_suffix('.preproc.c')  # /a.preproc.c
        ast_file = src.with_suffix('.ast')  # /a.ast

        cmd = "./preproc.exe {} {} {} {} {}"
        cmd = cmd.format(src, settings.mainQ, settings.correctQ,
                         preproc_src, ast_file)
        mlog.debug(cmd)

        out_msg, err_msg = CM.vcmd(cmd)
        assert not err_msg, err_msg
        mlog.debug(out_msg)

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

        cov_src = src.with_suffix('.cov.c')
        mlog.info("fault localization: {}".format(cov_src))
        cmd = "./coverage.exe {} {}".format(cov_src, ast_file)
        mlog.debug(cmd)
        out_msg, err_msg = CM.vcmd(cmd)
        assert not err_msg, err_msg
        mlog.debug(out_msg)
        assert cov_src.is_file(), cov_src
        return cov_src

    @classmethod
    def instr(self, src, ast_file):
        assert src.is_file(), src
        assert ast_file.is_file(), src

        fl_src = src.with_suffix('.fl.c')
        mlog.info("get good/bad inps from {}".format(fl_src))
        cmd = "./instr.exe {} {} {}".format(fl_src, ast_file, settings.maxV)
        mlog.debug(cmd)

        out_msg, err_msg = CM.vcmd(cmd)
        assert not err_msg, err_msg
        mlog.debug(out_msg)
        assert fl_src.is_file()
        return fl_src

    @classmethod
    def spy(cls, src, ast_file, sids):
        assert src.is_file(), src
        assert ast_file.is_file(), ast_file
        assert sids, sids

        ssids = '"{}"'.format(" ".join(map(str, sids)))
        label_src = src.with_suffix('.label.c')
        cmd = "./spy.exe {} {} {} {} {}".format(
            ast_file, label_src, ssids, settings.tplLevel, settings.maxV)
        mlog.debug(cmd)
        out_msg, err_msg = CM.vcmd(cmd)
        assert label_src.is_file(), label_src
        # mlog.debug(out_msg)
        # mlog.debug(err_msg)

        # compute tasks
        clist = out_msg.splitlines()[-1]
        clist = [c.strip() for c in clist.split(";")]
        clist = [c[1:][:-1] for c in clist]  # remove ( )
        clist = [map(int, c.split(',')) for c in clist]

        tasks = []
        for sid, cid, n in clist:
            rs = cls.get_data(cid, n)
            rs = [(sid, cid) + r for r in rs]
            tasks.extend(rs)

        from random import shuffle
        shuffle(tasks)
        mlog.debug("tasks {}".format(len(tasks)))

        return label_src, tasks

    @classmethod
    def transform(cls, src, inps_file, wid, sid, cid, myid, idxs):
        assert src.is_file(), src
        assert inps_file.is_file(), src
        assert wid >= 0, wid
        assert cid >= 0, cid
        assert myid >= 0, myid

        # call ocaml prog to transform file

        xinfo = "t{}_z{}_c{}".format(cid, len(idxs), myid)
        mlog.debug('worker {}: transform {} sid {} tpl {} xinfo {} idxs {} ***'
                   .format(wid, src, sid,
                           cid, xinfo, idxs))

        cmd = ('./modify.exe {} {} {} {} "{}" {} {}'
               .format(src, inps_file,
                       sid, cid, " ".join(map(str, idxs)),
                       xinfo, settings.maxV))

        mlog.debug("$ {}".format(cmd))
        rs, rs_err = CM.vcmd(cmd)

        # assert not rs, rs
        mlog.debug(rs_err[:-1] if rs_err.endswith("\n") else rs_err)

        if "error" in rs_err or "success" not in rs_err:
            mlog.error("worker {}: transform failed '{}' !".format(wid, cmd))
            mlog.error(rs_err)
            raise AssertionError

        # obtained the created result
        # Alert: Transform success: ## '/tmp/cece_4b2065/q.bug2.c.s1.t5_z3_c1.ceti.c' ##  __cil_tmp4 = (x || y) || z; ## __cil_tmp4 = (x || y) && z;

        rs_file, old_stmt, new_stmt = "", "", ""

        for line in rs_err.splitlines():
            if "success:" in line:
                line = line.split("##")
                assert len(line) == 4, len(line)  # must has 4 parts
                line = [l.strip() for l in line[1:]]
                rs_file = line[0][1:][:-1]  # remove ' ' from filename
                old_stmt, new_stmt = line[1], line[2]
                break

        rs_file = pathlib.Path(rs_file)
        assert rs_file.is_file(), rs_file
        return rs_file, old_stmt, new_stmt

    @classmethod
    def get_data(cls, cid, n):
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
    def exe_file(self):
        try:
            return self._exe_file
        except AttributeError:
            self._exe_file = ccompile(self.src)
            return self._exe_file

    @property
    def ast_file(self):
        try:
            return self._ast_file
        except AttributeError:
            _, self._ast_file = CIL.preproc(self.src)
            return self._ast_file

    @property
    def cov_src(self):
        try:
            return self._cov_src
        except AttributeError:
            self._cov_src = CIL.cov(self.src, self.ast_file)
            return self._cov_src

    def get_good_bad_inps(self, tmpdir):
        """
        Return good and bad inps.
        if not bad inps then program passes, otherwise program fails
        """
        assert tmpdir.is_dir(), tmpdir

        mlog.info("get good/bad inps from '{}'".format(self.src))
        fl_src = CIL.instr(self.src, self.ast_file)
        good_inps, bad_inps = KLEE.get_good_bad_inps(fl_src, tmpdir)
        return good_inps, bad_inps

    def check_inps(self, inps):
        """
        Determine which inp is good/bad wrt to src
        """
        assert inps, inps

        def check(inp):
            cmd = "{} {}".format(self.exe_file, ' '.join(map(str, inp)))
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

    def repair(self, inps_file, suspicious_stmts, do_mp=False):
        assert inps_file.is_file(), inps_file
        assert suspicious_stmts, suspicious_stmts

        label_src, tasks = CIL.spy(self.src, self.ast_file, suspicious_stmts)

        if do_mp:
            from multiprocessing import (Process, Queue, Value, cpu_count)
            Q = Queue()
            V = Value("i", 0)

            workloads = CM.getWorkloads(
                tasks, max_nprocesses=cpu_count(), chunksiz=2)
            mlog.info("workloads {}: {}"
                      .format(len(workloads), map(len, workloads)))

            workers = [Process(target=Worker.wprocess,
                               args=(i, self.ast_file, label_src, inps_file,
                                     wl, V, Q))
                       for i, wl in enumerate(workloads)]

            for w in workers:
                w.start()
            wrs = []
            for i, _ in enumerate(workers):
                wrs.extend(Q.get())
        else:
            wrs = Worker.wprocess(0, self.ast_file, label_src, inps_file,
                                  tasks, V=None, Q=None)

        repair_srcs = [Src(r) for r in wrs if r]
        mlog.info("found {} candidate sols".format(len(repair_srcs)))
        return repair_srcs

    @classmethod
    def check(cls, srcs, tmpdir):
        assert all(isinstance(src, Src) for src in srcs), srcs
        assert tmpdir.is_dir(), tmpdir

        good_inps, bad_inps = set(), set()
        for src in srcs:
            good_inps_, bad_inps_ = src.get_good_bad_inps(tmpdir)
            if not bad_inps_:  # found a fix
                return src, None, None
            else:
                for inp in good_inps_:
                    good_inps.add(inp)
                for inp in bad_inps_:
                    bad_inps.add(inp)
        return None, good_inps, bad_inps


class Worker:
    def __init__(self, wid, src, label_src, inps_file, sid, cid, myid, idxs):
        assert wid >= 0, wid
        assert src.is_file(), src
        assert inps_file.is_file(), src
        assert sid >= 0, sid
        assert cid >= 0, cid
        assert myid >= 0, myid

        self.wid = wid
        self.src = src
        self.inps_file = inps_file
        self.sid = sid
        self.cid = cid  # template id
        self.myid = myid
        self.idxs = idxs

        self.label_src = label_src

    def repair(self, old_stmt, new_stmt, uks):
        """
        Transforms from solutions for unknowns to fixes
        """
        # /var/tmp/CETI2_xkj_Bm/MedianBad1.c.s2.t3_z1_c0.ceti.c: m = y; ===> m = uk_0 + uk_1 * x; ===> uk_0 0, uk_1 1
        assert isinstance(old_stmt, str) and old_stmt, old_stmt
        assert isinstance(new_stmt, str) and new_stmt, new_stmt
        assert isinstance(uks, str) and uks, uks

        uksd = dict(ukv.split() for ukv in uks.split(','))
        label = "repair_stmt{}:".format(self.sid)
        contents = []
        for l in self.label_src.read_text().splitlines():
            l = l.strip()
            if contents and label in contents[-1]:
                assert old_stmt in l
                l = new_stmt
                for uk in uksd:
                    l = l.replace(uk, uksd[uk])
                l = l + "// was: {}".format(old_stmt)
            contents.append(l)

        contents = '\n'.join(contents)
        repair_src = pathlib.Path("{}_repair_{}_{}_{}_{}.c".format(
            self.label_src, self.wid, self.cid, self.myid,
            "_".join(map(str, self.idxs))))
        repair_src.write_text(contents)

        CM.vcmd("astyle -Y {}".format(repair_src))
        return repair_src

    def run(self):
        src, old_stmt, new_stmt = CIL.transform(
            self.src, self.inps_file, self.wid,
            self.sid, self.cid, self.myid, self.idxs)

        if src.is_file():  # transform success
            uks = KLEE.klrun(src, self.wid)
            if uks:
                mlog.debug("{}: {} ===> {} ===> {}".format(
                    src, old_stmt, new_stmt, uks))
                repair_src = self.repair(old_stmt, new_stmt, uks)
                assert repair_src.is_file(), repair_src
                return repair_src

        return None

    @classmethod
    def wprocess(cls, wid, src, label_src, inps_file, tasks, V, Q):
        assert src.is_file(), src
        assert label_src.is_file(), label_src

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
                w = cls(wid, src, label_src, inps_file, sid, cid, myid, idxs)
                r = w.run()
                if r:
                    mlog.debug("worker {}: sol found, break !".format(wid))
                    rs.append(r)
                    break

            return rs
        else:
            for sid, cid, myid, idxs in tasks:
                if V.value > 0:
                    mlog.debug("worker {}: sol found, break !".format(wid))
                    break
                else:
                    w = cls(wid, src, label_src, inps_file,
                            sid, cid, myid, idxs)
                    r = w.run()
                    if r:
                        mlog.debug(
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
        tmp_src = self.tmpdir / src.name
        shutil.copyfile(src, tmp_src)
        assert tmp_src.is_file()
        self.src = tmp_src

    def start(self):
        orig_src = Src(self.src)
        good_inps, bad_inps = orig_src.get_good_bad_inps(self.tmpdir)

        if not bad_inps:
            mlog.info("no bad tests: '{}' seems correct!".format(orig_src.src))
            return

        repair_src = None
        curr_iter = 0
        while True:
            curr_iter += 1
            suspicious_stmts = self.get_suspicious_stmts(
                orig_src.cov_src, settings.topN, good_inps, bad_inps)
            assert suspicious_stmts, suspicious_stmts
            mlog.info("{} suspicious stmts: {}".format(
                len(suspicious_stmts), ','.join(map(str, suspicious_stmts))))

            inps_file = self.write_inps(good_inps | bad_inps, "all_inps")

            candidate_srcs = orig_src.repair(inps_file, suspicious_stmts)
            if not candidate_srcs:
                mlog.info("no repair found. Stop!")
                break

            mlog.info("*** iter {}, candidates {}, goods {}, bads {}"
                      .format(curr_iter, len(candidate_srcs),
                              len(good_inps), len(bad_inps)))
            repair_src, goods, bads = Src.check(candidate_srcs, self.tmpdir)
            if repair_src:
                mlog.info(
                    "Found repair: {}".format(repair_src.src))
                break

            goods, bads = orig_src.check_inps(goods | bads)
            if goods:
                for inp in goods:
                    good_inps.add(inp)
            if bads:
                for inp in bads:
                    bad_inps.add(inp)

        mlog.info("iters: {}, repair found: {}"
                  .format(curr_iter, repair_src is not None))

    def write_inps(self, inps, fname):
        contents = "\n".join(map(lambda s: " ".join(map(str, s)), inps))
        inps_file = self.tmpdir / fname
        inps_file.write_text(contents)
        mlog.debug("write: {}".format(inps_file))
        return inps_file

    def get_suspicious_stmts(self, cov_src, n, good_inps, bad_inps):
        assert cov_src.is_file, cov_src
        assert n >= 1, n
        assert good_inps, good_inps
        assert bad_inps, bad_inps

        susp_stmts = FaultLoc(cov_src, good_inps, bad_inps,
                              settings.faultlocAlg, self.tmpdir).start()
        susp_stmts = [sid for sid, score_ in susp_stmts.most_common(n)]
        return susp_stmts

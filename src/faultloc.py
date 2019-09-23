from collections import Counter
import math

import settings
import common as CM
mlog = CM.getLogger(__name__, settings.loggingLevel)

"""
Perform statistical debugging to find a ranked list of 
suspicious statements
"""


class FaultLoc:
    def __init__(self, cov_src, good_inps, bad_inps, alg_id, tmpdir):
        assert cov_src.is_file(), cov_src.is_file()
        assert good_inps, good_inps
        assert bad_inps, bad_inps
        assert isinstance(alg_id, int), alg_id
        assert tmpdir.is_dir(), tmpdir

        self.cov_src = cov_src
        self.good_inps = good_inps
        self.bad_inps = bad_inps
        self.alg_id = alg_id
        self.tmpdir = tmpdir

    def start(self):
        # compile
        exe = self.cov_src.with_suffix('.exe')
        cmd = "clang {} -o {}".format(self.cov_src, exe)
        mlog.debug(cmd)
        _, err_msg = CM.vcmd(cmd)
        assert "error" not in err_msg, err_msg
        assert exe.is_file(), exe

        good_sids, bad_sids = self.collect_cov(exe)

        good_nruns, good_freqs = self.analyze_covs(good_sids)
        bad_nruns, bad_freqs = self.analyze_covs(bad_sids)
        assert bad_nruns == len(self.bad_inps)
        sscores = self.get_scores(good_nruns, good_freqs, bad_nruns, bad_freqs)
        return sscores

    def collect_cov(self, exe):
        assert exe.is_file(), exe

        path = self.cov_src.with_suffix('.c.path')

        def run(inps):
            if path.is_file():
                path.unlink()  # remove

            inps_str = [" ".join(map(str, inp)) for inp in inps]
            cmds = ["{} {}".format(exe, inp_str) for inp_str in inps_str]
            for cmd in cmds:
                out_msg, err_msg = CM.vcmd(cmd)
                assert not err_msg

            assert path.is_file(), path
            sids = [int(sid) for sid in path.read_text().splitlines() if sid]
            return sids

        good_sids = run(self.good_inps)
        bad_sids = run(self.bad_inps)

        return good_sids, bad_sids

    def analyze_covs(self, sids):
        assert all(isinstance(sid, int) for sid in sids) and sids, sids
        freqs = Counter()
        nruns = 0

        import itertools
        for k, g in itertools.groupby(sids, key=lambda x: x != 0):
            if not k:
                continue
            nruns += 1
            for sid in g:
                freqs[sid] += 1

        return nruns, freqs

    def get_scores(self, good_nruns, good_freqs,
                   bad_nruns, bad_freqs):

        assert good_nruns >= 1, good_nruns
        assert isinstance(good_freqs, Counter), good_freqs

        assert bad_nruns >= 1, bad_nruns
        assert isinstance(bad_freqs, Counter), bad_freqs

        sids = set(list(good_freqs) + list(bad_freqs))

        if self.alg_id == 0:
            mlog.debug("fault localize using Ochiai")
            falg = self.alg_Ochiai
        else:
            mlog.debug("fault localize using Tarantula")
            falg = self.alg_Tarantula

        def f(sid): return falg(
            good_nruns, good_freqs[sid], bad_nruns, bad_freqs[sid])
        scores = Counter({sid: f(sid) for sid in sids})
        # print scores.most_common(10)

        return scores

    @classmethod
    def alg_Tarantula(cls, good_nruns, good_occurs, bad_nruns, bad_occurs):
        a = float(bad_occurs) / bad_nruns
        b = float(good_occurs) / good_nruns
        c = a + b
        return a / c if c else 0.0

    @classmethod
    def alg_Ochiai(cls, good_nruns, good_occurs, bad_nruns, bad_occurs):
        c = math.sqrt(bad_occurs * good_occurs)
        return bad_nruns / c if c else 0.0

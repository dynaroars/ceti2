import pathlib
tmpdir = pathlib.Path("/var/tmp/")
faultlocAlg = 0  # 0 - Ochiai  #1 - Tarantula
loggingLevel = 3
timeout = 10
mainQ = "mainQ"
correctQ = "correctQ"
maxV = 100
topN = 10
topSScore = 0.5
tplLevel = 4  # use only templates with id <= level

KLEE_SRC = pathlib.Path("/home/SHARED/Devel/KLEE/klee")
assert KLEE_SRC.is_dir(), KLEE_SRC

KLEE_BUILD = pathlib.Path("/home/SHARED/Devel/KLEE/klee_build_dir")
assert KLEE_BUILD.is_dir(), KLEE_BUILD
KLEE_EXE = KLEE_BUILD / 'bin' / 'klee'
assert KLEE_EXE.is_file(), KLEE_EXE

KLEE_OPTS = ("-external-calls=all "
             "-solver-backend=z3 "
             "-max-solver-time={} "
             "-max-time={} "
             "-output-dir={} ")

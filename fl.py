#statistical fault localization

import common
def sfaultloc(src, goodTests, badTests):
    #instrument file to have printf stmts
    cmd = "./coverage {}".format(src)
    outMsg, errMsg = common.vcmd(cmd)
    assert not errMsg
    print outMsg

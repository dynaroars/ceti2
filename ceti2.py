if __name__ == "__main__":
    import argparse
    aparser = argparse.ArgumentParser("CETI2")
    aparser.add_argument("bad file", help="bfile")
    aparser.add_argument("good file", help="gfile")

    #0 Error #1 Warn #2 Info #3 Debug #4 Detail
    aparser.add_argument("--logger_level", "-logger_level",
                         help="set logger info",
                         type=int,
                         choices=range(5),
                         default = 2)

    aparser.add_argument("--seed", "-seed",
                         type=float,
                         help="use this seed")
    
    import logging
    from time import time
    args = aparser.parse_args()
    
    if __debug__: logging.warning("DEBUG MODE ON. Can be slow !")
    seed = round(time(), 2) if args.seed is None else float(args.seed)
    
    #Run it
    st = time()
    logging.info("time {}s".format(time() - st))
    

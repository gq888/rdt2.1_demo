# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse
from pathlib import Path
from .receiver import RdtReceiver, ReceiverConfig

def main():
    ap = argparse.ArgumentParser(description="RDT2.1(停等) 可靠文件接收端")
    ap.add_argument("--port", type=int, required=True, help="监听端口")
    ap.add_argument("--bind", default="0.0.0.0", help="绑定地址，默认0.0.0.0")
    ap.add_argument("--out-dir", default="./downloads", help="输出目录")
    ap.add_argument("--quiet", action="store_true", help="静默输出")
    args = ap.parse_args()

    cfg = ReceiverConfig(out_dir=Path(args.out_dir), verbose=not args.quiet)
    r = RdtReceiver((args.bind, args.port), cfg)
    r.serve_forever()

if __name__ == "__main__":
    main()

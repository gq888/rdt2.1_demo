# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse
from pathlib import Path
from .sender import RdtSender, SenderConfig

def main():
    ap = argparse.ArgumentParser(description="RDT2.1(停等) 可靠文件发送端")
    ap.add_argument("--file", required=True, help="要发送的文件路径")
    ap.add_argument("--host", required=True, help="接收端IP/域名")
    ap.add_argument("--port", type=int, required=True, help="接收端端口")
    ap.add_argument("--chunk", type=int, default=1024, help="分块大小(字节)，默认1024")
    ap.add_argument("--no-resume", action="store_true", help="禁用断点续传")
    ap.add_argument("--rto", type=float, default=0.3, help="初始RTO(秒)，默认0.3")
    ap.add_argument("--max-retry", type=int, default=50, help="最大重传次数，默认50")
    ap.add_argument("--quiet", action="store_true", help="静默输出")
    args = ap.parse_args()

    cfg = SenderConfig(chunk_size=args.chunk, rto_init=args.rto, max_retries=args.max_retry, verbose=not args.quiet)
    sender = RdtSender((args.host, args.port), cfg)
    sender.send_file(Path(args.file), resume=not args.no_resume)

if __name__ == "__main__":
    main()

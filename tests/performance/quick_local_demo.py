# -*- coding: utf-8 -*-
"""
本机快速验证脚本（不依赖tc）。
1) 启动接收端子进程
2) 生成随机文件
3) 发送
4) 校验接收文件sha256一致
"""
import os, sys, time, subprocess, hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DL = PROJECT_ROOT / "downloads"
DL.mkdir(exist_ok=True)

def sha256(p: Path):
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(1024*1024)
            if not b: break
            h.update(b)
    return h.hexdigest()

def main():
    port = 9000
    recv_cmd = [sys.executable, "-m", "rdtftp.cli_recv", "--port", str(port), "--out-dir", str(DL)]
    p = subprocess.Popen(recv_cmd, cwd=str(PROJECT_ROOT))

    try:
        time.sleep(0.6)
        src = PROJECT_ROOT / "test.bin"
        # 生成 3MB 文件
        src.write_bytes(os.urandom(100 * 1024))

        send_cmd = [sys.executable, "-m", "rdtftp.cli_send", "--file", str(src), "--host", "127.0.0.1", "--port", str(port)]
        t0 = time.time()
        subprocess.check_call(send_cmd, cwd=str(PROJECT_ROOT))
        elapsed = time.time() - t0

        dst = DL / src.name
        assert dst.exists(), "接收文件不存在"
        h1, h2 = sha256(src), sha256(dst)
        print(f"elapsed={elapsed:.3f}s sha256_match={h1==h2}")
        if h1 != h2:
            print("src:", h1)
            print("dst:", h2)
            raise SystemExit(2)
    finally:
        p.terminate()
        try:
            p.wait(timeout=1.0)
        except Exception:
            p.kill()

if __name__ == "__main__":
    main()

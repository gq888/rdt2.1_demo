# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .protocol import Packet, PktType, FLAG_RESUME, FLAG_META_JSON, FLAG_EOF
from .utils import sha256_file, file_id_from_sha256

@dataclass
class SenderConfig:
    chunk_size: int = 1024
    rto_init: float = 0.3  # seconds
    rto_min: float = 0.1
    rto_max: float = 2.0
    max_retries: int = 50
    verbose: bool = True

class RdtSender:
    def __init__(self, server: Tuple[str, int], cfg: SenderConfig):
        self.server = server
        self.cfg = cfg
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(self.cfg.rto_init)
        self.srtt: Optional[float] = None
        self.rto = self.cfg.rto_init

    def _log(self, msg: str):
        if self.cfg.verbose:
            print(msg, flush=True)

    def _update_rto(self, rtt: float):
        # 简单自适应超时：srtt平滑 + rto=2*srtt
        if self.srtt is None:
            self.srtt = rtt
        else:
            self.srtt = 0.875 * self.srtt + 0.125 * rtt
        self.rto = max(self.cfg.rto_min, min(self.cfg.rto_max, 2.0 * self.srtt))
        self.sock.settimeout(self.rto)

    def _send_and_wait(self, pkt: Packet, expect_type: int, expect_ack: Optional[int] = None) -> Packet:
        data = pkt.encode()
        retries = 0
        while True:
            t0 = time.time()
            self.sock.sendto(data, self.server)
            try:
                resp, _ = self.sock.recvfrom(65535)
            except socket.timeout:
                retries += 1
                if retries > self.cfg.max_retries:
                    raise TimeoutError(f"重试次数超过上限({self.cfg.max_retries})，发送失败：type={pkt.ptype}, seq={pkt.seq}")
                self._log(f"[timeout] 重传 type={pkt.ptype} seq={pkt.seq} (retries={retries}, rto={self.rto:.3f}s)")
                continue
            rtt = time.time() - t0
            self._update_rto(rtt)

            rpkt, ok = Packet.decode(resp)
            if not ok:
                self._log("[warn] 收到损坏包，忽略")
                continue
            if rpkt.ptype != expect_type:
                # 可能收到旧ACK，忽略
                continue
            if expect_ack is not None and rpkt.ack != expect_ack:
                continue
            return rpkt

    def send_file(self, file_path: Path, resume: bool = True) -> None:
        file_path = file_path.resolve()
        if not file_path.exists():
            raise FileNotFoundError(file_path)

        sha256 = sha256_file(file_path)
        fid = file_id_from_sha256(sha256)
        size = file_path.stat().st_size

        meta = {
            "filename": file_path.name,
            "filesize": size,
            "chunk_size": self.cfg.chunk_size,
            "sha256": sha256,
        }
        syn_flags = FLAG_META_JSON | (FLAG_RESUME if resume else 0)
        syn = Packet(ptype=PktType.SYN, flags=syn_flags, file_id=fid, payload=json.dumps(meta, ensure_ascii=False).encode("utf-8"))

        self._log(f"[SYN] -> {self.server} file={file_path.name} size={size}B chunk={self.cfg.chunk_size} fid={fid:016x}")
        synack = self._send_and_wait(syn, expect_type=PktType.SYN_ACK)
        # SYN-ACK payload: {"next_chunk": k, "message": "..."}
        next_chunk = 0
        if synack.payload:
            try:
                info = json.loads(synack.payload.decode("utf-8"))
                next_chunk = int(info.get("next_chunk", 0))
                msg = info.get("message", "")
                if msg:
                    self._log(f"[SYN-ACK] {msg} next_chunk={next_chunk}")
            except Exception:
                pass

        # 开始发送数据
        sent_bytes = next_chunk * self.cfg.chunk_size
        total_chunks = (size + self.cfg.chunk_size - 1) // self.cfg.chunk_size
        start = time.time()

        with file_path.open("rb") as f:
            if sent_bytes > 0:
                f.seek(sent_bytes)

            for chunk_id in range(next_chunk, total_chunks):
                payload = f.read(self.cfg.chunk_size)
                eof = (chunk_id == total_chunks - 1)
                flags = FLAG_EOF if eof else 0
                pkt = Packet(ptype=PktType.DATA, flags=flags, file_id=fid, seq=chunk_id, ack=0, chunk_id=chunk_id, payload=payload)

                ackpkt = self._send_and_wait(pkt, expect_type=PktType.ACK, expect_ack=chunk_id)
                sent_bytes += len(payload)
                if chunk_id % 200 == 0 or eof:
                    pct = sent_bytes / max(1, size) * 100.0
                    self._log(f"[ACK] chunk={chunk_id}/{total_chunks-1} ({pct:.1f}%) rto={self.rto:.3f}s")

        # FIN
        fin = Packet(ptype=PktType.FIN, flags=0, file_id=fid, seq=total_chunks, ack=0, chunk_id=total_chunks, payload=b"")
        self._log("[FIN] 发送结束信号")
        self._send_and_wait(fin, expect_type=PktType.FIN_ACK)

        elapsed = time.time() - start
        goodput = size / elapsed / 1024 / 1024 if elapsed > 0 else 0.0
        self._log(f"[DONE] elapsed={elapsed:.3f}s goodput={goodput:.2f} MiB/s")

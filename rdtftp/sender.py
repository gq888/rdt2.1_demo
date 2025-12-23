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

@dataclass
class TransferStats:
    """传输统计信息"""
    total_packets: int = 0
    retransmissions: int = 0
    timeouts: int = 0
    duplicate_acks: int = 0
    rto_updates: int = 0
    packet_loss_events: int = 0
    start_time: float = 0
    end_time: float = 0

class RdtSender:
    def __init__(self, server: Tuple[str, int], cfg: SenderConfig):
        self.server = server
        self.cfg = cfg
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(self.cfg.rto_init)
        self.srtt: Optional[float] = None
        self.rto = self.cfg.rto_init
        self.stats = TransferStats()  # 传输统计

    def _log(self, msg: str):
        if self.cfg.verbose:
            print(msg, flush=True)

    def _update_rto(self, rtt: float):
        # 简单自适应超时：srtt平滑 + rto=2*srtt
        old_rto = self.rto
        if self.srtt is None:
            self.srtt = rtt
        else:
            self.srtt = 0.875 * self.srtt + 0.125 * rtt
        self.rto = max(self.cfg.rto_min, min(self.cfg.rto_max, 2.0 * self.srtt))
        self.sock.settimeout(self.rto)
        
        # 详细RTO更新日志
        if abs(self.rto - old_rto) > 0.001:  # RTO有显著变化
            self.stats.rto_updates += 1
            self._log(f"[RTO-UPDATE] RTT={rtt:.3f}s -> SRTT={self.srtt:.3f}s -> RTO={self.rto:.3f}s (变化: {self.rto-old_rto:+.3f}s)")

    def _send_and_wait(self, pkt: Packet, expect_type: int, expect_ack: Optional[int] = None) -> Packet:
        """发送并等待响应，包含详细的丢包重传日志"""
        data = pkt.encode()
        retries = 0
        last_ack = None  # 记录上一个ACK，用于检测重复ACK
        
        self.stats.total_packets += 1
        
        while True:
            t0 = time.time()
            self.sock.sendto(data, self.server)
            
            try:
                resp, _ = self.sock.recvfrom(65535)
            except socket.timeout:
                retries += 1
                self.stats.timeouts += 1
                self.stats.packet_loss_events += 1  # 超时视为丢包事件
                
                if retries > self.cfg.max_retries:
                    self._log(f"[FAIL] 重试次数超过上限({self.cfg.max_retries})，发送失败：type={pkt.ptype}, seq={pkt.seq}")
                    self._log(f"[STATS] 传输统计 - 总包数:{self.stats.total_packets}, 重传:{self.stats.retransmissions}, "
                             f"超时:{self.stats.timeouts}, 丢包事件:{self.stats.packet_loss_events}, RTO更新:{self.stats.rto_updates}")
                    raise TimeoutError(f"重试次数超过上限({self.cfg.max_retries})，发送失败：type={pkt.ptype}, seq={pkt.seq}")
                
                # 详细的重传日志
                self._log(f"[TIMEOUT-{retries}] 超时重传 type={pkt.ptype} seq={pkt.seq} "
                         f"rto={self.rto:.3f}s (丢包事件#{self.stats.packet_loss_events})")
                self.stats.retransmissions += 1
                continue
                
            rtt = time.time() - t0
            self._update_rto(rtt)

            rpkt, ok = Packet.decode(resp)
            if not ok:
                self._log(f"[CORRUPT] 收到损坏包，忽略 (可能因网络错误导致)")
                self.stats.packet_loss_events += 1  # 损坏包也视为丢包事件
                continue
                
            if rpkt.ptype != expect_type:
                # 可能收到旧ACK或其他类型包，提供详细信息
                if rpkt.ptype == PktType.ACK and expect_ack is not None:
                    if last_ack is not None and rpkt.ack == last_ack:
                        self.stats.duplicate_acks += 1
                        self._log(f"[DUP-ACK] 收到重复ACK={rpkt.ack} (重复ACK#{self.stats.duplicate_acks})")
                    else:
                        self._log(f"[UNEXPECTED-ACK] 收到非期望ACK={rpkt.ack}，期望ACK={expect_ack}")
                    last_ack = rpkt.ack
                else:
                    self._log(f"[UNEXPECTED] 收到非期望包类型={rpkt.ptype}，期望={expect_type}")
                continue
                
            if expect_ack is not None and rpkt.ack != expect_ack:
                self._log(f"[WRONG-ACK] ACK不匹配：收到ACK={rpkt.ack}，期望ACK={expect_ack}")
                continue
                
            # 成功收到期望响应
            if retries > 0:
                self._log(f"[RECOVERY] 重传成功 after {retries} retries, RTT={rtt:.3f}s")
            
            return rpkt

    def send_file(self, file_path: Path, resume: bool = True) -> None:
        """发送文件，包含详细的丢包重传统计和日志"""
        file_path = file_path.resolve()
        if not file_path.exists():
            raise FileNotFoundError(file_path)

        # 重置统计信息
        self.stats = TransferStats()
        self.stats.start_time = time.time()

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
        
        try:
            synack = self._send_and_wait(syn, expect_type=PktType.SYN_ACK)
        except TimeoutError as e:
            self._log(f"[SYN-FAIL] 握手失败: {e}")
            self._log(f"[STATS-PRE] 握手阶段统计 - 总包数:{self.stats.total_packets}, 重传:{self.stats.retransmissions}, "
                     f"超时:{self.stats.timeouts}, 丢包事件:{self.stats.packet_loss_events}")
            raise
            
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
        
        self._log(f"[START] 开始数据传输: 总块数={total_chunks}, 起始块={next_chunk}, 已发送={sent_bytes}B")

        with file_path.open("rb") as f:
            if sent_bytes > 0:
                f.seek(sent_bytes)

            for chunk_id in range(next_chunk, total_chunks):
                payload = f.read(self.cfg.chunk_size)
                eof = (chunk_id == total_chunks - 1)
                flags = FLAG_EOF if eof else 0
                pkt = Packet(ptype=PktType.DATA, flags=flags, file_id=fid, seq=chunk_id, ack=0, chunk_id=chunk_id, payload=payload)

                try:
                    ackpkt = self._send_and_wait(pkt, expect_type=PktType.ACK, expect_ack=chunk_id)
                except TimeoutError as e:
                    self._log(f"[DATA-FAIL] 数据块{chunk_id}发送失败: {e}")
                    self._log(f"[STATS-MID] 传输中断统计 - 块{chunk_id}/{total_chunks-1}, "
                             f"总包数:{self.stats.total_packets}, 重传:{self.stats.retransmissions}, "
                             f"超时:{self.stats.timeouts}, 丢包事件:{self.stats.packet_loss_events}")
                    raise
                    
                sent_bytes += len(payload)
                
                # 详细的进度日志
                if chunk_id % 50 == 0 or eof or chunk_id < 10:  # 更频繁的日志
                    pct = sent_bytes / max(1, size) * 100.0
                    elapsed_current = time.time() - start
                    speed_kbps = sent_bytes / max(0.001, elapsed_current) / 1024
                    self._log(f"[PROGRESS] chunk={chunk_id}/{total_chunks-1} ({pct:.1f}%) "
                             f"速度={speed_kbps:.1f}KB/s RTO={self.rto:.3f}s "
                             f"统计:重传{self.stats.retransmissions}|超时{self.stats.timeouts}|丢包{self.stats.packet_loss_events}")

        # FIN
        fin = Packet(ptype=PktType.FIN, flags=0, file_id=fid, seq=total_chunks, ack=0, chunk_id=total_chunks, payload=b"")
        self._log("[FIN] 发送结束信号")
        
        try:
            self._send_and_wait(fin, expect_type=PktType.FIN_ACK)
        except TimeoutError as e:
            self._log(f"[FIN-FAIL] 结束信号发送失败: {e}")
            # 即使FIN失败，文件传输已完成，继续统计

        # 最终统计和总结
        self.stats.end_time = time.time()
        elapsed = self.stats.end_time - self.stats.start_time
        goodput = size / elapsed / 1024 / 1024 if elapsed > 0 else 0.0
        
        self._log(f"[DONE] 传输完成! elapsed={elapsed:.3f}s goodput={goodput:.2f} MiB/s")
        self._log(f"[FINAL-STATS] 完整传输统计:")
        self._log(f"    📊 总数据包数: {self.stats.total_packets}")
        self._log(f"    🔄 重传次数: {self.stats.retransmissions}")
        self._log(f"    ⏰ 超时次数: {self.stats.timeouts}")
        self._log(f"    📦 丢包事件: {self.stats.packet_loss_events}")
        self._log(f"    🔁 重复ACK: {self.stats.duplicate_acks}")
        self._log(f"    ⏱️  RTO更新: {self.stats.rto_updates}")
        
        # 丢包率分析
        if self.stats.total_packets > 0:
            loss_rate = (self.stats.retransmissions / self.stats.total_packets) * 100
            self._log(f"    📉 有效丢包率: {loss_rate:.1f}% (重传/总包)")
            
        if self.stats.packet_loss_events > 0:
            avg_retries_per_loss = self.stats.retransmissions / self.stats.packet_loss_events
            self._log(f"    🎯 平均重传/丢包事件: {avg_retries_per_loss:.1f}次")

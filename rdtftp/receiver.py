# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

from .protocol import Packet, PktType, FLAG_RESUME, FLAG_META_JSON, FLAG_EOF, FLAG_RESUME_OK
from .utils import load_json, save_json, sha256_file, file_id_from_sha256

@dataclass
class ReceiverConfig:
    out_dir: Path
    verbose: bool = True

class RdtReceiver:
    def __init__(self, bind: Tuple[str, int], cfg: ReceiverConfig):
        self.bind = bind
        self.cfg = cfg
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(self.bind)
        self._log(f"[LISTEN] UDP {self.bind[0]}:{self.bind[1]}")

        # session map: file_id -> session dict
        self.sessions: Dict[int, Dict] = {}

    def _log(self, msg: str):
        if self.cfg.verbose:
            print(msg, flush=True)

    def _session_paths(self, fid: int, filename: str) -> Tuple[Path, Path]:
        # 临时文件 + 元数据
        part = self.cfg.out_dir / f"{filename}.part"
        meta = self.cfg.out_dir / f"{filename}.rdtmeta.json"
        return part, meta

    def _load_or_init_session(self, meta: Dict) -> Dict:
        filename = meta["filename"]
        fid = int(meta["file_id"])
        chunk_size = int(meta["chunk_size"])
        filesize = int(meta["filesize"])
        sha256 = meta["sha256"]

        part_path, meta_path = self._session_paths(fid, filename)
        s = load_json(meta_path, default={})
        # 校验元信息是否匹配，不匹配则重置（避免同名不同文件）
        if s.get("file_id") != fid or s.get("sha256") != sha256 or s.get("chunk_size") != chunk_size or s.get("filesize") != filesize:
            s = {
                "filename": filename,
                "file_id": fid,
                "filesize": filesize,
                "chunk_size": chunk_size,
                "sha256": sha256,
                "next_chunk": 0,
                "updated_at": time.time(),
            }
            # 如果存在旧part但不匹配，重命名备份
            if part_path.exists():
                backup = part_path.with_suffix(part_path.suffix + f".bak_{int(time.time())}")
                part_path.rename(backup)
        else:
            # 根据现有part文件大小推断next_chunk（停等式下通常是连续前缀）
            if part_path.exists():
                sz = part_path.stat().st_size
                s["next_chunk"] = int(sz // chunk_size)
        save_json(meta_path, s)
        return s

    def serve_forever(self):
        self.cfg.out_dir.mkdir(parents=True, exist_ok=True)
        while True:
            data, addr = self.sock.recvfrom(65535)
            pkt, ok = Packet.decode(data)
            if not ok:
                # 不回包也可以；这里回一个ERR便于调试
                err = Packet(ptype=PktType.ERR, flags=0, file_id=0, payload=b"bad checksum")
                self.sock.sendto(err.encode(), addr)
                continue

            if pkt.ptype == PktType.SYN:
                self._handle_syn(pkt, addr)
            elif pkt.ptype == PktType.DATA:
                self._handle_data(pkt, addr)
            elif pkt.ptype == PktType.FIN:
                self._handle_fin(pkt, addr)
            else:
                # 其他类型忽略
                pass

    def _handle_syn(self, pkt: Packet, addr):
        if not (pkt.flags & FLAG_META_JSON):
            # 没带meta直接拒绝
            synack = Packet(ptype=PktType.SYN_ACK, flags=0, file_id=pkt.file_id,
                            payload=json.dumps({"next_chunk": 0, "message": "缺少元信息，已按0开始"}, ensure_ascii=False).encode("utf-8"))
            self.sock.sendto(synack.encode(), addr)
            return

        meta = json.loads(pkt.payload.decode("utf-8"))
        filename = meta.get("filename", "recv.bin")
        filesize = int(meta.get("filesize", 0))
        chunk_size = int(meta.get("chunk_size", 1024))
        sha256 = meta.get("sha256", "")
        fid = int(pkt.file_id)

        sess_meta = {
            "filename": filename,
            "filesize": filesize,
            "chunk_size": chunk_size,
            "sha256": sha256,
            "file_id": fid,
        }
        s = self._load_or_init_session(sess_meta)
        self.sessions[fid] = s

        next_chunk = int(s.get("next_chunk", 0)) if (pkt.flags & FLAG_RESUME) else 0
        flags = FLAG_RESUME_OK if (pkt.flags & FLAG_RESUME) else 0
        msg = "续传" if (pkt.flags & FLAG_RESUME) else "新传"
        self._log(f"[SYN] {addr} {msg} filename={filename} fid={fid:016x} next_chunk={next_chunk}")

        synack = Packet(
            ptype=PktType.SYN_ACK,
            flags=flags | FLAG_META_JSON,
            file_id=fid,
            ack=0,
            payload=json.dumps({"next_chunk": next_chunk, "message": f"{msg}已就绪"}, ensure_ascii=False).encode("utf-8"),
        )
        self.sock.sendto(synack.encode(), addr)

    def _handle_data(self, pkt: Packet, addr):
        fid = int(pkt.file_id)
        if fid not in self.sessions:
            # 未握手也可尝试临时创建一个会话（但更推荐先SYN）
            self._log("[WARN] 未建立会话，忽略DATA")
            return

        s = self.sessions[fid]
        filename = s["filename"]
        chunk_size = int(s["chunk_size"])
        expected = int(s.get("next_chunk", 0))
        part_path, meta_path = self._session_paths(fid, filename)

        # 停等式：只接受期望块。重复块/乱序块：回ACK(last)
        if pkt.chunk_id != expected or pkt.seq != expected:
            ack_id = expected - 1 if expected > 0 else 0
            ack = Packet(ptype=PktType.ACK, flags=0, file_id=fid, ack=ack_id, seq=0, chunk_id=ack_id, payload=b"")
            self.sock.sendto(ack.encode(), addr)
            return

        # 写入
        part_path.parent.mkdir(parents=True, exist_ok=True)
        with part_path.open("ab") as f:
            f.write(pkt.payload)

        # 更新会话
        s["next_chunk"] = expected + 1
        s["updated_at"] = time.time()
        save_json(meta_path, s)

        # ACK
        ack = Packet(ptype=PktType.ACK, flags=0, file_id=fid, ack=expected, seq=0, chunk_id=expected, payload=b"")
        self.sock.sendto(ack.encode(), addr)

        if (pkt.flags & FLAG_EOF) != 0:
            # EOF：尝试完成
            self._finalize_if_complete(fid)

    def _handle_fin(self, pkt: Packet, addr):
        fid = int(pkt.file_id)
        if fid in self.sessions:
            self._finalize_if_complete(fid)
        finack = Packet(ptype=PktType.FIN_ACK, flags=0, file_id=fid, ack=pkt.seq, payload=b"")
        self.sock.sendto(finack.encode(), addr)

    def _finalize_if_complete(self, fid: int):
        s = self.sessions.get(fid)
        if not s:
            return
        filename = s["filename"]
        filesize = int(s["filesize"])
        sha256 = s["sha256"]
        part_path, meta_path = self._session_paths(fid, filename)
        final_path = self.cfg.out_dir / filename

        if not part_path.exists():
            return
        if part_path.stat().st_size < filesize:
            # 未收完
            return

        # 校验sha256
        got = sha256_file(part_path)
        if sha256 and got != sha256:
            self._log(f"[FAIL] 文件校验失败 sha256_expected={sha256} got={got}，保留.part")
            return

        # 完成：重命名
        if final_path.exists():
            backup = final_path.with_suffix(final_path.suffix + f".bak_{int(time.time())}")
            final_path.rename(backup)
        part_path.rename(final_path)

        # 清理meta
        try:
            meta_path.unlink(missing_ok=True)
        except Exception:
            pass

        self._log(f"[OK] 接收完成：{final_path} ({filesize}B)")

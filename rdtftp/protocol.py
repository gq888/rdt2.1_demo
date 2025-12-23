# -*- coding: utf-8 -*-
"""
RDT2.1(停等式)可靠传输协议：基于UDP实现的可靠文件传输。
特点：
- 校验和(CRC32) + 序列号(按chunk_id递增) + ACK + 超时重传
- 文件分块(默认1KB/块) + EOF标志
- 断点续传：握手时由接收端返回 next_chunk，发送端从该块继续发送
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
import struct
import zlib
from typing import Tuple

MAGIC = b"\xCA\xFE"
VERSION = 1

class PktType(IntEnum):
    SYN = 1
    SYN_ACK = 2
    DATA = 3
    ACK = 4
    FIN = 5
    FIN_ACK = 6
    ERR = 7

# flags
FLAG_RESUME = 0x01      # SYN里表示希望续传
FLAG_EOF = 0x02         # DATA里表示最后一个块
FLAG_RESUME_OK = 0x04   # SYN-ACK里表示续传被接受
FLAG_META_JSON = 0x08   # 负载是JSON(utf-8)

# 固定头(32字节)：!2sBBBBQIIIHI
# magic(2) version(1) type(1) flags(1) hlen(1) file_id(8) seq(4) ack(4) chunk_id(4) payload_len(2) checksum(4)
HEADER_FMT = "!2sBBBBQIIIHI"
HEADER_LEN = struct.calcsize(HEADER_FMT)

@dataclass
class Packet:
    ptype: int
    flags: int
    file_id: int
    seq: int = 0
    ack: int = 0
    chunk_id: int = 0
    payload: bytes = b""

    def encode(self) -> bytes:
        payload_len = len(self.payload)
        # checksum字段先置0计算
        header_wo_checksum = struct.pack(
            HEADER_FMT,
            MAGIC,
            VERSION,
            int(self.ptype),
            int(self.flags),
            HEADER_LEN,
            int(self.file_id) & 0xFFFFFFFFFFFFFFFF,
            int(self.seq) & 0xFFFFFFFF,
            int(self.ack) & 0xFFFFFFFF,
            int(self.chunk_id) & 0xFFFFFFFF,
            payload_len & 0xFFFF,
            0
        )
        checksum = zlib.crc32(header_wo_checksum + self.payload) & 0xFFFFFFFF
        header = struct.pack(
            HEADER_FMT,
            MAGIC,
            VERSION,
            int(self.ptype),
            int(self.flags),
            HEADER_LEN,
            int(self.file_id) & 0xFFFFFFFFFFFFFFFF,
            int(self.seq) & 0xFFFFFFFF,
            int(self.ack) & 0xFFFFFFFF,
            int(self.chunk_id) & 0xFFFFFFFF,
            payload_len & 0xFFFF,
            checksum
        )
        return header + self.payload

    @staticmethod
    def decode(data: bytes) -> Tuple["Packet", bool]:
        if len(data) < HEADER_LEN:
            return Packet(PktType.ERR, 0, 0, payload=b"short packet"), False
        tup = struct.unpack(HEADER_FMT, data[:HEADER_LEN])
        magic, ver, ptype, flags, hlen, file_id, seq, ack, chunk_id, payload_len, checksum = tup
        if magic != MAGIC or ver != VERSION or hlen != HEADER_LEN:
            return Packet(PktType.ERR, 0, 0, payload=b"bad header"), False
        payload = data[HEADER_LEN:HEADER_LEN + payload_len]
        # 重新计算checksum
        header_wo_checksum = struct.pack(
            HEADER_FMT, MAGIC, VERSION, ptype, flags, HEADER_LEN, file_id, seq, ack, chunk_id, payload_len, 0
        )
        calc = zlib.crc32(header_wo_checksum + payload) & 0xFFFFFFFF
        ok = (calc == checksum)
        pkt = Packet(ptype=ptype, flags=flags, file_id=file_id, seq=seq, ack=ack, chunk_id=chunk_id, payload=payload)
        return pkt, ok

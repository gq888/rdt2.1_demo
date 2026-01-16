#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络模拟代理 - 修复版
用于模拟丢包、延迟等网络问题
修复了响应包无法正确返回给客户端的问题
"""

import socket
import random
import time
import threading
import argparse
from typing import Optional, Dict
from collections import defaultdict

class NetworkSimulator:
    def __init__(self, listen_port: int, target_host: str, target_port: int):
        self.listen_port = listen_port
        self.target_host = target_host
        self.target_port = target_port
        
        # 网络模拟参数
        self.packet_loss_rate = 0.0
        self.delay_ms = 0
        self.jitter_ms = 0
        self.duplicate_rate = 0.0
        self.reorder_rate = 0.0
        
        # 统计信息
        self.packets_forwarded = 0
        self.packets_dropped = 0
        self.packets_delayed = 0
        
        # 套接字
        self.listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.target_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = False
        
        # 客户端地址映射：file_id -> client_addr
        # 用于将响应包正确返回给原始客户端
        self.client_map: Dict[int, tuple] = {}
        self.client_map_lock = threading.Lock()
        
    def set_packet_loss(self, rate: float):
        """设置丢包率 (0.0 - 1.0)"""
        self.packet_loss_rate = max(0.0, min(1.0, rate))
        
    def should_drop_packet(self) -> bool:
        """判断是否应该丢包"""
        return random.random() < self.packet_loss_rate
        
    def set_delay(self, delay_ms: int, jitter_ms: int = 0):
        """设置延迟和抖动"""
        self.delay_ms = max(0, delay_ms)
        self.jitter_ms = max(0, jitter_ms)
        
    def set_duplicate_rate(self, rate: float):
        """设置重复包率"""
        self.duplicate_rate = max(0.0, min(1.0, rate))
        
    def get_delay_ms(self) -> int:
        """获取当前包的延迟时间"""
        if self.delay_ms == 0 and self.jitter_ms == 0:
            return 0
        
        # 基础延迟 + 随机抖动
        jitter = random.randint(-self.jitter_ms, self.jitter_ms) if self.jitter_ms > 0 else 0
        return max(0, self.delay_ms + jitter)
        
    def extract_file_id_from_packet(self, data: bytes) -> Optional[int]:
        """从RDT2.1包中提取file_id"""
        try:
            if len(data) < 32:  # 最小包头长度
                return None
                
            # RDT2.1包头格式: magic(2) + version(1) + type(1) + flags(1) + hlen(1) + file_id(8) + ...
            import struct
            magic = data[0:2]
            if magic != b'\xCA\xFE':  # RDT2.1 magic number
                return None
                
            # 跳过前6字节，file_id从第6字节开始
            file_id_bytes = data[6:14]
            file_id = struct.unpack('!Q', file_id_bytes)[0]  # 64位无符号整数
            return file_id
        except Exception:
            return None
        
    def forward_packet(self, data: bytes, from_addr: tuple, to_addr: tuple, is_response: bool = False):
        """转发数据包，应用网络模拟"""
        # 丢包检查
        if self.should_drop_packet():
            self.packets_dropped += 1
            print(f"[DROP] 丢包模拟: {len(data)} bytes from {from_addr} to {to_addr}")
            return
            
        # 获取延迟
        delay_ms = self.get_delay_ms()
        
        # 重复包检查
        should_duplicate = random.random() < self.duplicate_rate
        
        def send_packet():
            try:
                if is_response:
                    # 响应包：从目标返回给客户端
                    self.listen_sock.sendto(data, to_addr)
                else:
                    # 请求包：从客户端转发给目标
                    self.target_sock.sendto(data, to_addr)
                self.packets_forwarded += 1
                if delay_ms > 0:
                    self.packets_delayed += 1
                    
                direction = "response" if is_response else "request"
                print(f"[FORWARD] {direction}: {len(data)} bytes, delay={delay_ms}ms")
                
            except Exception as e:
                print(f"[ERROR] 转发错误: {e}")
        
        if delay_ms > 0:
            # 延迟发送
            threading.Timer(delay_ms / 1000.0, send_packet).start()
        else:
            # 立即发送
            send_packet()
            
        # 发送重复包（如果需要）
        if should_duplicate:
            if delay_ms > 0:
                threading.Timer((delay_ms + 1) / 1000.0, send_packet).start()
            else:
                send_packet()
    
    def handle_client_to_target(self):
        """处理客户端到目标的流量"""
        while self.running:
            try:
                self.listen_sock.settimeout(1.0)
                data, client_addr = self.listen_sock.recvfrom(65535)
                
                # 提取file_id用于客户端映射
                file_id = self.extract_file_id_from_packet(data)
                if file_id is not None:
                    with self.client_map_lock:
                        self.client_map[file_id] = client_addr
                    print(f"[CLIENT-MAP] 记录客户端映射: file_id={file_id:016x} -> {client_addr}")
                
                # 转发到目标
                self.forward_packet(data, client_addr, (self.target_host, self.target_port), is_response=False)
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[ERROR] 客户端处理错误: {e}")
                break
    
    def handle_target_to_client(self):
        """处理目标到客户端的流量"""
        while self.running:
            try:
                self.target_sock.settimeout(1.0)
                data, target_addr = self.target_sock.recvfrom(65535)
                
                # 提取file_id查找原始客户端
                file_id = self.extract_file_id_from_packet(data)
                if file_id is not None:
                    with self.client_map_lock:
                        client_addr = self.client_map.get(file_id)
                    
                    if client_addr:
                        print(f"[RESPONSE] 找到客户端: file_id={file_id:016x} -> {client_addr}")
                        self.forward_packet(data, target_addr, client_addr, is_response=True)
                    else:
                        print(f"[WARNING] 未找到客户端映射: file_id={file_id:016x}")
                        # 尝试广播给所有已知客户端（简化处理）
                        with self.client_map_lock:
                            for addr in self.client_map.values():
                                self.forward_packet(data, target_addr, addr, is_response=True)
                else:
                    print(f"[WARNING] 无法从响应包中提取file_id")
                    # 尝试广播给所有已知客户端
                    with self.client_map_lock:
                        for addr in self.client_map.values():
                            self.forward_packet(data, target_addr, addr, is_response=True)
                            
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[ERROR] 目标处理错误: {e}")
                break
    
    def start(self):
        """启动网络模拟器"""
        self.listen_sock.bind(("127.0.0.1", self.listen_port))
        self.running = True
        
        # 启动处理线程
        client_thread = threading.Thread(target=self.handle_client_to_target, daemon=True)
        target_thread = threading.Thread(target=self.handle_target_to_client, daemon=True)
        
        client_thread.start()
        target_thread.start()
        
        print(f"网络模拟器启动 - 监听端口: {self.listen_port}")
        print(f"目标地址: {self.target_host}:{self.target_port}")
        print(f"丢包率: {self.packet_loss_rate * 100:.1f}%")
        print(f"延迟: {self.delay_ms}ms (抖动: {self.jitter_ms}ms)")
        
        return client_thread, target_thread
    
    def stop(self):
        """停止网络模拟器"""
        self.running = False
        self.listen_sock.close()
        self.target_sock.close()
        
        print(f"\n网络模拟器停止")
        print(f"转发的包: {self.packets_forwarded}")
        print(f"丢弃的包: {self.packets_dropped}")
        print(f"延迟的包: {self.packets_delayed}")

def main():
    parser = argparse.ArgumentParser(description="网络模拟代理 - 模拟丢包、延迟等网络问题")
    parser.add_argument("--listen-port", type=int, required=True, help="监听端口")
    parser.add_argument("--target-host", required=True, help="目标主机")
    parser.add_argument("--target-port", type=int, required=True, help="目标端口")
    parser.add_argument("--loss-rate", type=float, default=0.0, help="丢包率 (0.0-1.0)")
    parser.add_argument("--delay", type=int, default=0, help="延迟 (毫秒)")
    parser.add_argument("--jitter", type=int, default=0, help="抖动 (毫秒)")
    parser.add_argument("--duplicate-rate", type=float, default=0.0, help="重复包率 (0.0-1.0)")
    
    args = parser.parse_args()
    
    simulator = NetworkSimulator(
        args.listen_port,
        args.target_host,
        args.target_port
    )
    
    # 设置网络参数
    simulator.set_packet_loss(args.loss_rate)
    simulator.set_delay(args.delay, args.jitter)
    simulator.set_duplicate_rate(args.duplicate_rate)
    
    try:
        threads = simulator.start()
        
        # 等待用户中断
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n收到中断信号，正在停止...")
    finally:
        simulator.stop()

if __name__ == "__main__":
    main()
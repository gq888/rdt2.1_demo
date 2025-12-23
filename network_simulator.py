#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络模拟代理 - 用于模拟丢包、延迟等网络问题
在macOS上替代Linux的tc/netem功能
"""

import socket
import random
import time
import threading
import argparse
from typing import Optional

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
        
    def set_packet_loss(self, rate: float):
        """设置丢包率 (0.0 - 1.0)"""
        self.packet_loss_rate = max(0.0, min(1.0, rate))
        
    def set_delay(self, delay_ms: int, jitter_ms: int = 0):
        """设置延迟和抖动"""
        self.delay_ms = max(0, delay_ms)
        self.jitter_ms = max(0, jitter_ms)
        
    def set_duplicate_rate(self, rate: float):
        """设置重复包率"""
        self.duplicate_rate = max(0.0, min(1.0, rate))
        
    def should_drop_packet(self) -> bool:
        """判断是否应该丢包"""
        return random.random() < self.packet_loss_rate
        
    def get_delay_ms(self) -> int:
        """获取当前包的延迟时间"""
        if self.delay_ms == 0 and self.jitter_ms == 0:
            return 0
        
        # 基础延迟 + 随机抖动
        jitter = random.randint(-self.jitter_ms, self.jitter_ms) if self.jitter_ms > 0 else 0
        return max(0, self.delay_ms + jitter)
        
    def forward_packet(self, data: bytes, addr: tuple, to_target: bool = True):
        """转发数据包，应用网络模拟"""
        # 丢包检查
        if self.should_drop_packet():
            self.packets_dropped += 1
            return
            
        # 获取延迟
        delay_ms = self.get_delay_ms()
        
        # 重复包检查
        should_duplicate = random.random() < self.duplicate_rate
        
        def send_packet():
            try:
                if to_target:
                    self.target_sock.sendto(data, (self.target_host, self.target_port))
                else:
                    self.listen_sock.sendto(data, addr)
                self.packets_forwarded += 1
                if delay_ms > 0:
                    self.packets_delayed += 1
            except Exception as e:
                print(f"转发错误: {e}")
        
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
                data, addr = self.listen_sock.recvfrom(65535)
                self.forward_packet(data, addr, to_target=True)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"客户端处理错误: {e}")
                break
    
    def handle_target_to_client(self):
        """处理目标到客户端的流量"""
        while self.running:
            try:
                self.target_sock.settimeout(1.0)
                data, addr = self.target_sock.recvfrom(65535)
                # 将数据发送回原始客户端（需要记录客户端地址）
                # 这里简化处理，实际应该维护客户端地址映射
                self.forward_packet(data, addr, to_target=False)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"目标处理错误: {e}")
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
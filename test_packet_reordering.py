#!/usr/bin/env python3
"""
RDT2.1协议数据包乱序测试
测试接收端是否能正确处理乱序到达的数据包
"""

import subprocess
import sys
import time
import os
import random
import threading
import socket
from pathlib import Path
from queue import Queue, PriorityQueue
import struct

# 设置项目根目录
TEST_DIR = Path(__file__).parent
DOWNLOADS_DIR = TEST_DIR / "downloads"

class ReorderingNetworkSimulator:
    """数据包重排序网络模拟器"""
    
    def __init__(self, listen_port: int, target_host: str, target_port: int, reorder_rate: float = 0.3):
        self.listen_port = listen_port
        self.target_host = target_host
        self.target_port = target_port
        self.reorder_rate = reorder_rate  # 重排序概率
        
        # 创建socket
        self.listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.listen_sock.bind(('127.0.0.1', listen_port))
        self.listen_sock.settimeout(1.0)
        
        self.target_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.target_sock.settimeout(1.0)
        
        self.running = True
        self.packet_buffer = PriorityQueue()  # 按序列号排序的缓冲区
        self.last_seq = -1
        self.buffer_lock = threading.Lock()
        
        # 统计信息
        self.stats = {
            'total_packets': 0,
            'reordered_packets': 0,
            'buffered_packets': 0,
            'immediate_forward': 0
        }
        
    def extract_sequence_number(self, data: bytes) -> int:
        """从RDT2.1数据包中提取序列号"""
        try:
            if len(data) < 32:
                return -1
                
            # RDT2.1包头格式检查
            magic = data[0:2]
            if magic != b'\xCA\xFE':
                return -1
                
            # 数据包类型
            ptype = data[2]
            if ptype == 3:  # DATA包
                # 序列号在包头中的位置（需要根据实际协议格式调整）
                # 假设序列号在包头的某个固定位置
                if len(data) >= 24:
                    seq_bytes = data[16:20]  # 假设序列号在16-20字节
                    seq_num = struct.unpack('!I', seq_bytes)[0]
                    return seq_num
            
            return -1
        except Exception as e:
            print(f"[ERROR] 提取序列号失败: {e}")
            return -1
    
    def should_reorder(self) -> bool:
        """决定是否进行重排序"""
        return random.random() < self.reorder_rate
    
    def handle_client_to_target(self):
        """处理客户端到目标的流量（数据包重排序）"""
        print(f"[REORDER-SIM] 启动重排序模拟器，重排序率: {self.reorder_rate*100:.0f}%")
        
        while self.running:
            try:
                data, client_addr = self.listen_sock.recvfrom(65535)
                self.stats['total_packets'] += 1
                
                # 提取序列号
                seq_num = self.extract_sequence_number(data)
                
                if seq_num >= 0:
                    # 数据包，考虑重排序
                    with self.buffer_lock:
                        if self.should_reorder() and seq_num > self.last_seq + 1:
                            # 缓冲这个数据包，模拟乱序
                            self.packet_buffer.put((seq_num, data, client_addr))
                            self.stats['reordered_packets'] += 1
                            self.stats['buffered_packets'] += 1
                            print(f"[REORDER] 缓冲数据包 seq={seq_num} (期望: {self.last_seq + 1})")
                            
                            # 立即发送一些后续包（模拟乱序）
                            self.send_buffered_packets()
                        else:
                            # 立即转发或按顺序转发
                            self.forward_packet(data, client_addr, (self.target_host, self.target_port))
                            self.stats['immediate_forward'] += 1
                            if seq_num == self.last_seq + 1:
                                self.last_seq = seq_num
                                self.send_buffered_packets()  # 尝试发送缓冲的包
                else:
                    # 非数据包（如SYN、ACK等），直接转发
                    self.forward_packet(data, client_addr, (self.target_host, self.target_port))
                    self.stats['immediate_forward'] += 1
                    
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[ERROR] 客户端到目标转发错误: {e}")
                
    def send_buffered_packets(self):
        """发送缓冲的数据包"""
        while not self.packet_buffer.empty():
            try:
                seq_num, data, client_addr = self.packet_buffer.queue[0]
                if seq_num <= self.last_seq + 1:
                    # 这个包可以按顺序发送了
                    self.packet_buffer.get()
                    self.forward_packet(data, client_addr, (self.target_host, self.target_port))
                    self.last_seq = seq_num
                    print(f"[REORDER] 发送缓冲包 seq={seq_num}")
                else:
                    break
            except Exception as e:
                print(f"[ERROR] 发送缓冲包错误: {e}")
                break
    
    def handle_target_to_client(self):
        """处理目标到客户端的流量（正常转发）"""
        while self.running:
            try:
                data, target_addr = self.target_sock.recvfrom(65535)
                # 对于响应包，直接转发回原始客户端
                self.target_sock.sendto(data, ('127.0.0.1', self.listen_port - 1))
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[ERROR] 目标到客户端转发错误: {e}")
    
    def forward_packet(self, data: bytes, from_addr: tuple, to_addr: tuple):
        """转发数据包"""
        try:
            if to_addr == (self.target_host, self.target_port):
                # 客户端到目标
                self.target_sock.sendto(data, to_addr)
            else:
                # 目标到客户端
                self.listen_sock.sendto(data, from_addr)
            
            # 打印转发信息
            ptype = data[2] if len(data) > 2 else 0
            seq_num = self.extract_sequence_number(data)
            if seq_num >= 0:
                print(f"[FORWARD] 类型={ptype} seq={seq_num} 大小={len(data)}B")
            else:
                print(f"[FORWARD] 类型={ptype} 大小={len(data)}B")
                
        except Exception as e:
            print(f"[ERROR] 数据包转发失败: {e}")
    
    def start(self):
        """启动模拟器"""
        self.client_thread = threading.Thread(target=self.handle_client_to_target)
        self.target_thread = threading.Thread(target=self.handle_target_to_client)
        
        self.client_thread.start()
        self.target_thread.start()
        
    def stop(self):
        """停止模拟器"""
        self.running = False
        
        if hasattr(self, 'client_thread'):
            self.client_thread.join(timeout=2)
        if hasattr(self, 'target_thread'):
            self.target_thread.join(timeout=2)
            
        self.listen_sock.close()
        self.target_sock.close()
        
        # 打印统计信息
        print(f"\n[REORDER-STATS] 重排序统计:")
        print(f"  📊 总数据包: {self.stats['total_packets']}")
        print(f"  🔄 重排序包: {self.stats['reordered_packets']}")
        print(f"  📦 缓冲包: {self.stats['buffered_packets']}")
        print(f"  ⚡ 立即转发: {self.stats['immediate_forward']}")
        print(f"  📈 重排序率: {(self.stats['reordered_packets']/self.stats['total_packets']*100):.1f}%")

def create_test_file(size_kb: int) -> Path:
    """创建测试文件"""
    test_file = TEST_DIR / f"reorder_test_{size_kb}kb.bin"
    with open(test_file, 'wb') as f:
        f.write(os.urandom(size_kb * 1024))
    return test_file

def calculate_file_hash(file_path: Path) -> str:
    """计算文件SHA256哈希"""
    import hashlib
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def test_packet_reordering():
    """测试数据包重排序"""
    print("🎯 RDT2.1协议数据包乱序测试")
    print("="*80)
    
    # 确保下载目录存在
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    
    # 创建测试文件（100KB，足够大以观察乱序行为）
    test_file = create_test_file(100)
    print(f"📁 测试文件: {test_file.name} ({test_file.stat().st_size}B)")
    
    # 计算原始文件哈希
    original_hash = calculate_file_hash(test_file)
    print(f"🔐 原始文件SHA256: {original_hash}")
    
    # 启动接收端
    print("\n🔧 启动接收端...")
    recv_cmd = [sys.executable, "-m", "rdtftp.cli_recv", "--port", "6666", "--out-dir", str(DOWNLOADS_DIR)]
    recv_proc = subprocess.Popen(recv_cmd, cwd=str(TEST_DIR), 
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.0)  # 确保接收端启动
    
    # 启动重排序网络模拟器（30%重排序概率）
    print("🔧 启动重排序网络模拟器（30%重排序概率）...")
    simulator = ReorderingNetworkSimulator(
        listen_port=6665,
        target_host="127.0.0.1",
        target_port=6666,
        reorder_rate=0.3
    )
    simulator.start()
    time.sleep(0.5)  # 确保模拟器启动
    
    # 发送文件
    print(f"\n📤 开始传输文件（通过乱序网络）...")
    send_cmd = [
        sys.executable, "-m", "rdtftp.cli_send",
        "--file", str(test_file),
        "--host", "127.0.0.1", 
        "--port", "6665",      # 连接到重排序模拟器
        "--rto", "0.3",        # 初始RTO 0.3秒
        "--max-retry", "50"    # 最多重试50次
    ]
    
    start_time = time.time()
    result = subprocess.run(send_cmd, cwd=str(TEST_DIR), 
                           capture_output=True, text=True, timeout=120)
    elapsed = time.time() - start_time
    
    print(f"\n⏱️  传输完成！用时: {elapsed:.3f}秒")
    print(f"返回码: {result.returncode}")
    
    # 显示详细传输日志
    if result.stdout:
        print(f"\n📋 详细传输日志:")
        print("-" * 80)
        for line in result.stdout.strip().split('\n'):
            print(f"  {line}")
        print("-" * 80)
    
    # 停止网络模拟器
    simulator.stop()
    
    # 验证接收文件
    print(f"\n🔍 验证接收文件完整性...")
    received_file = DOWNLOADS_DIR / test_file.name
    
    success = False
    if received_file.exists():
        received_hash = calculate_file_hash(received_file)
        print(f"🔐 接收文件SHA256: {received_hash}")
        
        if original_hash == received_hash:
            print("  ✅ 文件完整性验证通过！哈希完全一致")
            success = True
        else:
            print("  ❌ 文件完整性验证失败！哈希不匹配")
            print(f"  📊 差异分析:")
            print(f"    原始: {original_hash}")
            print(f"    接收: {received_hash}")
            
            # 进一步分析文件差异
            analyze_file_differences(test_file, received_file)
    else:
        print(f"  ❌ 接收文件不存在！应该在: {received_file}")
        # 检查downloads目录内容
        if DOWNLOADS_DIR.exists():
            files = list(DOWNLOADS_DIR.glob("*"))
            print(f"  📁 downloads目录内容: {[f.name for f in files]}")
    
    # 分析传输行为
    if result.stdout:
        stats = analyze_transmission_behavior(result.stdout)
        print_behavior_analysis(stats, elapsed, test_file.stat().st_size)
    
    # 清理
    print(f"\n{'='*80}")
    if success:
        print("🎉 数据包乱序测试成功！RDT2.1协议正确处理了乱序数据包")
        print("💡 即使在30%的重排序环境下，协议仍能保证数据顺序和完整性")
    else:
        print("❌ 数据包乱序测试失败！协议未能正确处理乱序数据包")
    
    # 终止进程
    try:
        recv_proc.terminate()
        recv_proc.wait(timeout=2)
    except:
        recv_proc.kill()
    
    # 清理临时文件
    if test_file.exists():
        test_file.unlink()
    if received_file.exists():
        received_file.unlink()

def analyze_file_differences(original: Path, received: Path):
    """分析两个文件的差异"""
    try:
        with open(original, 'rb') as f1, open(received, 'rb') as f2:
            orig_data = f1.read()
            recv_data = f2.read()
        
        if len(orig_data) != len(recv_data):
            print(f"  📏 文件大小不同: 原始={len(orig_data)}B, 接收={len(recv_data)}B")
        
        # 找到第一个不同的字节
        diff_pos = -1
        for i in range(min(len(orig_data), len(recv_data))):
            if orig_data[i] != recv_data[i]:
                diff_pos = i
                break
        
        if diff_pos >= 0:
            print(f"  🔍 第一个差异位置: {diff_pos}")
            print(f"  📊 原始字节: 0x{orig_data[diff_pos]:02x}")
            print(f"  📊 接收字节: 0x{recv_data[diff_pos]:02x}")
        else:
            print("  ✅ 文件内容相同（但大小不同）")
            
    except Exception as e:
        print(f"  ❌ 文件差异分析失败: {e}")

def analyze_transmission_behavior(log_output: str) -> dict:
    """分析传输行为"""
    stats = {
        'timeouts': 0,
        'retransmissions': 0,
        'rto_updates': 0,
        'data_packets': 0,
        'ack_packets': 0,
        'duplicate_acks': 0,
        'out_of_order_events': 0,
        'buffering_events': 0,
        'recovery_events': 0,
        'progress_reports': 0,
        'total_chunks': 0,
        'completed_chunks': 0,
        'max_rto': 0.0,
        'min_rto': 999.0,
        'final_rto': 0.0
    }
    
    for line in log_output.strip().split('\n'):
        line = line.strip()
        
        # 超时事件
        if '[TIMEOUT]' in line and '模拟' not in line:
            stats['timeouts'] += 1
            # 提取RTO值
            import re
            rto_match = re.search(r'RTO[:=]([\d.]+)', line)
            if rto_match:
                rto_val = float(rto_match.group(1))
                stats['max_rto'] = max(stats['max_rto'], rto_val)
                stats['min_rto'] = min(stats['min_rto'], rto_val)
                stats['final_rto'] = rto_val
        
        # 重传事件
        elif '重传' in line and '模拟' not in line:
            stats['retransmissions'] += 1
        
        # RTO更新
        elif '[RTO-UPDATE]' in line:
            stats['rto_updates'] += 1
        
        # 数据包
        elif '[DATA]' in line and '->' in line:
            stats['data_packets'] += 1
        
        # ACK包
        elif '[ACK]' in line:
            stats['ack_packets'] += 1
        
        # 重复ACK
        elif '重复ACK' in line:
            stats['duplicate_acks'] += 1
        
        # 乱序事件（通过日志模式检测）
        elif '乱序' in line or 'out-of-order' in line.lower():
            stats['out_of_order_events'] += 1
        
        # 缓冲事件
        elif '缓冲' in line and '数据包' in line:
            stats['buffering_events'] += 1
        
        # 恢复事件
        elif '[RECOVERY]' in line:
            stats['recovery_events'] += 1
        
        # 进度报告
        elif '[PROGRESS]' in line and 'chunk=' in line:
            stats['progress_reports'] += 1
            import re
            # 提取总块数和完成块数
            match = re.search(r'chunk=(\d+)/(\d+)', line)
            if match:
                current = int(match.group(1))
                total = int(match.group(2))
                stats['completed_chunks'] = current
                stats['total_chunks'] = total
    
    return stats

def print_behavior_analysis(stats: dict, elapsed_time: float, file_size: int):
    """打印行为分析"""
    print(f"\n📈 数据包乱序传输行为分析:")
    print(f"  ⏰ 总超时次数: {stats['timeouts']} 次")
    print(f"  🔄 总重传次数: {stats['retransmissions']} 次")
    print(f"  📊 RTO更新次数: {stats['rto_updates']} 次")
    print(f"  📦 数据包发送: {stats['data_packets']} 个")
    print(f"  ✅ ACK包接收: {stats['ack_packets']} 个")
    print(f"  🔁 重复ACK: {stats['duplicate_acks']} 个")
    print(f"  🔄 乱序事件: {stats['out_of_order_events']} 次")
    print(f"  📦 缓冲事件: {stats['buffering_events']} 次")
    print(f"  ✅ 恢复事件: {stats['recovery_events']} 次")
    
    if stats['timeouts'] > 0:
        print(f"  ⏱️  RTO范围: {stats['min_rto']:.3f}s - {stats['max_rto']:.3f}s")
        print(f"  📍 最终RTO: {stats['final_rto']:.3f}s")
    
    if stats['total_chunks'] > 0:
        completion_rate = (stats['completed_chunks'] / stats['total_chunks']) * 100
        print(f"  📊 完成进度: {stats['completed_chunks']}/{stats['total_chunks']} ({completion_rate:.1f}%)")
        
        # 计算重传率
        if stats['data_packets'] > 0:
            retrans_rate = (stats['retransmissions'] / stats['data_packets']) * 100
            print(f"  🎯 重传率: {retrans_rate:.1f}%")
    
    # 计算有效吞吐量
    if elapsed_time > 0 and file_size > 0:
        throughput_kbs = file_size / (elapsed_time * 1024)  # KB/s
        print(f"  📈 有效吞吐量: {throughput_kbs:.1f} KB/s")

if __name__ == "__main__":
    test_packet_reordering()
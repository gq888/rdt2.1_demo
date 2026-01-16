#!/usr/bin/env python3
"""
RDT2.1协议10%丢包率环境演示
使用网络模拟器来模拟10%丢包，展示详细的传输过程
"""

import subprocess
import sys
import time
import os
import tempfile
import threading
import queue
from pathlib import Path

# 设置项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
TEST_DIR = PROJECT_ROOT
DOWNLOADS_DIR = TEST_DIR / "downloads"

class AsyncStreamReader:
    """最小化的异步流读取器"""
    
    def __init__(self, stream, name, log_prefix=""):
        self.stream = stream
        self.name = name
        self.log_prefix = log_prefix
        self.queue = queue.Queue()
        self.thread = None
        self.running = False
        self.buffer = []
        
    def start(self):
        """启动异步读取线程"""
        self.running = True
        self.thread = threading.Thread(target=self._read_stream, name=f"Reader-{self.name}")
        self.thread.daemon = True
        self.thread.start()
        
    def _read_stream(self):
        """异步读取流数据"""
        try:
            for line in iter(self.stream.readline, ''):
                if line and self.running:
                    line = line.rstrip('\n\r')
                    self.buffer.append(line)
                    self.queue.put(line)
                    # 实时输出
                    self._output_line(line)
                else:
                    break
        except Exception as e:
            self.queue.put(f"[ERROR] Stream reader error: {e}")
        finally:
            self.running = False
            
    def _output_line(self, line):
        """输出单行日志"""
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        if self.log_prefix:
            print(f"[{timestamp}] {self.log_prefix} {line}", flush=True)
        else:
            print(f"[{timestamp}] {line}", flush=True)
            
    def get_lines(self):
        """获取所有已读取的行"""
        return self.buffer.copy()
        
    def stop(self):
        """停止读取线程"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

def create_test_file(size_kb: int) -> Path:
    """创建测试文件"""
    test_file = TEST_DIR / f"lossy_demo_{size_kb}kb.bin"
    with open(test_file, 'wb') as f:
        f.write(os.urandom(size_kb * 1024))
    return test_file

def test_with_network_simulator():
    """使用网络模拟器测试10%丢包率 - 异步流式输出版"""
    print("🎯 RDT2.1协议10%丢包率环境演示（异步流式输出）")
    print("="*80)
    
    # 确保下载目录存在
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    
    # 创建测试文件（50KB，足够大以观察重传行为）
    test_file = create_test_file(50)
    print(f"📁 测试文件: {test_file.name} ({test_file.stat().st_size}B)")
    
    # 启动接收端（异步方式）
    print("\n🔧 启动接收端...")
    recv_cmd = [sys.executable, "-m", "rdtftp.cli_recv", "--port", "6666", "--out-dir", str(DOWNLOADS_DIR)]
    recv_proc = subprocess.Popen(recv_cmd, cwd=str(TEST_DIR), 
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    
    # 创建接收端异步读取器
    recv_reader = AsyncStreamReader(recv_proc.stdout, "receiver", "[RECV]")
    recv_reader.start()
    
    time.sleep(1.0)  # 确保接收端启动
    
    # 启动网络模拟器（10%丢包率，异步方式）
    print("🔧 启动网络模拟器（10%丢包率）...")
    sim_cmd = [
        sys.executable, "-m", "network_simulator_fixed",
        "--listen-port", "6665",
        "--target-host", "127.0.0.1", 
        "--target-port", "6666",
        "--loss-rate", "0.1",  # 10%丢包率
        "--delay", "20",        # 20ms延迟
        "--jitter", "10"        # 10ms抖动
    ]
    sim_proc = subprocess.Popen(sim_cmd, cwd=str(TEST_DIR),
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    
    # 创建模拟器异步读取器
    sim_reader = AsyncStreamReader(sim_proc.stdout, "simulator", "[SIM]")
    sim_reader.start()
    
    time.sleep(0.5)  # 确保模拟器启动
    
    # 发送文件（异步流式输出）
    print(f"\n📤 开始传输文件（通过10%丢包网络）...")
    send_cmd = [
        sys.executable, "-m", "rdtftp.cli_send",
        "--file", str(test_file),
        "--host", "127.0.0.1", 
        "--port", "6665",      # 连接到网络模拟器
        "--rto", "0.3",        # 初始RTO 0.3秒
        "--max-retry", "50"    # 最多重试50次
    ]
    
    # 使用异步方式启动发送进程
    send_proc = subprocess.Popen(
        send_cmd,
        cwd=str(TEST_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # 创建发送进程异步读取器
    send_reader = AsyncStreamReader(send_proc.stdout, "sender", "[SEND]")
    send_reader.start()
    
    start_time = time.time()
    
    # 等待发送进程完成
    exit_code = send_proc.wait()
    elapsed = time.time() - start_time
    
    print(f"\n⏱️  传输完成！用时: {elapsed:.3f}秒")
    print(f"返回码: {exit_code}")
    
    # 获取传输日志用于后续分析
    send_output = send_reader.get_lines()
    
    # 停止所有异步读取器
    send_reader.stop()
    
    # 获取网络模拟器输出
    if sim_proc.poll() is None:  # 如果模拟器还在运行
        sim_proc.terminate()
        sim_proc.wait(timeout=2)
    
    sim_reader.stop()
    sim_output = sim_reader.get_lines()
    if sim_output:
        print(f"\n🌐 网络模拟器日志:")
        print("-" * 80)
        for line in sim_output:
            if line.strip() and any(keyword in line for keyword in ['丢包', '延迟', '转发']):
                print(f"  {line}")
        print("-" * 80)
    
    # 验证文件完整性
    print(f"\n🔍 验证文件完整性...")
    received_file = DOWNLOADS_DIR / test_file.name
    
    success = False
    if received_file.exists():
        # 计算原始文件和接收文件的SHA256
        import hashlib
        def calc_sha256(path):
            sha256_hash = hashlib.sha256()
            with open(path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        
        original_hash = calc_sha256(test_file)
        received_hash = calc_sha256(received_file)
        
        print(f"  原始文件SHA256: {original_hash}")
        print(f"  接收文件SHA256: {received_hash}")
        
        if original_hash == received_hash:
            print("  ✅ 文件完整性验证通过！")
            success = True
        else:
            print("  ❌ 文件完整性验证失败！")
    else:
        print(f"  ❌ 接收文件不存在！应该在: {received_file}")
        # 检查downloads目录内容
        if DOWNLOADS_DIR.exists():
            files = list(DOWNLOADS_DIR.glob("*"))
            print(f"  📁 downloads目录内容: {[f.name for f in files]}")
    
    # 分析传输统计
    if send_output:
        stats = analyze_transmission_log('\n'.join(send_output))
        print_stats_summary(stats, elapsed, test_file.stat().st_size)
    
    # 清理
    print(f"\n{'='*80}")
    if success:
        print("🎉 10%丢包率测试成功！RDT2.1协议成功应对网络挑战")
    else:
        print("❌ 10%丢包率测试失败！")
    
    # 停止接收端读取器并终止进程
    recv_reader.stop()
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

def analyze_transmission_log(log_output: str) -> dict:
    """分析传输日志"""
    stats = {
        'timeouts': 0,
        'retransmissions': 0,
        'rto_updates': 0,
        'data_packets': 0,
        'ack_packets': 0,
        'syn_events': 0,
        'fin_events': 0,
        'progress_reports': 0,
        'max_rto': 0.0,
        'min_rto': 999.0,
        'final_rto': 0.0,
        'total_chunks': 0,
        'completed_chunks': 0
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
        
        # SYN事件
        elif '[SYN]' in line and '->' in line:
            stats['syn_events'] += 1
        
        # FIN事件
        elif '[FIN]' in line:
            stats['fin_events'] += 1
        
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

def print_stats_summary(stats: dict, elapsed_time: float, file_size: int):
    """打印统计摘要"""
    print(f"\n📈 10%丢包率传输行为分析:")
    print(f"  ⏰ 总超时次数: {stats['timeouts']} 次")
    print(f"  🔄 总重传次数: {stats['retransmissions']} 次")
    print(f"  📊 RTO更新次数: {stats['rto_updates']} 次")
    print(f"  📦 数据包发送: {stats['data_packets']} 个")
    print(f"  ✅ ACK包接收: {stats['ack_packets']} 个")
    print(f"  🔗 SYN握手: {stats['syn_events']} 次")
    print(f"  🏁 FIN结束: {stats['fin_events']} 次")
    
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
        throughput_kbps = (file_size * 8) / (elapsed_time * 1024)  # Kbps
        throughput_kbs = file_size / (elapsed_time * 1024)  # KB/s
        print(f"  📈 有效吞吐量: {throughput_kbs:.1f} KB/s ({throughput_kbps:.1f} Kbps)")

if __name__ == "__main__":
    test_with_network_simulator()
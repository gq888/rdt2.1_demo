#!/usr/bin/env python3
"""
RDT2.1协议断点续传功能测试 - 简化版（异步流式输出版）
直接模拟传输中断，然后验证续传功能
"""

import subprocess
import sys
import time
import os
import signal
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
    test_file = TEST_DIR / f"resume_demo_{size_kb}kb.bin"
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

def test_breakpoint_resume_simple():
    """简化版断点续传测试 - 异步流式输出版"""
    print("🎯 RDT2.1协议断点续传功能测试（异步流式输出）")
    print("="*80)
    
    # 确保下载目录存在
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    
    # 创建测试文件（100KB，足够观察断点续传）
    test_file = create_test_file(60)
    original_hash = calculate_file_hash(test_file)
    
    print(f"📁 测试文件: {test_file.name}")
    print(f"📊 文件大小: {test_file.stat().st_size}B")
    print(f"🔐 原始文件SHA256: {original_hash}")
    
    # 第一步：启动传输，然后手动中断
    print(f"\n🔧 步骤1: 启动传输...")
    
    # 启动接收端（异步方式）
    recv_cmd = [sys.executable, "-m", "rdtftp.cli_recv", "--port", "6666", "--out-dir", str(DOWNLOADS_DIR)]
    recv_proc = subprocess.Popen(recv_cmd, cwd=str(TEST_DIR), 
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    
    # 创建接收端异步读取器
    recv_reader = AsyncStreamReader(recv_proc.stdout, "receiver", "[RECV]")
    recv_reader.start()
    
    time.sleep(1.0)
    
    # 启动网络模拟器（异步方式）
    print("🔧 启动网络模拟器...")
    sim_cmd = [
        sys.executable, "-m", "network_simulator_fixed",
        "--listen-port", "6665",
        "--target-host", "127.0.0.1", 
        "--target-port", "6666",
        "--loss-rate", "0.00",   # 0%丢包率
        "--delay", "2",         # 2ms延迟
        "--jitter", "3"         # 3ms抖动
    ]
    sim_proc = subprocess.Popen(sim_cmd, cwd=str(TEST_DIR),
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    
    # 创建模拟器异步读取器
    sim_reader = AsyncStreamReader(sim_proc.stdout, "simulator", "[SIM]")
    sim_reader.start()
    
    time.sleep(0.5)
    
    # 启动发送端（异步方式）
    print(f"📤 开始传输文件...")
    send_cmd = [
        sys.executable, "-m", "rdtftp.cli_send",
        "--file", str(test_file),
        "--host", "127.0.0.1", 
        "--port", "6665",
        "--rto", "0.3",
        "--max-retry", "50"
        # 注意：默认启用断点续传（没有--no-resume标志）
    ]
    
    # 运行传输一段时间，然后中断（异步方式）
    send_proc = subprocess.Popen(send_cmd, cwd=str(TEST_DIR),
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    
    # 创建发送进程异步读取器
    send_reader = AsyncStreamReader(send_proc.stdout, "sender", "[SEND]")
    send_reader.start()
    
    # 让传输运行几秒钟（模拟部分传输）
    print(f"⏰ 让传输运行3秒，然后中断...")
    time.sleep(0.3)
    
    # 中断传输
    print(f"🛑 中断传输（模拟网络故障）...")
    send_proc.terminate()
    try:
        send_proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        send_proc.kill()
    
    # 停止发送读取器
    send_reader.stop()
    
    # 检查部分传输的文件
    print(f"\n🔍 检查部分传输的文件...")
    partial_file = DOWNLOADS_DIR / f"{test_file.name}.part"
    partial_meta = DOWNLOADS_DIR / f"{test_file.name}.rdtmeta.json"
    
    partial_size = 0
    interrupt_info = "未知"
    
    if partial_file.exists():
        partial_size = partial_file.stat().st_size
        print(f"  📊 部分文件大小: {partial_size}B ({partial_size/test_file.stat().st_size*100:.1f}%)")
        
        if partial_meta.exists():
            with open(partial_meta, 'r') as f:
                meta_content = f.read()
            print(f"  📋 元数据: {meta_content}")
            
            # 解析元数据
            import json
            try:
                meta_data = json.loads(meta_content)
                next_chunk = meta_data.get('next_chunk', 0)
                total_chunks = meta_data.get('total_chunks', 0)
                interrupt_info = f"第{next_chunk}个数据块（共{total_chunks}个）"
                print(f"  📍 中断位置: {interrupt_info}")
            except:
                print(f"  ⚠️  无法解析元数据")
        else:
            print(f"  ⚠️  无元数据文件")
    else:
        print(f"  ❌ 部分文件不存在")
    
    # 停止第一轮传输
    print(f"\n🔧 停止第一轮传输...")
    try:
        recv_proc.terminate()
        recv_proc.wait(timeout=2)
    except:
        recv_proc.kill()
    
    try:
        sim_proc.terminate()
        sim_proc.wait(timeout=2)
    except:
        sim_proc.kill()
    
    # 停止读取器
    recv_reader.stop()
    sim_reader.stop()
    
    # 第二步：从断点继续传输
    print(f"\n🔧 步骤2: 从断点继续传输...")
    if partial_file.exists() and partial_size > 0:
        print(f"🎯 检测到部分传输文件，将尝试断点续传")
        print(f"📊 续传起始位置: {interrupt_info}")
        
        # 重新启动接收端（异步方式）
        print("🔧 重新启动接收端（断点续传模式）...")
        recv_cmd2 = [sys.executable, "-m", "rdtftp.cli_recv", "--port", "6666", "--out-dir", str(DOWNLOADS_DIR)]
        recv_proc2 = subprocess.Popen(recv_cmd2, cwd=str(TEST_DIR), 
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        
        # 创建第二轮接收端读取器
        recv_reader2 = AsyncStreamReader(recv_proc2.stdout, "receiver2", "[RECV2]")
        recv_reader2.start()
        
        time.sleep(1.0)
        
        # 重新启动网络模拟器（异步方式）
        print("🔧 重新启动网络模拟器...")
        sim_proc2 = subprocess.Popen(sim_cmd, cwd=str(TEST_DIR),
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        
        # 创建第二轮模拟器读取器
        sim_reader2 = AsyncStreamReader(sim_proc2.stdout, "simulator2", "[SIM2]")
        sim_reader2.start()
        
        time.sleep(0.5)
        
        # 重新启动发送端（应该能从断点继续，异步方式）
        print(f"📤 从断点继续传输...")
        send_cmd2 = [
            sys.executable, "-m", "rdtftp.cli_send",
            "--file", str(test_file),
            "--host", "127.0.0.1", 
            "--port", "6665",
            "--rto", "0.3",
            "--max-retry", "50"
        ]
        
        resume_start_time = time.time()
        
        # 使用异步方式启动续传进程
        send_proc2 = subprocess.Popen(send_cmd2, cwd=str(TEST_DIR),
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        
        # 创建续传进程读取器
        send_reader2 = AsyncStreamReader(send_proc2.stdout, "sender2", "[SEND2]")
        send_reader2.start()
        
        # 等待续传完成
        exit_code2 = send_proc2.wait()
        resume_elapsed = time.time() - resume_start_time
        
        print(f"\n⏱️  续传完成！用时: {resume_elapsed:.3f}秒")
        print(f"返回码: {exit_code2}")
        
        # 停止续传读取器
        send_reader2.stop()
        
        # 验证最终文件
        print(f"\n🔍 验证最终接收文件...")
        final_file = DOWNLOADS_DIR / test_file.name
        
        final_success = False
        if final_file.exists():
            final_hash = calculate_file_hash(final_file)
            print(f"🔐 最终文件SHA256: {final_hash}")
            print(f"🔐 原始文件SHA256: {original_hash}")
            
            if original_hash == final_hash:
                print(f"  ✅ 最终文件完整性验证通过！")
                final_success = True
            else:
                print(f"  ❌ 最终文件完整性验证失败！")
                
                # 分析差异
                final_size = final_file.stat().st_size
                original_size = test_file.stat().st_size
                print(f"  📊 文件大小对比: 原始={original_size}B, 最终={final_size}B")
        else:
            print(f"  ❌ 最终文件不存在！")
        
        # 分析续传行为
        send_output2 = send_reader2.get_lines()
        if send_output2:
            resume_stats = analyze_resume_behavior('\n'.join(send_output2))
            print_resume_analysis(resume_stats, resume_elapsed)
        
        # 总体分析
        print(f"\n{'='*80}")
        print(f"📈 断点续传测试总结:")
        
        if final_success:
            print(f"🎉 断点续传测试成功！")
            print(f"💡 RDT2.1协议成功处理了传输中断和续传")
            print(f"📊 部分文件大小: {partial_size}B")
            print(f"⏱️  续传用时: {resume_elapsed:.3f}秒")
        else:
            print(f"❌ 断点续传测试失败！")
        
        # 停止第二轮读取器
        recv_reader2.stop()
        sim_reader2.stop()
        
        # 清理
        try:
            recv_proc2.terminate()
            recv_proc2.wait(timeout=2)
        except:
            recv_proc2.kill()
        
        try:
            sim_proc2.terminate()
            sim_proc2.wait(timeout=2)
        except:
            sim_proc2.kill()
        
        # 清理文件
        if final_file.exists():
            final_file.unlink()
        if partial_meta.exists():
            partial_meta.unlink()
            
    else:
        print(f"❌ 没有找到部分传输文件，无法进行续传测试")
    
    # 清理原始测试文件
    if test_file.exists():
        test_file.unlink()

def analyze_resume_behavior(log_output: str) -> dict:
    """分析续传行为"""
    stats = {
        'resumed_from_chunk': -1,
        'total_chunks': 0,
        'resumed_chunks': 0,
        'timeouts': 0,
        'retransmissions': 0,
        'rto_updates': 0,
        'syn_ack_received': False,
        'resume_info': '',
        'progress_reports': 0
    }
    
    for line in log_output.strip().split('\n'):
        line = line.strip()
        
        # 查找续传信息
        if '续传' in line or 'resume' in line.lower():
            stats['resume_info'] = line
            # 解析续传位置
            import re
            match = re.search(r'next_chunk=(\d+)', line)
            if match:
                stats['resumed_from_chunk'] = int(match.group(1))
        
        # SYN-ACK信息
        if 'SYN-ACK' in line and '续传' in line:
            stats['syn_ack_received'] = True
        
        # 进度信息
        if '[PROGRESS]' in line and 'chunk=' in line:
            stats['progress_reports'] += 1
            import re
            match = re.search(r'chunk=(\d+)/(\d+)', line)
            if match:
                current = int(match.group(1))
                total = int(match.group(2))
                stats['total_chunks'] = total
                if stats['resumed_from_chunk'] >= 0:
                    stats['resumed_chunks'] = current - stats['resumed_from_chunk'] + 1
        
        # 超时和重传
        if '[TIMEOUT]' in line:
            stats['timeouts'] += 1
        elif '重传' in line:
            stats['retransmissions'] += 1
        elif '[RTO-UPDATE]' in line:
            stats['rto_updates'] += 1
    
    return stats

def print_resume_analysis(stats: dict, elapsed_time: float):
    """打印续传分析"""
    print(f"\n📊 续传行为分析:")
    
    if stats['resumed_from_chunk'] >= 0:
        print(f"  📍 续传起始位置: 第{stats['resumed_from_chunk']}个数据块")
        print(f"  📊 续传信息: {stats['resume_info']}")
    else:
        print(f"  ⚠️  未检测到明确的续传信息")
    
    if stats['syn_ack_received']:
        print(f"  ✅ 接收端确认续传就绪")
    
    if stats['total_chunks'] > 0 and stats['resumed_from_chunk'] >= 0:
        resumed_percentage = (stats['resumed_from_chunk'] / stats['total_chunks']) * 100
        print(f"  📈 续传位置占比: {resumed_percentage:.1f}%")
        
        if stats['resumed_chunks'] > 0:
            print(f"  📊 续传数据块数: {stats['resumed_chunks']}个")
    
    print(f"  ⏰ 续传超时次数: {stats['timeouts']}次")
    print(f"  🔄 续传重传次数: {stats['retransmissions']}次")
    print(f"  📊 续传RTO更新: {stats['rto_updates']}次")
    print(f"  📋 进度报告次数: {stats['progress_reports']}次")
    
    if elapsed_time > 0 and stats['resumed_chunks'] > 0:
        chunks_per_second = stats['resumed_chunks'] / elapsed_time
        print(f"  ⚡ 续传速度: {chunks_per_second:.1f}数据块/秒")

if __name__ == "__main__":
    test_breakpoint_resume_simple()
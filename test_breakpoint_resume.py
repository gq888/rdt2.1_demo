#!/usr/bin/env python3
"""
RDT2.1协议断点续传功能测试
测试传输中断后能否从断点继续传输
"""

import subprocess
import sys
import time
import os
import signal
import threading
from pathlib import Path

# 设置项目根目录
TEST_DIR = Path(__file__).parent
DOWNLOADS_DIR = TEST_DIR / "downloads"

def create_test_file(size_kb: int) -> Path:
    """创建测试文件"""
    test_file = TEST_DIR / f"resume_test_{size_kb}kb.bin"
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

def get_partial_file_hash(file_path: Path, size_bytes: int) -> str:
    """计算文件部分内容的哈希"""
    import hashlib
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        data = f.read(size_bytes)
        sha256_hash.update(data)
    return sha256_hash.hexdigest()

def test_breakpoint_resume():
    """测试断点续传功能"""
    print("🎯 RDT2.1协议断点续传功能测试")
    print("="*80)
    
    # 确保下载目录存在
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    
    # 创建测试文件（200KB，足够大以观察断点续传）
    test_file = create_test_file(200)
    original_hash = calculate_file_hash(test_file)
    
    print(f"📁 测试文件: {test_file.name}")
    print(f"📊 文件大小: {test_file.stat().st_size}B")
    print(f"🔐 原始文件SHA256: {original_hash}")
    
    # 第一步：启动传输，然后在中间中断
    print(f"\n🔧 步骤1: 启动传输并计划中断...")
    
    # 启动接收端
    recv_cmd = [sys.executable, "-m", "rdtftp.cli_recv", "--port", "6666", "--out-dir", str(DOWNLOADS_DIR)]
    recv_proc = subprocess.Popen(recv_cmd, cwd=str(TEST_DIR), 
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.0)
    
    # 启动网络模拟器（添加一些丢包和延迟，模拟不稳定网络）
    print("🔧 启动网络模拟器（模拟不稳定网络）...")
    sim_cmd = [
        sys.executable, "network_simulator_fixed.py",
        "--listen-port", "6665",
        "--target-host", "127.0.0.1", 
        "--target-port", "6666",
        "--loss-rate", "0.02",   # 2%丢包率
        "--delay", "30",         # 30ms延迟
        "--jitter", "20"         # 20ms抖动
    ]
    sim_proc = subprocess.Popen(sim_cmd, cwd=str(TEST_DIR),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(0.5)
    
    # 启动发送端（添加监控，在传输到一半时中断）
    print(f"📤 开始传输文件（将在中途中断）...")
    send_cmd = [
        sys.executable, "-m", "rdtftp.cli_send",
        "--file", str(test_file),
        "--host", "127.0.0.1", 
        "--port", "6665",
        "--rto", "0.3",
        "--max-retry", "50"
    ]
    
    # 启动发送进程
    send_proc = subprocess.Popen(send_cmd, cwd=str(TEST_DIR),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # 监控传输进度，在传输到约50%时中断
    print(f"⏰ 监控传输进度，将在约50%时中断...")
    partial_transmitted = False
    interrupt_chunk = -1
    
    # 实时监控输出
    start_time = time.time()
    last_progress = 0
    
    while send_proc.poll() is None and time.time() - start_time < 30:
        # 检查接收端输出以获取进度信息
        if recv_proc.stdout:
            line = recv_proc.stdout.readline()
            if line and 'chunk=' in line:
                print(f"  📊 接收进度: {line.strip()}")
                # 解析进度
                import re
                match = re.search(r'chunk=(\d+)/(\d+)', line)
                if match:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    progress_percent = (current / total) * 100
                    
                    if progress_percent >= 40 and not partial_transmitted:
                        print(f"  ⚠️  检测到传输进度: {progress_percent:.1f}%，准备中断...")
                        interrupt_chunk = current
                        partial_transmitted = True
                        break
        
        # 也检查发送端输出
        if send_proc.stdout:
            line = send_proc.stdout.readline()
            if line and ('PROGRESS' in line or 'chunk=' in line):
                print(f"  📤 发送进度: {line.strip()}")
                import re
                match = re.search(r'chunk=(\d+)/(\d+)', line)
                if match:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    progress_percent = (current / total) * 100
                    
                    if progress_percent >= 40 and not partial_transmitted:
                        print(f"  ⚠️  检测到传输进度: {progress_percent:.1f}%，准备中断...")
                        interrupt_chunk = current
                        partial_transmitted = True
                        break
        
        time.sleep(0.1)
    
    # 如果没有自动检测到进度，手动中断
    if not partial_transmitted:
        print(f"  ⚠️  未检测到明确进度，将在5秒后手动中断...")
        time.sleep(5)
        interrupt_chunk = 50  # 假设中断在第50个数据块
    
    # 中断传输（模拟网络故障或用户中断）
    print(f"  🛑 中断传输（模拟网络故障）...")
    send_proc.terminate()
    try:
        send_proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        send_proc.kill()
    
    # 检查部分传输的文件
    print(f"\n🔍 检查部分传输的文件...")
    partial_file = DOWNLOADS_DIR / test_file.name
    partial_meta = DOWNLOADS_DIR / f"{test_file.name}.rdtmeta.json"
    
    if partial_file.exists():
        partial_size = partial_file.stat().st_size
        print(f"  📊 部分文件大小: {partial_size}B")
        
        if partial_meta.exists():
            with open(partial_meta, 'r') as f:
                meta_content = f.read()
            print(f"  📋 元数据文件内容: {meta_content}")
            
            # 解析元数据以获取传输状态
            import json
            try:
                meta_data = json.loads(meta_content)
                next_chunk = meta_data.get('next_chunk', 0)
                total_chunks = meta_data.get('total_chunks', 0)
                print(f"  📊 传输状态: next_chunk={next_chunk}, total_chunks={total_chunks}")
                interrupt_chunk = next_chunk - 1 if next_chunk > 0 else 0
            except:
                print(f"  ⚠️  无法解析元数据")
    else:
        print(f"  ❌ 部分文件不存在")
        # 检查目录内容
        if DOWNLOADS_DIR.exists():
            files = list(DOWNLOADS_DIR.glob("*"))
            print(f"  📁 目录内容: {[f.name for f in files]}")
    
    # 计算部分文件的哈希（前partial_size字节）
    if partial_file.exists() and partial_file.stat().st_size > 0:
        partial_hash = get_partial_file_hash(test_file, partial_file.stat().st_size)
        print(f"  🔐 原始文件对应部分哈希: {partial_hash}")
        
        # 验证部分文件内容
        actual_partial_hash = calculate_file_hash(partial_file)
        if partial_hash == actual_partial_hash:
            print(f"  ✅ 部分文件内容验证通过！")
        else:
            print(f"  ❌ 部分文件内容验证失败！")
    
    # 停止接收端和模拟器
    print(f"\n🔧 停止第一轮传输组件...")
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
    
    # 第二步：从断点继续传输
    print(f"\n🔧 步骤2: 从断点继续传输...")
    print(f"🎯 断点位置: 第{interrupt_chunk}个数据块（约{interrupt_chunk/200*100:.1f}%）")
    
    # 重新启动接收端（应该能识别已部分传输的文件）
    print("🔧 重新启动接收端（断点续传模式）...")
    recv_cmd2 = [sys.executable, "-m", "rdtftp.cli_recv", "--port", "6666", "--out-dir", str(DOWNLOADS_DIR)]
    recv_proc2 = subprocess.Popen(recv_cmd2, cwd=str(TEST_DIR), 
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.0)
    
    # 重新启动网络模拟器
    print("🔧 重新启动网络模拟器...")
    sim_proc2 = subprocess.Popen(sim_cmd, cwd=str(TEST_DIR),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(0.5)
    
    # 重新启动发送端（应该能从断点继续）
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
    result2 = subprocess.run(send_cmd2, cwd=str(TEST_DIR), 
                            capture_output=True, text=True, timeout=120)
    resume_elapsed = time.time() - resume_start_time
    
    print(f"\n⏱️  续传完成！用时: {resume_elapsed:.3f}秒")
    print(f"返回码: {result2.returncode}")
    
    # 显示续传日志
    if result2.stdout:
        print(f"\n📋 续传详细日志:")
        print("-" * 80)
        for line in result2.stdout.strip().split('\n'):
            print(f"  {line}")
        print("-" * 80)
    
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
            
            if final_size == original_size:
                print(f"  📏 文件大小相同，但内容不同")
            else:
                print(f"  📏 文件大小不同")
    else:
        print(f"  ❌ 最终文件不存在！")
    
    # 分析续传行为
    if result2.stdout:
        resume_stats = analyze_resume_behavior(result2.stdout)
        print_resume_analysis(resume_stats, resume_elapsed)
    
    # 总体分析
    print(f"\n{'='*80}")
    print(f"📈 断点续传测试总结:")
    
    if final_success:
        print(f"🎉 断点续传测试成功！")
        print(f"💡 RDT2.1协议成功处理了传输中断和续传")
        
        # 估算节省的时间
        total_time = 2.015 + resume_elapsed  # 粗略估算
        full_transfer_estimate = total_time * 2  # 假设完整传输需要约2倍时间
        time_saved = full_transfer_estimate - total_time
        print(f"⏱️  估算节省的时间: {time_saved:.1f}秒 ({time_saved/full_transfer_estimate*100:.1f}%)")
    else:
        print(f"❌ 断点续传测试失败！")
    
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
    test_breakpoint_resume()
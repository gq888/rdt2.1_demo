#!/usr/bin/env python3
"""
RDT2.1协议数据包乱序测试 - 简化版本
使用网络模拟器来模拟数据包乱序，验证接收端是否能正确处理
"""

import subprocess
import sys
import time
import os
import tempfile
from pathlib import Path

# 设置项目根目录
TEST_DIR = Path(__file__).parent
DOWNLOADS_DIR = TEST_DIR / "downloads"

def create_test_file(size_kb: int) -> Path:
    """创建测试文件"""
    test_file = TEST_DIR / f"reorder_simple_{size_kb}kb.bin"
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

def test_with_reordering_simulator():
    """使用网络模拟器测试数据包乱序"""
    print("🎯 RDT2.1协议数据包乱序测试 - 简化版")
    print("="*80)
    
    # 确保下载目录存在
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    
    # 创建测试文件（20KB，较小的文件便于观察）
    test_file = create_test_file(20)
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
    
    # 启动网络模拟器（添加延迟和抖动来模拟乱序）
    print("🔧 启动网络模拟器（模拟乱序网络）...")
    sim_cmd = [
        sys.executable, "network_simulator_fixed.py",
        "--listen-port", "6665",
        "--target-host", "127.0.0.1", 
        "--target-port", "6666",
        "--loss-rate", "0.05",   # 5%丢包率（降低丢包率）
        "--delay", "50",         # 50ms基础延迟
        "--jitter", "100"        # 100ms抖动（高抖动会导致乱序）
    ]
    sim_proc = subprocess.Popen(sim_cmd, cwd=str(TEST_DIR),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(0.5)  # 确保模拟器启动
    
    # 发送文件
    print(f"\n📤 开始传输文件（通过高抖动网络模拟乱序）...")
    send_cmd = [
        sys.executable, "-m", "rdtftp.cli_send",
        "--file", str(test_file),
        "--host", "127.0.0.1", 
        "--port", "6665",      # 连接到网络模拟器
        "--rto", "0.5",        # 增加RTO以应对高延迟
        "--max-retry", "30"    # 减少重试次数
    ]
    
    start_time = time.time()
    result = subprocess.run(send_cmd, cwd=str(TEST_DIR), 
                           capture_output=True, text=True, timeout=180)
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
    
    # 显示网络模拟器日志
    if sim_proc.poll() is None:  # 如果模拟器还在运行
        sim_proc.terminate()
        sim_proc.wait(timeout=2)
    
    sim_output = sim_proc.stdout.read()
    if sim_output:
        print(f"\n🌐 网络模拟器日志:")
        print("-" * 80)
        reorder_count = 0
        for line in sim_output.strip().split('\n'):
            if any(keyword in line for keyword in ['延迟', '转发', '丢包']):
                print(f"  {line}")
                if '延迟' in line and '变化' in line:
                    reorder_count += 1
        print("-" * 80)
        if reorder_count > 0:
            print(f"  📊 检测到 {reorder_count} 次延迟变化事件")
    
    # 验证接收文件
    print(f"\n🔍 验证接收文件完整性...")
    received_file = DOWNLOADS_DIR / test_file.name
    
    success = False
    if received_file.exists():
        received_hash = calculate_file_hash(received_file)
        print(f"🔐 接收文件SHA256: {received_hash}")
        
        if original_hash == received_hash:
            print("  ✅ 文件完整性验证通过！哈希完全一致")
            print("  💡 即使在高抖动网络环境下，RDT2.1仍能保证数据顺序和完整性")
            success = True
        else:
            print("  ❌ 文件完整性验证失败！哈希不匹配")
            print(f"  📊 差异分析:")
            print(f"    原始: {original_hash[:16]}...{original_hash[-16:]}")
            print(f"    接收: {received_hash[:16]}...{received_hash[-16:]}")
            
            # 进一步分析文件差异
            analyze_file_differences(test_file, received_file)
    else:
        print(f"  ❌ 接收文件不存在！应该在: {received_file}")
        # 检查downloads目录内容
        if DOWNLOADS_DIR.exists():
            files = list(DOWNLOADS_DIR.glob("*"))
            print(f"  📁 downloads目录内容: {[f.name for f in files if f.is_file()]}")
    
    # 分析传输行为
    if result.stdout:
        stats = analyze_transmission_behavior(result.stdout)
        print_behavior_analysis(stats, elapsed, test_file.stat().st_size)
    
    # 清理
    print(f"\n{'='*80}")
    if success:
        print("🎉 数据包乱序测试成功！RDT2.1协议正确处理了网络乱序")
        print("🎯 高抖动网络环境模拟了真实的数据包乱序场景")
    else:
        print("❌ 数据包乱序测试失败！需要进一步分析原因")
    
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
            print(f"  🔍 第一个差异位置: 字节偏移 {diff_pos}")
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
        'syn_events': 0,
        'fin_events': 0,
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

def print_behavior_analysis(stats: dict, elapsed_time: float, file_size: int):
    """打印行为分析"""
    print(f"\n📈 高抖动网络传输行为分析:")
    print(f"  ⏰ 总超时次数: {stats['timeouts']} 次")
    print(f"  🔄 总重传次数: {stats['retransmissions']} 次")
    print(f"  📊 RTO更新次数: {stats['rto_updates']} 次")
    print(f"  📦 数据包发送: {stats['data_packets']} 个")
    print(f"  ✅ ACK包接收: {stats['ack_packets']} 个")
    print(f"  🔁 重复ACK: {stats['duplicate_acks']} 个")
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
        throughput_kbs = file_size / (elapsed_time * 1024)  # KB/s
        print(f"  📈 有效吞吐量: {throughput_kbs:.1f} KB/s")

if __name__ == "__main__":
    test_with_reordering_simulator()
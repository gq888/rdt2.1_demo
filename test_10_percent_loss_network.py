#!/usr/bin/env python3
"""
RDT2.1协议10%丢包率环境测试 - 使用网络模拟器
通过network_simulator.py创建真实的10%丢包环境
"""

import subprocess
import sys
import time
import os
from pathlib import Path

# 设置项目根目录
TEST_DIR = Path(__file__).parent
DOWNLOADS_DIR = TEST_DIR / "downloads"

def create_test_file(size_kb: int) -> Path:
    """创建测试文件"""
    test_file = TEST_DIR / f"lossy_test_{size_kb}kb.bin"
    with open(test_file, 'wb') as f:
        f.write(os.urandom(size_kb * 1024))
    return test_file

def test_10_percent_loss_with_network_simulator():
    """使用网络模拟器测试10%丢包率环境下的RDT2.1传输"""
    print("🎯 RDT2.1协议10%丢包率环境测试（使用网络模拟器）")
    print("="*80)
    
    # 确保下载目录存在
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    
    # 创建测试文件（30KB，适中的文件大小）
    test_file = create_test_file(30)
    print(f"📁 测试文件: {test_file.name} ({test_file.stat().st_size}B)")
    
    # 启动接收端（监听在6666端口）
    print("\n🔧 启动接收端...")
    recv_cmd = [sys.executable, "-m", "rdtftp.cli_recv", "--port", "6666", "--out-dir", str(DOWNLOADS_DIR)]
    recv_proc = subprocess.Popen(recv_cmd, cwd=str(TEST_DIR), 
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.0)  # 确保接收端启动
    
    # 启动网络模拟器（10%丢包率）
    print("🔧 启动网络模拟器（10%丢包率）...")
    sim_cmd = [
        sys.executable, "network_simulator.py",
        "--port", "6665", "--target-port", "6666",
        "--loss", "0.1",  # 10%丢包率
        "--delay", "10", "--jitter", "5"
    ]
    sim_proc = subprocess.Popen(sim_cmd, cwd=str(TEST_DIR),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(2.0)  # 更长的启动时间确保网络模拟器就绪
    
    # 发送文件（通过丢包网络）
    print(f"\n📤 开始传输文件（通过10%丢包网络）...")
    send_cmd = [
        sys.executable, "-m", "rdtftp.cli_send",
        "--file", str(test_file),
        "--host", "127.0.0.1", 
        "--port", "6665"  # 连接到网络模拟器
    ]
    
    start_time = time.time()
    result = subprocess.run(send_cmd, cwd=str(TEST_DIR), 
                           capture_output=True, text=True, timeout=180)  # 3分钟超时
    elapsed = time.time() - start_time
    
    print(f"\n⏱️  传输完成！用时: {elapsed:.3f}秒")
    print(f"返回码: {result.returncode}")
    
    if result.stdout:
        print(f"\n📋 详细传输日志:")
        for line in result.stdout.strip().split('\n'):
            print(f"  {line}")
    
    if result.stderr:
        print(f"\n⚠️  错误输出:")
        for line in result.stderr.strip().split('\n'):
            print(f"  {line}")
    
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
    if result.stdout:
        stats = {
            'timeouts': 0,
            'retransmissions': 0,
            'recoveries': 0,
            'data_chunks': 0,
            'syn_events': 0,
            'fin_events': 0,
            'progress_reports': 0,
            'rto_updates': 0,
            'packet_loss_events': 0
        }
        
        for line in result.stdout.strip().split('\n'):
            if '[TIMEOUT' in line:
                stats['timeouts'] += 1
            elif '重传' in line or 'retransmit' in line.lower():
                stats['retransmissions'] += 1
            elif '[RECOVERY]' in line:
                stats['recoveries'] += 1
            elif '[SYN]' in line and '->' in line:
                stats['syn_events'] += 1
            elif '[FIN]' in line:
                stats['fin_events'] += 1
            elif '[RTO-UPDATE]' in line:
                stats['rto_updates'] += 1
            elif '[PROGRESS]' in line and 'chunk=' in line:
                stats['progress_reports'] += 1
                import re
                match = re.search(r'chunk=(\d+)/(\d+)', line)
                if match:
                    current = int(match.group(1))
                    stats['data_chunks'] = max(stats['data_chunks'], current)
            elif '丢包事件' in line:
                stats['packet_loss_events'] += 1
        
        print(f"\n📈 10%丢包率网络传输行为分析:")
        print(f"  ✅ SYN握手: {'成功' if stats['syn_events'] > 0 else '失败'}")
        print(f"  📦 数据块传输: {stats['data_chunks']} 块")
        print(f"  📊 进度报告: {stats['progress_reports']} 次")
        print(f"  ⏰ 超时事件: {stats['timeouts']} 次")
        print(f"  🔄 重传事件: {stats['retransmissions']} 次")
        print(f"  ✅ 恢复事件: {stats['recoveries']} 次")
        print(f"  📦 丢包事件: {stats['packet_loss_events']} 次")
        print(f"  ⏱️  RTO更新: {stats['rto_updates']} 次")
        print(f"  🏁 FIN结束: {'成功' if stats['fin_events'] > 0 else '失败'}")
        
        if stats['timeouts'] > 0:
            recovery_rate = (stats['recoveries'] / stats['timeouts']) * 100
            print(f"  🎯 丢包恢复成功率: {recovery_rate:.1f}%")
            
        # 计算有效吞吐量
        if success and elapsed > 0:
            file_size_kb = test_file.stat().st_size / 1024
            effective_throughput = file_size_kb / elapsed
            print(f"  📈 有效吞吐量: {effective_throughput:.1f} KB/s")
            
            # 对比理论无丢包情况
            theoretical_throughput = effective_throughput * (1 / (1 - 0.1))  # 10%丢包的理论影响
            efficiency = (effective_throughput / theoretical_throughput) * 100
            print(f"  ⚡ 传输效率: {efficiency:.1f}% (相对于理论值)")
    
    # 清理
    print(f"\n{'='*80}")
    if success:
        print("🎉 10%丢包率网络测试成功！RDT2.1协议在网络干扰下仍能保证可靠性")
        print("💡 即使在真实的10%丢包网络环境下，协议仍能保证数据完整性和正确性")
    else:
        print("❌ 10%丢包率网络测试失败！高丢包网络环境对传输造成严重影响")
    
    # 终止进程
    try:
        recv_proc.terminate()
        recv_proc.wait(timeout=2)
    except:
        recv_proc.kill()
    
    if sim_proc:
        try:
            sim_proc.terminate()
            sim_proc.wait(timeout=2)
        except:
            sim_proc.kill()
    
    # 清理测试文件
    if test_file.exists():
        test_file.unlink()
    if received_file.exists():
        received_file.unlink()

if __name__ == "__main__":
    test_10_percent_loss_with_network_simulator()
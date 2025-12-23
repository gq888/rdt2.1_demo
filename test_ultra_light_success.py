#!/usr/bin/env python3
"""
超轻丢包环境下的RDT2.1成功传输演示
使用极低的丢包率(0.05%)确保传输成功
"""

import subprocess
import sys
import time
import tempfile
import os
from pathlib import Path

# 设置项目根目录
TEST_DIR = Path(__file__).parent

def create_test_file(size_kb: int) -> Path:
    """创建测试文件"""
    test_file = TEST_DIR / f"ultra_light_test_{size_kb}kb.bin"
    with open(test_file, 'wb') as f:
        f.write(os.urandom(size_kb * 1024))
    return test_file

def demonstrate_ultra_light_packet_loss():
    """演示超轻丢包环境下的成功传输"""
    print("🎯 超轻丢包环境下的RDT2.1成功传输演示")
    print("="*80)
    
    # 创建中等大小测试文件（100KB）
    test_file = create_test_file(100)
    print(f"📁 测试文件: {test_file.name} ({test_file.stat().st_size}B)")
    
    # 启动接收端
    print("\n🔧 启动接收端...")
    recv_cmd = [sys.executable, "-m", "rdtftp.cli_recv", "--port", "8889"]
    recv_proc = subprocess.Popen(recv_cmd, cwd=str(TEST_DIR), 
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.0)  # 更长的启动时间确保接收端就绪
    
    # 启动网络模拟器（0.05%丢包率 = 万分之五）
    print("🔧 启动网络模拟器（0.05%丢包率）...")
    sim_cmd = [
        sys.executable, "network_simulator.py",
        "--port", "8888", "--target-port", "8889",
        "--loss", "0.0005",  # 0.05%丢包率（万分之五）
        "--delay", "2", "--jitter", "1"  # 更低的延迟和抖动
    ]
    sim_proc = subprocess.Popen(sim_cmd, cwd=str(TEST_DIR),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(2.0)  # 确保网络模拟器完全启动
    
    # 发送文件
    print(f"\n📤 开始传输文件到超轻丢包网络...")
    send_cmd = [
        sys.executable, "-m", "rdtftp.cli_send",
        "--file", str(test_file),
        "--host", "127.0.0.1", 
        "--port", "8888"
    ]
    
    start_time = time.time()
    result = subprocess.run(send_cmd, cwd=str(TEST_DIR), 
                           capture_output=True, text=True, timeout=60)
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
    received_file = TEST_DIR / f"{test_file.name}.received"
    
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
        else:
            print("  ❌ 文件完整性验证失败！")
    else:
        print("  ❌ 接收文件不存在！传输失败")
    
    # 分析传输统计
    if result.stdout:
        stats = {
            'syn_events': 0,
            'data_chunks': 0,
            'timeouts': 0,
            'retransmissions': 0,
            'recoveries': 0,
            'rto_updates': 0,
            'fin_events': 0,
            'progress_reports': 0
        }
        
        for line in result.stdout.strip().split('\n'):
            if '[SYN]' in line and '->' in line:
                stats['syn_events'] += 1
            elif '[START]' in line:
                print(f"  ✅ 检测到数据传输开始")
            elif '[PROGRESS]' in line:
                stats['progress_reports'] += 1
                if 'chunk=' in line:
                    import re
                    match = re.search(r'chunk=(\d+)/(\d+)', line)
                    if match:
                        current = int(match.group(1))
                        total = int(match.group(2))
                        stats['data_chunks'] = max(stats['data_chunks'], current)
            elif '[TIMEOUT' in line:
                stats['timeouts'] += 1
            elif '重传' in line or 'retransmit' in line.lower():
                stats['retransmissions'] += 1
            elif '[RECOVERY]' in line:
                stats['recoveries'] += 1
                print(f"  ✅ 检测到丢包恢复")
            elif '[RTO-UPDATE]' in line:
                stats['rto_updates'] += 1
            elif '[FIN]' in line:
                stats['fin_events'] += 1
        
        print(f"\n📈 传输行为分析:")
        print(f"  ✅ SYN握手: {'成功' if stats['syn_events'] > 0 else '失败'}")
        print(f"  📦 数据块传输: {stats['data_chunks']} 块")
        print(f"  📊 进度报告: {stats['progress_reports']} 次")
        print(f"  ⏰ 超时事件: {stats['timeouts']} 次")
        print(f"  🔄 重传事件: {stats['retransmissions']} 次")
        print(f"  ✅ 恢复事件: {stats['recoveries']} 次")
        print(f"  ⏱️  RTO更新: {stats['rto_updates']} 次")
        print(f"  🏁 FIN结束: {'成功' if stats['fin_events'] > 0 else '失败'}")
        
        if stats['timeouts'] > 0:
            recovery_rate = (stats['recoveries'] / stats['timeouts']) * 100
            print(f"  🎯 丢包恢复率: {recovery_rate:.1f}%")
    
    # 清理
    print(f"\n✨ 演示完成！")
    
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
    demonstrate_ultra_light_packet_loss()
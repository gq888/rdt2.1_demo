#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDT2.1 网络模拟测试 - 简化版详细日志演示
专注于显示丢包重传过程的详细日志
"""

import os
import sys
import time
import subprocess
import hashlib
from pathlib import Path

# 测试配置
TEST_DIR = Path(__file__).parent
DOWNLOADS_DIR = TEST_DIR / "test_downloads_demo"
TEST_FILES_DIR = TEST_DIR / "test_files"
RECV_PORT = 9100
SIMULATOR_PORT = 9200
RECV_HOST = "127.0.0.1"

# 确保目录存在
DOWNLOADS_DIR.mkdir(exist_ok=True)
TEST_FILES_DIR.mkdir(exist_ok=True)

def sha256_file(path: Path) -> str:
    """计算文件SHA256哈希值"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def create_test_file(name: str, size_kb: int) -> Path:
    """创建测试文件"""
    file_path = TEST_FILES_DIR / name
    content = b"Demo content for RDT2.1 packet loss testing. " * (size_kb * 1024 // 45)
    file_path.write_bytes(content[:size_kb * 1024])
    return file_path

def start_receiver(port: int, output_dir: Path) -> subprocess.Popen:
    """启动接收端进程"""
    cmd = [
        sys.executable, "-m", "rdtftp.cli_recv",
        "--port", str(port),
        "--out-dir", str(output_dir)
    ]
    print(f"[接收端] 启动命令: {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=str(TEST_DIR))

def send_file_with_logging(file_path: Path, host: str, port: int, **kwargs) -> dict:
    """发送文件并详细记录传输过程"""
    cmd = [
        sys.executable, "-m", "rdtftp.cli_send",
        "--file", str(file_path),
        "--host", host,
        "--port", str(port)
    ]
    
    # 添加额外参数
    for key, value in kwargs.items():
        cmd.extend([f"--{key.replace('_', '-')}", str(value)])
    
    print(f"[发送端] 执行命令: {' '.join(cmd)}")
    start_time = time.time()
    result = subprocess.run(cmd, cwd=str(TEST_DIR), capture_output=True, text=True)
    elapsed = time.time() - start_time
    
    # 详细分析输出
    print(f"[传输详情] 用时: {elapsed:.3f}秒")
    
    if result.stdout:
        print("[传输输出] 详细日志:")
        lines = result.stdout.strip().split('\n')
        
        # 统计信息
        stats = {
            'syn_sent': 0,
            'syn_ack_received': 0,
            'data_packets': 0,
            'acks_received': 0,
            'retransmissions': 0,
            'timeouts': 0,
            'packet_loss_indications': 0,
            'rto_updates': 0
        }
        
        for line in lines:
            print(f"    {line}")
            
            # 分析每一行
            if '[SYN]' in line and '->' in line:
                stats['syn_sent'] += 1
                if '续传' in line:
                    print(f"    [分析] 检测到续传请求")
            elif '[SYN-ACK]' in line:
                stats['syn_ack_received'] += 1
            elif '[ACK]' in line and 'chunk=' in line:
                stats['acks_received'] += 1
                # 提取进度信息
                if 'chunk=' in line:
                    import re
                    match = re.search(r'chunk=(\d+)/(\d+)', line)
                    if match:
                        current = int(match.group(1))
                        total = int(match.group(2))
                        if total > 0:
                            progress = (current / total) * 100
                            print(f"    [分析] 传输进度: {progress:.1f}%")
            elif 'timeout' in line.lower() or '超时' in line.lower():
                stats['timeouts'] += 1
                print(f"    [分析] ⚠️ 检测到超时!")
            elif 'retransmit' in line.lower() or '重传' in line.lower():
                stats['retransmissions'] += 1
                print(f"    [分析] 🔄 检测到重传!")
            elif 'packet loss' in line.lower() or '丢包' in line.lower():
                stats['packet_loss_indications'] += 1
                print(f"    [分析] 📦 检测到丢包!")
            elif 'rto' in line.lower() and ('update' in line.lower() or '更新' in line.lower()):
                stats['rto_updates'] += 1
                print(f"    [分析] ⏱️ RTO超时时间更新")
        
        # 打印统计总结
        print(f"\n[传输统计]")
        print(f"    SYN发送: {stats['syn_sent']}")
        print(f"    SYN-ACK接收: {stats['syn_ack_received']}")
        print(f"    ACK接收: {stats['acks_received']}")
        print(f"    重传次数: {stats['retransmissions']}")
        print(f"    超时次数: {stats['timeouts']}")
        print(f"    丢包指示: {stats['packet_loss_indications']}")
        print(f"    RTO更新: {stats['rto_updates']}")
    
    if result.stderr:
        print("[错误输出]")
        for line in result.stderr.strip().split('\n'):
            print(f"    {line}")
    
    return {
        "success": result.returncode == 0,
        "elapsed": elapsed,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode
    }

def demo_normal_vs_packet_loss():
    """对比演示正常网络vs丢包网络"""
    print("=" * 60)
    print("RDT2.1 网络传输对比演示 - 正常 vs 丢包环境")
    print("=" * 60)
    
    # 创建测试文件
    test_file = create_test_file("demo_test.txt", 50)  # 50KB
    print(f"\n[准备] 创建测试文件: {test_file.name} ({test_file.stat().st_size} bytes)")
    
    # 测试1: 正常网络
    print(f"\n{'='*60}")
    print("[测试1] 正常网络环境 (无丢包)")
    print(f"{'='*60}")
    
    receiver1 = start_receiver(RECV_PORT, DOWNLOADS_DIR)
    time.sleep(0.8)
    
    try:
        result1 = send_file_with_logging(test_file, RECV_HOST, RECV_PORT)
        time.sleep(0.5)
        
        received_file1 = DOWNLOADS_DIR / "demo_test.txt"
        if received_file1.exists():
            hash1 = sha256_file(test_file)
            hash1_received = sha256_file(received_file1)
            success1 = hash1 == hash1_received
            print(f"\n[结果1] 文件完整性: {'✅ 通过' if success1 else '❌ 失败'}")
            print(f"[结果1] 传输时间: {result1['elapsed']:.3f}秒")
        else:
            print(f"\n[结果1] ❌ 接收文件不存在")
            success1 = False
            
    finally:
        receiver1.terminate()
        time.sleep(0.5)
    
    # 清理接收文件
    if (DOWNLOADS_DIR / "demo_test.txt").exists():
        (DOWNLOADS_DIR / "demo_test.txt").unlink()
    
    # 测试2: 丢包网络
    print(f"\n{'='*60}")
    print("[测试2] 丢包网络环境 (10% 丢包率)")
    print(f"{'='*60}")
    
    receiver2 = start_receiver(RECV_PORT, DOWNLOADS_DIR)
    time.sleep(0.8)
    
    # 启动网络模拟器
    simulator_cmd = [
        sys.executable, "network_simulator.py",
        "--listen-port", str(SIMULATOR_PORT),
        "--target-host", "127.0.0.1",
        "--target-port", str(RECV_PORT),
        "--loss-rate", "0.10",  # 10% 丢包率
        "--delay", "20",
        "--jitter", "10"
    ]
    
    print(f"\n[模拟器] 启动命令: {' '.join(simulator_cmd)}")
    simulator = subprocess.Popen(simulator_cmd, cwd=str(TEST_DIR))
    time.sleep(1.5)  # 等待模拟器启动
    
    try:
        result2 = send_file_with_logging(test_file, RECV_HOST, SIMULATOR_PORT)
        time.sleep(1.0)
        
        received_file2 = DOWNLOADS_DIR / "demo_test.txt"
        if received_file2.exists():
            hash2 = sha256_file(test_file)
            hash2_received = sha256_file(received_file2)
            success2 = hash2 == hash2_received
            print(f"\n[结果2] 文件完整性: {'✅ 通过' if success2 else '❌ 失败'}")
            print(f"[结果2] 传输时间: {result2['elapsed']:.3f}秒")
        else:
            print(f"\n[结果2] ❌ 接收文件不存在")
            success2 = False
            
    finally:
        simulator.terminate()
        try:
            simulator.wait(timeout=2.0)
        except:
            simulator.kill()
        receiver2.terminate()
        time.sleep(0.5)
    
    # 对比总结
    print(f"\n{'='*60}")
    print("[对比总结]")
    print(f"{'='*60}")
    print(f"正常网络环境:")
    print(f"  ✅ 文件传输: {'成功' if success1 else '失败'}")
    print(f"  ⏱️ 传输时间: {result1['elapsed']:.3f}秒")
    print(f"\n丢包网络环境 (10% 丢包率):")
    print(f"  ✅ 文件传输: {'成功' if success2 else '失败'}")
    print(f"  ⏱️ 传输时间: {result2['elapsed']:.3f}秒")
    
    if success1 and success2:
        time_diff = result2['elapsed'] - result1['elapsed']
        print(f"\n📊 性能影响:")
        print(f"  丢包环境额外用时: {time_diff:.3f}秒")
        print(f"  性能下降比例: {(time_diff/result1['elapsed']*100):.1f}%")
    
    return success1 and success2

def main():
    """主函数"""
    print("RDT2.1 详细日志网络模拟演示")
    print("本演示将对比正常网络与丢包网络的传输过程")
    print("重点关注丢包检测、重传机制、超时处理等细节")
    
    try:
        success = demo_normal_vs_packet_loss()
        if success:
            print(f"\n🎉 演示完成！所有测试均通过")
            return 0
        else:
            print(f"\n❌ 演示失败！部分测试未通过")
            return 1
    except KeyboardInterrupt:
        print(f"\n⚠️ 演示被用户中断")
        return 1
    except Exception as e:
        print(f"\n💥 演示出错: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
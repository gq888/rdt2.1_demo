#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDT2.1 网络模拟测试 - 详细日志版本
测试不同网络环境下的传输行为，包括丢包、延迟、抖动等场景
"""

import os
import sys
import time
import socket
import subprocess
import hashlib
import tempfile
import threading
from pathlib import Path

# 测试配置
TEST_DIR = Path(__file__).parent
DOWNLOADS_DIR = TEST_DIR / "test_downloads_net"
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
    content = b"Test content for RDT2.1 protocol testing. " * (size_kb * 1024 // 45)
    file_path.write_bytes(content[:size_kb * 1024])
    return file_path

def start_receiver(port: int, output_dir: Path) -> subprocess.Popen:
    """启动接收端进程"""
    cmd = [
        sys.executable, "-m", "rdtftp.cli_recv",
        "--port", str(port),
        "--out-dir", str(output_dir)
    ]
    print(f"  启动接收端: {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=str(TEST_DIR))

def send_file_verbose(file_path: Path, host: str, port: int, **kwargs) -> dict:
    """发送文件并返回统计信息（显示详细输出）"""
    cmd = [
        sys.executable, "-m", "rdtftp.cli_send",
        "--file", str(file_path),
        "--host", host,
        "--port", str(port)
        # 移除 --quiet 参数以显示详细输出
    ]
    
    # 添加额外参数
    for key, value in kwargs.items():
        cmd.extend([f"--{key.replace('_', '-')}", str(value)])
    
    print(f"  执行命令: {' '.join(cmd)}")
    start_time = time.time()
    result = subprocess.run(cmd, cwd=str(TEST_DIR), capture_output=True, text=True)
    elapsed = time.time() - start_time
    
    # 打印详细输出
    if result.stdout:
        print("  传输输出:")
        for line in result.stdout.strip().split('\n'):
            print(f"    {line}")
    if result.stderr:
        print("  错误输出:")
        for line in result.stderr.strip().split('\n'):
            print(f"    {line}")
    
    return {
        "success": result.returncode == 0,
        "elapsed": elapsed,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode
    }

class NetworkSimulator:
    """网络模拟器管理器"""
    
    def __init__(self):
        self.simulator_process = None
    
    def setup_simulator(self, loss_rate=0.0, delay_ms=0, jitter_ms=0):
        """设置网络模拟器"""
        cmd = [
            sys.executable, "network_simulator.py",
            "--listen-port", str(SIMULATOR_PORT),
            "--target-host", "127.0.0.1",
            "--target-port", str(RECV_PORT),
            "--loss-rate", str(loss_rate),
            "--delay", str(delay_ms),
            "--jitter", str(jitter_ms)
        ]
        print(f"  启动网络模拟器: {' '.join(cmd)}")
        self.simulator_process = subprocess.Popen(cmd, cwd=str(TEST_DIR))
        time.sleep(1.5)  # 等待模拟器启动
    
    def stop_simulator(self):
        """停止网络模拟器"""
        if self.simulator_process:
            self.simulator_process.terminate()
            try:
                self.simulator_process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.simulator_process.kill()
                self.simulator_process.wait()
            self.simulator_process = None

def analyze_transfer_output(stdout: str, stderr: str) -> dict:
    """分析传输输出，提取关键统计信息"""
    stats = {
        "total_packets": 0,
        "retransmissions": 0,
        "timeouts": 0,
        "duplicate_acks": 0,
        "packet_loss_detected": 0,
        "rto_updates": 0,
        "avg_rtt_ms": 0.0
    }
    
    if stdout:
        lines = stdout.split('\n')
        for line in lines:
            line = line.strip()
            # 统计重传
            if 'retransmit' in line.lower() or '重传' in line:
                stats["retransmissions"] += 1
            # 统计超时
            if 'timeout' in line.lower() or '超时' in line:
                stats["timeouts"] += 1
            # 统计重复ACK
            if 'duplicate ack' in line.lower() or '重复ack' in line:
                stats["duplicate_acks"] += 1
            # 统计丢包检测
            if 'packet loss' in line.lower() or '丢包' in line:
                stats["packet_loss_detected"] += 1
            # 统计RTO更新
            if 'rto' in line.lower() and ('update' in line.lower() or '更新' in line):
                stats["rto_updates"] += 1
            # 提取平均RTT
            if 'avg rtt' in line.lower() or '平均rtt' in line:
                try:
                    import re
                    numbers = re.findall(r'\d+\.?\d*', line)
                    if numbers:
                        stats["avg_rtt_ms"] = float(numbers[-1])
                except:
                    pass
    
    return stats

def test_normal_transmission():
    """测试正常网络环境下的传输"""
    print("\n=== 测试1: 正常网络环境 ===")
    
    # 创建测试文件
    test_file = create_test_file("normal_test.txt", 100)  # 100KB
    print(f"  创建测试文件: {test_file} ({test_file.stat().st_size} bytes)")
    
    # 启动接收端
    receiver = start_receiver(RECV_PORT, DOWNLOADS_DIR)
    time.sleep(0.5)
    
    try:
        # 发送文件
        result = send_file_verbose(test_file, RECV_HOST, RECV_PORT)
        
        # 等待文件写入完成
        time.sleep(0.5)
        
        # 验证结果
        received_file = DOWNLOADS_DIR / "normal_test.txt"
        success = received_file.exists()
        
        if success:
            original_hash = sha256_file(test_file)
            received_hash = sha256_file(received_file)
            hash_match = original_hash == received_hash
            print(f"  结果: {'成功' if hash_match else '失败'}")
            print(f"  用时: {result['elapsed']:.3f}秒")
            print(f"  文件完整性: {'通过' if hash_match else '不通过'}")
            
            # 分析传输统计
            stats = analyze_transfer_output(result['stdout'], result['stderr'])
            print(f"  传输统计:")
            print(f"    重传次数: {stats['retransmissions']}")
            print(f"    超时次数: {stats['timeouts']}")
            print(f"    丢包检测: {stats['packet_loss_detected']}")
            
            return hash_match
        else:
            print(f"  结果: 失败 - 接收文件不存在")
            return False
            
    finally:
        receiver.terminate()
        try:
            receiver.wait(timeout=1.0)
        except:
            receiver.kill()

def test_packet_loss_scenario():
    """测试丢包网络环境下的传输"""
    print("\n=== 测试2: 丢包网络环境 (5% 丢包率) ===")
    
    # 创建测试文件
    test_file = create_test_file("packet_loss_test.txt", 100)  # 100KB
    print(f"  创建测试文件: {test_file} ({test_file.stat().st_size} bytes)")
    
    # 启动接收端
    receiver = start_receiver(RECV_PORT, DOWNLOADS_DIR)
    time.sleep(0.5)
    
    # 设置网络模拟器
    simulator = NetworkSimulator()
    
    try:
        # 启动丢包模拟器
        simulator.setup_simulator(loss_rate=0.05, delay_ms=10, jitter_ms=5)
        
        # 通过模拟器发送文件
        result = send_file_verbose(test_file, RECV_HOST, SIMULATOR_PORT)
        
        # 等待文件写入完成
        time.sleep(1.0)
        
        # 验证结果
        received_file = DOWNLOADS_DIR / "packet_loss_test.txt"
        success = received_file.exists()
        
        if success:
            original_hash = sha256_file(test_file)
            received_hash = sha256_file(received_file)
            hash_match = original_hash == received_hash
            print(f"  结果: {'成功' if hash_match else '失败'}")
            print(f"  用时: {result['elapsed']:.3f}秒")
            print(f"  文件完整性: {'通过' if hash_match else '不通过'}")
            
            # 分析传输统计
            stats = analyze_transfer_output(result['stdout'], result['stderr'])
            print(f"  传输统计:")
            print(f"    重传次数: {stats['retransmissions']}")
            print(f"    超时次数: {stats['timeouts']}")
            print(f"    丢包检测: {stats['packet_loss_detected']}")
            print(f"    RTO更新: {stats['rto_updates']}")
            print(f"    平均RTT: {stats['avg_rtt_ms']:.1f}ms")
            
            return hash_match
        else:
            print(f"  结果: 失败 - 接收文件不存在")
            return False
            
    finally:
        simulator.stop_simulator()
        receiver.terminate()
        try:
            receiver.wait(timeout=1.0)
        except:
            receiver.kill()

def test_high_packet_loss_scenario():
    """测试高丢包率网络环境下的传输"""
    print("\n=== 测试3: 高丢包网络环境 (15% 丢包率) ===")
    
    # 创建测试文件
    test_file = create_test_file("extreme_test.txt", 50)  # 50KB
    print(f"  创建测试文件: {test_file} ({test_file.stat().st_size} bytes)")
    
    # 启动接收端
    receiver = start_receiver(RECV_PORT, DOWNLOADS_DIR)
    time.sleep(0.5)
    
    # 设置网络模拟器
    simulator = NetworkSimulator()
    
    try:
        # 启动高丢包模拟器
        simulator.setup_simulator(loss_rate=0.15, delay_ms=20, jitter_ms=10)
        
        # 通过模拟器发送文件
        result = send_file_verbose(test_file, RECV_HOST, SIMULATOR_PORT)
        
        # 等待文件写入完成
        time.sleep(2.0)
        
        # 验证结果
        received_file = DOWNLOADS_DIR / "extreme_test.txt"
        success = received_file.exists()
        
        if success:
            original_hash = sha256_file(test_file)
            received_hash = sha256_file(received_file)
            hash_match = original_hash == received_hash
            print(f"  结果: {'成功' if hash_match else '失败'}")
            print(f"  用时: {result['elapsed']:.3f}秒")
            print(f"  文件完整性: {'通过' if hash_match else '不通过'}")
            
            # 分析传输统计
            stats = analyze_transfer_output(result['stdout'], result['stderr'])
            print(f"  传输统计:")
            print(f"    重传次数: {stats['retransmissions']}")
            print(f"    超时次数: {stats['timeouts']}")
            print(f"    丢包检测: {stats['packet_loss_detected']}")
            print(f"    RTO更新: {stats['rto_updates']}")
            print(f"    平均RTT: {stats['avg_rtt_ms']:.1f}ms")
            
            return hash_match
        else:
            print(f"  结果: 失败 - 接收文件不存在")
            return False
            
    finally:
        simulator.stop_simulator()
        receiver.terminate()
        try:
            receiver.wait(timeout=1.0)
        except:
            receiver.kill()

def test_delay_scenario():
    """测试高延迟网络环境下的传输"""
    print("\n=== 测试4: 高延迟网络环境 (200ms 延迟) ===")
    
    # 创建测试文件
    test_file = create_test_file("delay_test.txt", 50)  # 50KB
    print(f"  创建测试文件: {test_file} ({test_file.stat().st_size} bytes)")
    
    # 启动接收端
    receiver = start_receiver(RECV_PORT, DOWNLOADS_DIR)
    time.sleep(0.5)
    
    # 设置网络模拟器
    simulator = NetworkSimulator()
    
    try:
        # 启动延迟模拟器
        simulator.setup_simulator(loss_rate=0.02, delay_ms=200, jitter_ms=50)
        
        # 通过模拟器发送文件
        result = send_file_verbose(test_file, RECV_HOST, SIMULATOR_PORT)
        
        # 等待文件写入完成
        time.sleep(2.0)
        
        # 验证结果
        received_file = DOWNLOADS_DIR / "delay_test.txt"
        success = received_file.exists()
        
        if success:
            original_hash = sha256_file(test_file)
            received_hash = sha256_file(received_file)
            hash_match = original_hash == received_hash
            print(f"  结果: {'成功' if hash_match else '失败'}")
            print(f"  用时: {result['elapsed']:.3f}秒")
            print(f"  文件完整性: {'通过' if hash_match else '不通过'}")
            
            # 分析传输统计
            stats = analyze_transfer_output(result['stdout'], result['stderr'])
            print(f"  传输统计:")
            print(f"    重传次数: {stats['retransmissions']}")
            print(f"    超时次数: {stats['timeouts']}")
            print(f"    丢包检测: {stats['packet_loss_detected']}")
            print(f"    RTO更新: {stats['rto_updates']}")
            print(f"    平均RTT: {stats['avg_rtt_ms']:.1f}ms")
            
            return hash_match
        else:
            print(f"  结果: 失败 - 接收文件不存在")
            return False
            
    finally:
        simulator.stop_simulator()
        receiver.terminate()
        try:
            receiver.wait(timeout=1.0)
        except:
            receiver.kill()

def test_mixed_issues_scenario():
    """测试混合网络问题环境"""
    print("\n=== 测试5: 混合网络问题 (丢包+延迟+抖动) ===")
    
    # 创建测试文件
    test_file = create_test_file("mixed_issues_test.txt", 50)  # 50KB
    print(f"  创建测试文件: {test_file} ({test_file.stat().st_size} bytes)")
    
    # 启动接收端
    receiver = start_receiver(RECV_PORT, DOWNLOADS_DIR)
    time.sleep(0.5)
    
    # 设置网络模拟器
    simulator = NetworkSimulator()
    
    try:
        # 启动混合问题模拟器
        simulator.setup_simulator(loss_rate=0.08, delay_ms=100, jitter_ms=30)
        
        # 通过模拟器发送文件
        result = send_file_verbose(test_file, RECV_HOST, SIMULATOR_PORT)
        
        # 等待文件写入完成
        time.sleep(2.0)
        
        # 验证结果
        received_file = DOWNLOADS_DIR / "mixed_issues_test.txt"
        success = received_file.exists()
        
        if success:
            original_hash = sha256_file(test_file)
            received_hash = sha256_file(received_file)
            hash_match = original_hash == received_hash
            print(f"  结果: {'成功' if hash_match else '失败'}")
            print(f"  用时: {result['elapsed']:.3f}秒")
            print(f"  文件完整性: {'通过' if hash_match else '不通过'}")
            
            # 分析传输统计
            stats = analyze_transfer_output(result['stdout'], result['stderr'])
            print(f"  传输统计:")
            print(f"    重传次数: {stats['retransmissions']}")
            print(f"    超时次数: {stats['timeouts']}")
            print(f"    丢包检测: {stats['packet_loss_detected']}")
            print(f"    RTO更新: {stats['rto_updates']}")
            print(f"    平均RTT: {stats['avg_rtt_ms']:.1f}ms")
            
            return hash_match
        else:
            print(f"  结果: 失败 - 接收文件不存在")
            return False
            
    finally:
        simulator.stop_simulator()
        receiver.terminate()
        try:
            receiver.wait(timeout=1.0)
        except:
            receiver.kill()

def test_interruption_and_resume():
    """测试传输中断和续传"""
    print("\n=== 测试6: 传输中断和续传 ===")
    
    # 创建测试文件
    test_file = create_test_file("interruption_test.txt", 200)  # 200KB
    print(f"  创建测试文件: {test_file} ({test_file.stat().st_size} bytes)")
    
    # 启动接收端
    receiver = start_receiver(RECV_PORT, DOWNLOADS_DIR)
    time.sleep(0.5)
    
    # 设置网络模拟器
    simulator = NetworkSimulator()
    
    try:
        print("  步骤1: 开始传输 (5% 丢包率)")
        simulator.setup_simulator(loss_rate=0.05, delay_ms=10, jitter_ms=5)
        
        # 开始传输，但会在中途停止模拟器来模拟中断
        import threading
        
        def stop_simulator_after_delay():
            time.sleep(2.0)  # 传输2秒后中断
            print("  步骤2: 模拟网络中断")
            simulator.stop_simulator()
        
        # 启动中断线程
        interrupt_thread = threading.Thread(target=stop_simulator_after_delay)
        interrupt_thread.start()
        
        # 开始传输（这会失败）
        result1 = send_file_verbose(test_file, RECV_HOST, SIMULATOR_PORT)
        interrupt_thread.join()
        
        print(f"  第一次传输结果: {'中断' if result1['returncode'] != 0 else '完成'}")
        
        # 等待一段时间
        time.sleep(1.0)
        
        print("  步骤3: 网络恢复，尝试续传")
        # 重新启动模拟器
        simulator.setup_simulator(loss_rate=0.02, delay_ms=10, jitter_ms=5)
        
        # 再次尝试传输（应该能续传）
        result2 = send_file_verbose(test_file, RECV_HOST, SIMULATOR_PORT)
        
        # 等待文件写入完成
        time.sleep(1.0)
        
        # 验证结果
        received_file = DOWNLOADS_DIR / "interruption_test.txt"
        success = received_file.exists()
        
        if success:
            original_hash = sha256_file(test_file)
            received_hash = sha256_file(received_file)
            hash_match = original_hash == received_hash
            print(f"  续传结果: {'成功' if hash_match else '失败'}")
            print(f"  总用时: {result1['elapsed'] + result2['elapsed']:.3f}秒")
            print(f"  文件完整性: {'通过' if hash_match else '不通过'}")
            
            # 分析传输统计
            stats1 = analyze_transfer_output(result1['stdout'], result1['stderr'])
            stats2 = analyze_transfer_output(result2['stdout'], result2['stderr'])
            print(f"  第一次传输统计:")
            print(f"    重传次数: {stats1['retransmissions']}")
            print(f"    超时次数: {stats1['timeouts']}")
            print(f"  续传统计:")
            print(f"    重传次数: {stats2['retransmissions']}")
            print(f"    超时次数: {stats2['timeouts']}")
            
            return hash_match
        else:
            print(f"  结果: 失败 - 接收文件不存在")
            return False
            
    finally:
        simulator.stop_simulator()
        receiver.terminate()
        try:
            receiver.wait(timeout=1.0)
        except:
            receiver.kill()

def compare_scenarios():
    """对比不同网络环境下的传输表现"""
    print("\n=== 网络环境对比分析 ===")
    
    results = {}
    
    # 运行各种场景测试
    results['normal'] = test_normal_transmission()
    results['packet_loss_5%'] = test_packet_loss_scenario()
    results['packet_loss_15%'] = test_high_packet_loss_scenario()
    results['high_delay'] = test_delay_scenario()
    results['mixed_issues'] = test_mixed_issues_scenario()
    results['interruption_resume'] = test_interruption_and_resume()
    
    # 输出对比总结
    print("\n=== 测试结果总结 ===")
    print("测试场景                    结果")
    print("-" * 40)
    for scenario, success in results.items():
        scenario_name = {
            'normal': '正常网络',
            'packet_loss_5%': '5%丢包率',
            'packet_loss_15%': '15%丢包率',
            'high_delay': '高延迟网络',
            'mixed_issues': '混合网络问题',
            'interruption_resume': '中断续传'
        }.get(scenario, scenario)
        print(f"{scenario_name:<20} {'通过' if success else '失败'}")
    
    passed = sum(results.values())
    total = len(results)
    print(f"\n总计: {passed}/{total} 测试通过")
    
    return results

def main():
    """主函数"""
    print("RDT2.1 网络模拟测试 - 详细日志版本")
    print("=" * 50)
    
    # 对比不同网络环境
    results = compare_scenarios()
    
    # 检查是否有失败的测试
    failed_tests = [name for name, success in results.items() if not success]
    if failed_tests:
        print(f"\n失败的测试: {', '.join(failed_tests)}")
        return 1
    else:
        print("\n所有测试均通过!")
        return 0

if __name__ == "__main__":
    sys.exit(main())
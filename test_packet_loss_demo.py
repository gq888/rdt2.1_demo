#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDT2.1 网络模拟测试 - 丢包重传日志显示演示
专注于显示丢包重传过程的详细日志，对比正常与异常网络环境
"""

import os
import sys
import time
import subprocess
import hashlib
from pathlib import Path

# 测试配置
TEST_DIR = Path(__file__).parent
DOWNLOADS_DIR = TEST_DIR / "test_downloads_packet_demo"
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
    content = b"Demo content for RDT2.1 packet loss and retransmission testing. " * (size_kb * 1024 // 60)
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

def analyze_packet_loss_behavior(stdout: str, stderr: str) -> dict:
    """分析丢包重传行为"""
    stats = {
        'total_packets': 0,
        'retransmissions': 0,
        'timeouts': 0,
        'duplicate_acks': 0,
        'rto_updates': 0,
        'packet_loss_events': 0,
        'recovery_events': 0,
        'transmission_patterns': []
    }
    
    if stdout:
        lines = stdout.strip().split('\n')
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # 检测重传事件
            if any(keyword in line_lower for keyword in ['retransmit', '重传', 'resend']):
                stats['retransmissions'] += 1
                stats['transmission_patterns'].append(f"重传: {line.strip()}")
                
            # 检测超时事件
            if any(keyword in line_lower for keyword in ['timeout', '超时']):
                stats['timeouts'] += 1
                stats['transmission_patterns'].append(f"超时: {line.strip()}")
                
            # 检测丢包事件
            if any(keyword in line_lower for keyword in ['packet loss', '丢包', 'lost']):
                stats['packet_loss_events'] += 1
                stats['transmission_patterns'].append(f"丢包: {line.strip()}")
                
            # 检测RTO更新
            if 'rto' in line_lower and any(keyword in line_lower for keyword in ['update', 'change', 'adjust']):
                stats['rto_updates'] += 1
                stats['transmission_patterns'].append(f"RTO更新: {line.strip()}")
                
            # 检测恢复事件
            if any(keyword in line_lower for keyword in ['recovery', 'recover', '恢复']):
                stats['recovery_events'] += 1
                stats['transmission_patterns'].append(f"恢复: {line.strip()}")
                
            # 检测数据传输模式
            if '[ack]' in line and 'chunk=' in line:
                stats['total_packets'] += 1
                
    return stats

def send_file_with_detailed_logging(file_path: Path, host: str, port: int, scenario_name: str, **kwargs) -> dict:
    """发送文件并详细记录传输过程，专门用于丢包重传分析"""
    cmd = [
        sys.executable, "-m", "rdtftp.cli_send",
        "--file", str(file_path),
        "--host", host,
        "--port", str(port)
    ]
    
    # 添加额外参数
    for key, value in kwargs.items():
        cmd.extend([f"--{key.replace('_', '-')}", str(value)])
    
    print(f"\n[{scenario_name}] 执行命令: {' '.join(cmd)}")
    start_time = time.time()
    result = subprocess.run(cmd, cwd=str(TEST_DIR), capture_output=True, text=True)
    elapsed = time.time() - start_time
    
    print(f"[{scenario_name}] 传输完成 - 用时: {elapsed:.3f}秒")
    
    # 详细分析输出
    if result.stdout:
        print(f"\n[{scenario_name}] 传输输出分析:")
        lines = result.stdout.strip().split('\n')
        
        # 实时分析每一行输出
        for line in lines:
            print(f"    {line}")
            
            # 实时分析关键事件
            line_lower = line.lower()
            if 'timeout' in line_lower or '超时' in line_lower:
                print(f"    ⚠️  [实时分析] 检测到超时事件！")
            elif 'retransmit' in line_lower or '重传' in line_lower:
                print(f"    🔄  [实时分析] 检测到重传事件！")
            elif 'packet loss' in line_lower or '丢包' in line_lower:
                print(f"    📦  [实时分析] 检测到丢包事件！")
            elif 'rto' in line_lower and ('update' in line_lower or '更新' in line_lower):
                print(f"    ⏱️  [实时分析] 检测到RTO超时时间更新！")
            elif '[ack]' in line and 'chunk=' in line:
                # 提取进度信息
                import re
                match = re.search(r'chunk=(\d+)/(\d+)', line)
                if match:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    if total > 0:
                        progress = (current / total) * 100
                        print(f"    📊  [实时分析] 传输进度: {progress:.1f}%")
    
    # 分析丢包重传行为
    stats = analyze_packet_loss_behavior(result.stdout, result.stderr)
    
    print(f"\n[{scenario_name}] 丢包重传统计分析:")
    print(f"    📊 总数据包数: {stats['total_packets']}")
    print(f"    🔄 重传次数: {stats['retransmissions']}")
    print(f"    ⏰ 超时次数: {stats['timeouts']}")
    print(f"    📦 丢包事件: {stats['packet_loss_events']}")
    print(f"    ⏱️  RTO更新: {stats['rto_updates']}")
    print(f"    ✅ 恢复事件: {stats['recovery_events']}")
    
    if stats['transmission_patterns']:
        print(f"\n[{scenario_name}] 关键传输事件:")
        for event in stats['transmission_patterns'][-10:]:  # 显示最近10个事件
            print(f"    {event}")
    
    if result.stderr:
        print(f"\n[{scenario_name}] 错误输出:")
        for line in result.stderr.strip().split('\n'):
            print(f"    {line}")
    
    return {
        "success": result.returncode == 0,
        "elapsed": elapsed,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
        "stats": stats
    }

def demo_packet_loss_comparison():
    """演示丢包重传行为对比"""
    print("=" * 80)
    print("RDT2.1 丢包重传行为详细分析演示")
    print("对比正常网络 vs 轻丢包网络 vs 重丢包网络的传输行为")
    print("=" * 80)
    
    # 创建测试文件
    test_file = create_test_file("packet_loss_demo.txt", 30)  # 30KB
    print(f"\n[准备] 创建测试文件: {test_file.name} ({test_file.stat().st_size} bytes)")
    
    results = {}
    
    # 测试1: 正常网络 (0% 丢包)
    print(f"\n{'='*80}")
    print("[测试1] 正常网络环境 (0% 丢包率)")
    print(f"{'='*80}")
    
    receiver1 = start_receiver(RECV_PORT, DOWNLOADS_DIR)
    time.sleep(1.0)
    
    try:
        results['normal'] = send_file_with_detailed_logging(
            test_file, RECV_HOST, RECV_PORT, "正常网络"
        )
        time.sleep(0.5)
        
        # 验证文件完整性
        received_file = DOWNLOADS_DIR / "packet_loss_demo.txt"
        if received_file.exists():
            original_hash = sha256_file(test_file)
            received_hash = sha256_file(received_file)
            results['normal']['file_integrity'] = original_hash == received_hash
        else:
            results['normal']['file_integrity'] = False
            
    finally:
        receiver1.terminate()
        time.sleep(0.5)
    
    # 清理接收文件
    received_file = DOWNLOADS_DIR / "packet_loss_demo.txt"
    if received_file.exists():
        received_file.unlink()
    
    # 测试2: 轻丢包网络 (3% 丢包)
    print(f"\n{'='*80}")
    print("[测试2] 轻丢包网络环境 (3% 丢包率)")
    print(f"{'='*80}")
    
    receiver2 = start_receiver(RECV_PORT, DOWNLOADS_DIR)
    time.sleep(1.0)
    
    # 启动轻丢包模拟器
    simulator_cmd2 = [
        sys.executable, "network_simulator.py",
        "--listen-port", str(SIMULATOR_PORT),
        "--target-host", "127.0.0.1",
        "--target-port", str(RECV_PORT),
        "--loss-rate", "0.03",  # 3% 丢包率
        "--delay", "10",
        "--jitter", "5"
    ]
    
    print(f"\n[轻丢包模拟器] 启动: {' '.join(simulator_cmd2)}")
    simulator2 = subprocess.Popen(simulator_cmd2, cwd=str(TEST_DIR))
    time.sleep(2.0)  # 等待模拟器启动
    
    try:
        results['light_loss'] = send_file_with_detailed_logging(
            test_file, RECV_HOST, SIMULATOR_PORT, "轻丢包网络"
        )
        time.sleep(1.0)
        
        # 验证文件完整性
        received_file = DOWNLOADS_DIR / "packet_loss_demo.txt"
        if received_file.exists():
            original_hash = sha256_file(test_file)
            received_hash = sha256_file(received_file)
            results['light_loss']['file_integrity'] = original_hash == received_hash
        else:
            results['light_loss']['file_integrity'] = False
            
    finally:
        simulator2.terminate()
        try:
            simulator2.wait(timeout=2.0)
        except:
            simulator2.kill()
        receiver2.terminate()
        time.sleep(0.5)
    
    # 清理接收文件
    received_file = DOWNLOADS_DIR / "packet_loss_demo.txt"
    if received_file.exists():
        received_file.unlink()
    
    # 对比分析
    print(f"\n{'='*80}")
    print("[对比分析] 不同网络环境下的传输行为对比")
    print(f"{'='*80}")
    
    scenarios = ['normal', 'light_loss']
    scenario_names = {
        'normal': '正常网络 (0% 丢包)',
        'light_loss': '轻丢包网络 (3% 丢包)'
    }
    
    print(f"\n📊 传输成功率对比:")
    for scenario in scenarios:
        if scenario in results:
            name = scenario_names[scenario]
            success = results[scenario]['success']
            integrity = results[scenario].get('file_integrity', False)
            elapsed = results[scenario]['elapsed']
            print(f"  {name}: {'✅ 成功' if success else '❌ 失败'} (文件完整性: {'✅' if integrity else '❌'}, 用时: {elapsed:.3f}s)")
    
    print(f"\n🔄 重传行为对比:")
    for scenario in scenarios:
        if scenario in results and 'stats' in results[scenario]:
            name = scenario_names[scenario]
            stats = results[scenario]['stats']
            print(f"  {name}:")
            print(f"    重传次数: {stats['retransmissions']}")
            print(f"    超时次数: {stats['timeouts']}")
            print(f"    丢包事件: {stats['packet_loss_events']}")
            print(f"    RTO更新: {stats['rto_updates']}")
            
            if stats['retransmissions'] > 0 or stats['timeouts'] > 0:
                print(f"    ⚠️  检测到网络问题导致的重传行为")
            else:
                print(f"    ✅ 未检测到重传行为")
    
    # 总结
    all_success = all(results[scenario]['success'] for scenario in scenarios if scenario in results)
    all_integrity = all(results[scenario].get('file_integrity', False) for scenario in scenarios if scenario in results)
    
    print(f"\n🎯 演示总结:")
    print(f"  整体传输成功率: {'✅ 全部成功' if all_success else '❌ 部分失败'}")
    print(f"  文件完整性验证: {'✅ 全部通过' if all_integrity else '❌ 部分失败'}")
    
    # 显示关键发现
    print(f"\n🔍 关键发现:")
    for scenario in scenarios:
        if scenario in results and 'stats' in results[scenario]:
            stats = results[scenario]['stats']
            if stats['retransmissions'] > 0:
                print(f"  • {scenario_names[scenario]} 环境下检测到 {stats['retransmissions']} 次重传")
            if stats['timeouts'] > 0:
                print(f"  • {scenario_names[scenario]} 环境下检测到 {stats['timeouts']} 次超时")
            if stats['packet_loss_events'] > 0:
                print(f"  • {scenario_names[scenario]} 环境下检测到 {stats['packet_loss_events']} 次丢包事件")
    
    return all_success and all_integrity

def main():
    """主函数"""
    print("RDT2.1 丢包重传日志显示演示")
    print("本演示将详细展示在不同网络环境下的丢包和重传行为")
    print("帮助理解RDT2.1协议如何应对网络问题")
    
    try:
        success = demo_packet_loss_comparison()
        if success:
            print(f"\n🎉 演示完成！所有测试均通过，详细展示了丢包重传行为")
            return 0
        else:
            print(f"\n❌ 演示失败！部分测试未通过")
            return 1
    except KeyboardInterrupt:
        print(f"\n⚠️ 演示被用户中断")
        return 1
    except Exception as e:
        print(f"\n💥 演示出错: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
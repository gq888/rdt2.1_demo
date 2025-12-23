#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDT2.1 丢包重传可视化演示
展示不同丢包率下的传输行为和重传统计
"""

import subprocess
import time
import sys
from pathlib import Path
import json

# 测试目录
TEST_DIR = Path(__file__).parent
DOWNLOADS_DIR = TEST_DIR / "downloads_visualization"

def create_test_files():
    """创建不同大小的测试文件"""
    files = {}
    
    # 小文件 (10KB) - 用于快速测试
    small_file = TEST_DIR / "test_small_10kb.txt"
    small_file.write_text("RDT2.1 Test Data " * 500)  # 约10KB
    files['small'] = small_file
    
    # 中等文件 (100KB) - 用于观察重传行为
    medium_file = TEST_DIR / "test_medium_100kb.txt"
    medium_file.write_text("RDT2.1 Test Data " * 5000)  # 约100KB
    files['medium'] = medium_file
    
    # 大文件 (1MB) - 用于压力测试
    large_file = TEST_DIR / "test_large_1mb.txt"
    large_file.write_text("RDT2.1 Test Data " * 50000)  # 约1MB
    files['large'] = large_file
    
    return files

def run_single_test(file_path: Path, loss_rate: float, test_name: str) -> dict:
    """运行单次测试"""
    print(f"\n{'='*80}")
    print(f"🎯 {test_name} - 丢包率: {loss_rate*100:.0f}%")
    print(f"📁 测试文件: {file_path.name} ({file_path.stat().st_size}B)")
    print('='*80)
    
    # 确保下载目录存在
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    
    # 清理之前的下载文件
    for old_file in DOWNLOADS_DIR.glob("test_*.txt"):
        old_file.unlink(missing_ok=True)
    
    # 启动接收端
    recv_cmd = [sys.executable, "-m", "rdtftp.cli_recv", "--port", "6666", "--out-dir", str(DOWNLOADS_DIR)]
    recv_proc = subprocess.Popen(recv_cmd, cwd=str(TEST_DIR), 
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    time.sleep(1.0)
    
    # 启动网络模拟器
    sim_cmd = [
        sys.executable, "network_simulator_fixed.py",
        "--listen-port", "6665",
        "--target-host", "127.0.0.1",
        "--target-port", "6666",
        "--loss-rate", str(loss_rate),
        "--delay", "10", "--jitter", "5"
    ]
    sim_proc = subprocess.Popen(sim_cmd, cwd=str(TEST_DIR),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    time.sleep(2.0)
    
    try:
        # 发送文件
        send_cmd = [
            sys.executable, "-m", "rdtftp.cli_send",
            "--file", str(file_path),
            "--host", "127.0.0.1", 
            "--port", "6665",
            "--rto", "0.3",
            "--max-retry", "50"
        ]
        
        start_time = time.time()
        result = subprocess.run(send_cmd, cwd=str(TEST_DIR), 
                               capture_output=True, text=True, timeout=120)
        elapsed = time.time() - start_time
        
        success = result.returncode == 0
        
        # 验证文件完整性
        downloaded_file = DOWNLOADS_DIR / file_path.name
        integrity_ok = False
        if downloaded_file.exists():
            original_content = file_path.read_bytes()
            downloaded_content = downloaded_file.read_bytes()
            integrity_ok = original_content == downloaded_content
        
        # 提取统计信息
        stats = extract_stats_from_output(result.stdout)
        
        print(f"\n📊 测试结果:")
        print(f"   状态: {'✅ 成功' if success else '❌ 失败'}")
        print(f"   用时: {elapsed:.2f}s")
        print(f"   文件完整性: {'✅ 通过' if integrity_ok else '❌ 失败'}")
        
        if stats:
            print(f"   总数据包: {stats['total_packets']}")
            print(f"   重传次数: {stats['retransmissions']}")
            print(f"   超时次数: {stats['timeouts']}")
            print(f"   丢包事件: {stats['packet_loss_events']}")
            print(f"   有效丢包率: {stats['loss_rate']:.1f}%")
            print(f"   吞吐量: {stats['throughput']:.2f} KB/s")
        
        return {
            'success': success,
            'elapsed': elapsed,
            'integrity_ok': integrity_ok,
            'stats': stats,
            'stdout': result.stdout,
            'stderr': result.stderr
        }
        
    except subprocess.TimeoutExpired:
        print("❌ 传输超时")
        return {'success': False, 'error': 'timeout'}
    except Exception as e:
        print(f"❌ 测试错误: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        sim_proc.terminate()
        recv_proc.terminate()
        
        try:
            sim_proc.wait(timeout=2.0)
            recv_proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            sim_proc.kill()
            recv_proc.kill()

def extract_stats_from_output(output: str) -> dict:
    """从输出中提取统计信息"""
    stats = {
        'total_packets': 0,
        'retransmissions': 0,
        'timeouts': 0,
        'packet_loss_events': 0,
        'loss_rate': 0.0,
        'throughput': 0.0
    }
    
    lines = output.split('\n')
    for line in lines:
        if '总数据包数:' in line:
            try:
                stats['total_packets'] = int(line.split('总数据包数:')[1].strip())
            except:
                pass
        elif '重传次数:' in line:
            try:
                stats['retransmissions'] = int(line.split('重传次数:')[1].strip())
            except:
                pass
        elif '超时次数:' in line:
            try:
                stats['timeouts'] = int(line.split('超时次数:')[1].strip())
            except:
                pass
        elif '丢包事件:' in line:
            try:
                stats['packet_loss_events'] = int(line.split('丢包事件:')[1].strip())
            except:
                pass
        elif '有效丢包率:' in line:
            try:
                stats['loss_rate'] = float(line.split('有效丢包率:')[1].strip().replace('%', ''))
            except:
                pass
        elif 'goodput=' in line:
            try:
                # 提取 goodput 值 (MiB/s) 并转换为 KB/s
                import re
                match = re.search(r'goodput=([\d.]+) MiB/s', line)
                if match:
                    goodput_mib = float(match.group(1))
                    stats['throughput'] = goodput_mib * 1024  # MiB/s to KB/s
            except:
                pass
    
    return stats

def main():
    """主测试函数"""
    print("="*80)
    print("🧪 RDT2.1 丢包重传可视化演示")
    print("="*80)
    
    # 创建测试文件
    test_files = create_test_files()
    
    # 测试配置
    loss_rates = [0.0, 0.01, 0.05, 0.1, 0.15]  # 0%, 1%, 5%, 10%, 15%
    
    all_results = {}
    
    for file_size, file_path in test_files.items():
        print(f"\n{'#'*80}")
        print(f"# 📁 文件大小: {file_size.upper()} ({file_path.stat().st_size}B)")
        print(f"{'#'*80}")
        
        file_results = {}
        
        for loss_rate in loss_rates:
            test_name = f"{file_size.upper()}-{int(loss_rate*100)}%"
            result = run_single_test(file_path, loss_rate, test_name)
            file_results[loss_rate] = result
            
            # 如果小文件测试失败，跳过后续测试
            if file_size == 'small' and not result['success']:
                print(f"\n⚠️  小文件测试失败，跳过后续测试")
                break
        
        all_results[file_size] = file_results
    
    # 生成总结报告
    print("\n" + "="*80)
    print("📊 RDT2.1 丢包重传行为总结报告")
    print("="*80)
    
    for file_size, file_results in all_results.items():
        print(f"\n📁 文件大小: {file_size.upper()}")
        print("-" * 60)
        print(f"{'丢包率':>8} | {'状态':>6} | {'用时(s)':>8} | {'重传':>6} | {'超时':>6} | {'丢包事件':>8} | {'吞吐量(KB/s)':>12}")
        print("-" * 60)
        
        for loss_rate, result in file_results.items():
            if result['success'] and result['stats']:
                stats = result['stats']
                status = "✅ 成功"
                print(f"{loss_rate*100:>7.0f}% | {status:>6} | {result['elapsed']:>8.2f} | "
                      f"{stats['retransmissions']:>6} | {stats['timeouts']:>6} | "
                      f"{stats['packet_loss_events']:>8} | {stats['throughput']:>12.1f}")
            else:
                status = "❌ 失败"
                print(f"{loss_rate*100:>7.0f}% | {status:>6} | {result.get('elapsed', 0):>8.2f} | "
                      f"{'-':>6} | {'-':>6} | {'-':>8} | {'-':>12}")
    
    # 清理测试文件
    for file_path in test_files.values():
        file_path.unlink(missing_ok=True)
    
    print(f"\n✅ 测试完成！")
    return all_results

if __name__ == "__main__":
    results = main()
    sys.exit(0)
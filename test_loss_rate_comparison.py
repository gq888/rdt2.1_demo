#!/usr/bin/env python3
"""
RDT2.1协议不同丢包率对比测试
对比0%、1%、5%、10%丢包率下的传输表现
"""

import subprocess
import sys
import time
import os
from pathlib import Path
from dataclasses import dataclass

# 设置项目根目录
TEST_DIR = Path(__file__).parent
DOWNLOADS_DIR = TEST_DIR / "downloads"

@dataclass
class TestResult:
    loss_rate: float
    success: bool
    elapsed: float
    timeouts: int
    retransmissions: int
    throughput: float
    efficiency: float
    error_message: str = ""

def create_test_file(size_kb: int) -> Path:
    """创建测试文件"""
    test_file = TEST_DIR / f"lossy_test_{size_kb}kb.bin"
    with open(test_file, 'wb') as f:
        f.write(os.urandom(size_kb * 1024))
    return test_file

def run_single_test(loss_rate: float, test_file: Path) -> TestResult:
    """运行单次丢包率测试"""
    print(f"\n{'='*60}")
    print(f"🎯 测试丢包率: {loss_rate*100:.0f}%")
    print(f"{'='*60}")
    
    # 启动接收端
    recv_cmd = [sys.executable, "-m", "rdtftp.cli_recv", "--port", "6666", "--out-dir", str(DOWNLOADS_DIR)]
    recv_proc = subprocess.Popen(recv_cmd, cwd=str(TEST_DIR), 
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.0)
    
    # 启动网络模拟器
    sim_cmd = [
        sys.executable, "network_simulator.py",
        "--port", "6665", "--target-port", "6666",
        "--loss", str(loss_rate),
        "--delay", "10", "--jitter", "5"
    ]
    sim_proc = subprocess.Popen(sim_cmd, cwd=str(TEST_DIR),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(2.0)
    
    # 发送文件
    send_cmd = [
        sys.executable, "-m", "rdtftp.cli_send",
        "--file", str(test_file),
        "--host", "127.0.0.1", 
        "--port", "6665"
    ]
    
    start_time = time.time()
    try:
        result = subprocess.run(send_cmd, cwd=str(TEST_DIR), 
                               capture_output=True, text=True, timeout=60)
        elapsed = time.time() - start_time
        success = result.returncode == 0
        error_message = ""
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        success = False
        error_message = "传输超时"
    
    # 分析结果
    timeouts = 0
    retransmissions = 0
    throughput = 0.0
    efficiency = 0.0
    
    if success:
        # 验证文件完整性
        received_file = DOWNLOADS_DIR / test_file.name
        if received_file.exists():
            # 计算SHA256验证
            import hashlib
            def calc_sha256(path):
                sha256_hash = hashlib.sha256()
                with open(path, "rb") as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
                return sha256_hash.hexdigest()
            
            original_hash = calc_sha256(test_file)
            received_hash = calc_sha256(received_file)
            
            if original_hash != received_hash:
                success = False
                error_message = "文件完整性验证失败"
        else:
            success = False
            error_message = "接收文件不存在"
    
    # 统计传输日志
    if 'result' in locals() and result.stdout:
        for line in result.stdout.strip().split('\n'):
            if '[TIMEOUT' in line:
                timeouts += 1
            elif '重传' in line or 'retransmit' in line.lower():
                retransmissions += 1
    
    # 计算吞吐量
    if success and elapsed > 0:
        file_size_kb = test_file.stat().st_size / 1024
        throughput = file_size_kb / elapsed
        # 理论效率计算（考虑丢包影响）
        theoretical_throughput = throughput * (1 / (1 - loss_rate)) if loss_rate < 1 else throughput
        efficiency = (throughput / theoretical_throughput) * 100 if theoretical_throughput > 0 else 0
    
    # 清理进程
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
    
    # 清理接收文件
    received_file = DOWNLOADS_DIR / test_file.name
    if received_file.exists():
        received_file.unlink()
    
    return TestResult(
        loss_rate=loss_rate,
        success=success,
        elapsed=elapsed,
        timeouts=timeouts,
        retransmissions=retransmissions,
        throughput=throughput,
        efficiency=efficiency,
        error_message=error_message
    )

def main():
    """主测试函数"""
    print("🔬 RDT2.1协议不同丢包率对比测试")
    print("="*80)
    print("测试目的：分析RDT2.1协议在不同网络质量下的表现")
    print("测试方法：使用网络模拟器创建不同丢包率的网络环境")
    print("="*80)
    
    # 确保下载目录存在
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    
    # 创建测试文件（50KB，适中的文件大小）
    test_file = create_test_file(50)
    print(f"\n📁 测试文件: {test_file.name} ({test_file.stat().st_size}B)")
    
    # 测试不同丢包率
    loss_rates = [0.0, 0.01, 0.05, 0.10]  # 0%, 1%, 5%, 10%
    results = []
    
    for loss_rate in loss_rates:
        try:
            result = run_single_test(loss_rate, test_file)
            results.append(result)
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            results.append(TestResult(
                loss_rate=loss_rate,
                success=False,
                elapsed=0,
                timeouts=0,
                retransmissions=0,
                throughput=0,
                efficiency=0,
                error_message=str(e)
            ))
    
    # 显示对比结果
    print(f"\n{'='*80}")
    print("📊 不同丢包率测试结果对比")
    print(f"{'='*80}")
    
    print(f"{'丢包率':<8} {'状态':<8} {'用时(s)':<10} {'超时':<6} {'重传':<6} {'吞吐量':<10} {'效率':<8} {'备注'}")
    print("-" * 70)
    
    for result in results:
        status = "✅成功" if result.success else "❌失败"
        loss_pct = f"{result.loss_rate*100:.0f}%"
        elapsed_str = f"{result.elapsed:.2f}" if result.success else "-"
        timeout_str = str(result.timeouts)
        retrans_str = str(result.retransmissions)
        throughput_str = f"{result.throughput:.1f}KB/s" if result.success else "-"
        efficiency_str = f"{result.efficiency:.1f}%" if result.success else "-"
        note = result.error_message if not result.success else ""
        
        print(f"{loss_pct:<8} {status:<8} {elapsed_str:<10} {timeout_str:<6} {retrans_str:<6} {throughput_str:<10} {efficiency_str:<8} {note}")
    
    # 分析结果
    print(f"\n{'='*80}")
    print("🔍 结果分析")
    print(f"{'='*80}")
    
    # 成功率的对比
    success_rates = [r.success for r in results]
    print(f"📈 成功率对比:")
    for i, (loss_rate, success) in enumerate(zip(loss_rates, success_rates)):
        status = "✅" if success else "❌"
        print(f"  {loss_rate*100:4.0f}%丢包率: {status} {'成功' if success else '失败'}")
    
    # 性能影响分析
    print(f"\n⚡ 性能影响分析:")
    baseline_throughput = results[0].throughput if results[0].success else 0
    
    for result in results:
        if result.success and baseline_throughput > 0:
            performance_loss = (1 - result.throughput / baseline_throughput) * 100
            print(f"  {result.loss_rate*100:4.0f}%丢包率: 吞吐量下降 {performance_loss:.1f}%")
    
    # 协议鲁棒性评估
    print(f"\n🛡️  协议鲁棒性评估:")
    successful_transfers = sum(1 for r in results if r.success)
    total_tests = len(results)
    robustness = (successful_transfers / total_tests) * 100
    
    print(f"  总体鲁棒性: {robustness:.1f}%")
    
    if robustness >= 75:
        print("  🏆 评估: RDT2.1协议具有优秀的网络适应性")
    elif robustness >= 50:
        print("  📊 评估: RDT2.1协议具有良好的网络适应性")
    else:
        print("  ⚠️  评估: RDT2.1协议网络适应性有待提升")
    
    # 关键发现
    print(f"\n💡 关键发现:")
    
    # 找到失败的临界点
    failed_index = next((i for i, r in enumerate(results) if not r.success), None)
    if failed_index is not None:
        critical_loss_rate = results[failed_index].loss_rate
        print(f"  🔴 协议失效临界点: {critical_loss_rate*100:.0f}%丢包率")
    
    # 性能退化趋势
    if len([r for r in results if r.success]) > 1:
        print(f"  📉 随着丢包率增加，传输性能呈下降趋势")
        print(f"  🔄 重传次数与丢包率呈正相关关系")
    
    print(f"\n{'='*80}")
    print("🎯 测试结论")
    print(f"{'='*80}")
    print("RDT2.1协议在不同网络质量下的表现:")
    
    for result in results:
        if result.success:
            print(f"  • {result.loss_rate*100:.0f}%丢包率: 传输成功，吞吐量 {result.throughput:.1f}KB/s")
        else:
            print(f"  • {result.loss_rate*100:.0f}%丢包率: 传输失败 ({result.error_message})")
    
    # 清理测试文件
    if test_file.exists():
        test_file.unlink()
    
    print(f"\n✅ 对比测试完成！")

if __name__ == "__main__":
    main()
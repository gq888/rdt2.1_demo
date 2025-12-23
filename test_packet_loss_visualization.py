#!/usr/bin/env python3
"""
可视化丢包重传行为演示
专门用于展示详细的丢包检测和重传机制
"""
import subprocess
import time
import sys
from pathlib import Path

TEST_DIR = Path(__file__).parent

def create_test_file(size_kb: int = 50) -> Path:
    """创建测试文件"""
    test_file = TEST_DIR / f"test_{size_kb}kb.bin"
    with open(test_file, 'wb') as f:
        f.write(b'A' * (size_kb * 1024))
    return test_file

def run_single_transfer_with_logging(file_path: Path, scenario_name: str, packet_loss_rate: float = 0.0):
    """运行单次传输并捕获详细日志"""
    print(f"\n{'='*80}")
    print(f"[{scenario_name}] 网络环境: {packet_loss_rate}% 丢包率")
    print(f"[{scenario_name}] 测试文件: {file_path.name} ({file_path.stat().st_size}B)")
    print(f"{'='*80}")
    
    # 启动接收端
    recv_cmd = [sys.executable, "-m", "rdtftp.cli_recv", "--port", "9999"]
    recv_proc = subprocess.Popen(recv_cmd, cwd=str(TEST_DIR), 
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(0.5)  # 确保接收端启动
    
    # 启动网络模拟器
    if packet_loss_rate > 0:
        sim_cmd = [
            sys.executable, "network_simulator.py",
            "--port", "9998", "--target-port", "9999",
            "--loss", str(packet_loss_rate/100),
            "--delay", "10", "--jitter", "5"
        ]
        sim_proc = subprocess.Popen(sim_cmd, cwd=str(TEST_DIR),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        target_port = 9998
        time.sleep(1.0)  # 更长的启动时间
    else:
        sim_proc = None
        target_port = 9999
    
    # 发送文件
    send_cmd = [
        sys.executable, "-m", "rdtftp.cli_send",
        "--file", str(file_path),
        "--host", "127.0.0.1",
        "--port", str(target_port)
    ]
    
    print(f"[{scenario_name}] 执行命令: {' '.join(send_cmd)}")
    start_time = time.time()
    
    result = subprocess.run(send_cmd, cwd=str(TEST_DIR), capture_output=True, text=True)
    elapsed = time.time() - start_time
    
    print(f"\n[{scenario_name}] 传输结果:")
    print(f"  返回码: {result.returncode}")
    print(f"  用时: {elapsed:.3f}秒")
    
    # 分析输出中的关键事件
    if result.stdout:
        print(f"\n[{scenario_name}] 传输日志分析:")
        lines = result.stdout.strip().split('\n')
        
        events = {
            'timeouts': 0,
            'retransmissions': 0,
            'packet_loss': 0,
            'rto_updates': 0,
            'recoveries': 0,
            'progress_updates': 0
        }
        
        for line in lines:
            print(f"  {line}")
            
            # 事件检测
            if 'TIMEOUT' in line:
                events['timeouts'] += 1
            elif '重传' in line or 'retransmit' in line.lower():
                events['retransmissions'] += 1
            elif '丢包' in line or 'packet loss' in line.lower():
                events['packet_loss'] += 1
            elif 'RTO-UPDATE' in line:
                events['rto_updates'] += 1
            elif 'RECOVERY' in line:
                events['recoveries'] += 1
            elif 'PROGRESS' in line:
                events['progress_updates'] += 1
        
        print(f"\n[{scenario_name}] 事件统计:")
        print(f"  🔄 重传次数: {events['retransmissions']}")
        print(f"  ⏰ 超时次数: {events['timeouts']}")
        print(f"  📦 丢包事件: {events['packet_loss']}")
        print(f"  ⏱️  RTO更新: {events['rto_updates']}")
        print(f"  ✅ 恢复事件: {events['recoveries']}")
        print(f"  📊 进度更新: {events['progress_updates']}")
    
    if result.stderr:
        print(f"\n[{scenario_name}] 错误输出:")
        for line in result.stderr.strip().split('\n'):
            print(f"  {line}")
    
    # 清理进程
    if sim_proc:
        sim_proc.terminate()
        sim_proc.wait()
    recv_proc.terminate()
    recv_proc.wait()
    
    return result.returncode == 0, elapsed

def main():
    """主函数：对比不同丢包率下的传输行为"""
    print("🚀 RDT2.1 丢包重传行为可视化演示")
    print("="*80)
    
    # 创建测试文件
    test_file = create_test_file(100)  # 100KB文件
    
    scenarios = [
        ("正常网络", 0.0),      # 0% 丢包
        ("轻微丢包", 1.0),      # 1% 丢包  
        ("中等丢包", 3.0),      # 3% 丢包
    ]
    
    results = {}
    
    for name, loss_rate in scenarios:
        try:
            success, elapsed = run_single_transfer_with_logging(test_file, name, loss_rate)
            results[name] = {
                'success': success,
                'elapsed': elapsed,
                'loss_rate': loss_rate
            }
        except Exception as e:
            print(f"[{name}] 测试失败: {e}")
            results[name] = {
                'success': False,
                'elapsed': 0,
                'loss_rate': loss_rate,
                'error': str(e)
            }
    
    # 总结对比
    print(f"\n{'='*80}")
    print("📊 传输行为对比总结")
    print(f"{'='*80}")
    
    for name, result in results.items():
        status = "✅ 成功" if result['success'] else "❌ 失败"
        print(f"{name} ({result['loss_rate']}% 丢包): {status}, 用时: {result['elapsed']:.3f}s")
        if 'error' in result:
            print(f"  错误: {result['error']}")
    
    # 清理测试文件
    test_file.unlink(missing_ok=True)
    
    print(f"\n✨ 演示完成！")
    print("关键观察点:")
    print("  • 随着丢包率增加，重传和超时次数会显著增加")
    print("  • RTO超时时间会根据网络状况自适应调整")
    print("  • 详细的日志帮助理解每个数据包的传输状态")

if __name__ == "__main__":
    main()
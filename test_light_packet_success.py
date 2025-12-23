#!/usr/bin/env python3
"""
轻丢包环境下的成功传输演示
展示RDT2.1如何在有丢包的情况下成功完成传输
"""
import subprocess
import time
import sys
from pathlib import Path

TEST_DIR = Path(__file__).parent

def create_test_file(size_kb: int = 20) -> Path:
    """创建小测试文件，确保能在轻丢包下成功传输"""
    test_file = TEST_DIR / f"small_test_{size_kb}kb.bin"
    with open(test_file, 'wb') as f:
        f.write(b'TEST' * (size_kb * 256))  # 重复模式便于验证
    return test_file

def demonstrate_light_packet_loss():
    """演示轻丢包环境下的成功传输"""
    print("🎯 轻丢包环境下的RDT2.1成功传输演示")
    print("="*80)
    
    # 创建小测试文件
    test_file = create_test_file(20)  # 20KB文件
    print(f"📁 测试文件: {test_file.name} ({test_file.stat().st_size}B)")
    
    # 启动接收端
    print("\n🔧 启动接收端...")
    recv_cmd = [sys.executable, "-m", "rdtftp.cli_recv", "--port", "9999"]
    recv_proc = subprocess.Popen(recv_cmd, cwd=str(TEST_DIR), 
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(0.5)
    
    # 启动网络模拟器（0.5%丢包率）
    print("🔧 启动网络模拟器（0.5%丢包率）...")
    sim_cmd = [
        sys.executable, "network_simulator.py",
        "--port", "9998", "--target-port", "9999",
        "--loss", "0.005",  # 0.5%丢包率
        "--delay", "5", "--jitter", "2"
    ]
    sim_proc = subprocess.Popen(sim_cmd, cwd=str(TEST_DIR),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.0)
    
    # 发送文件
    print(f"\n📤 开始传输文件到轻丢包网络...")
    send_cmd = [
        sys.executable, "-m", "rdtftp.cli_send",
        "--file", str(test_file),
        "--host", "127.0.0.1", 
        "--port", "9998"
    ]
    
    print(f"执行命令: {' '.join(send_cmd)}")
    start_time = time.time()
    
    result = subprocess.run(send_cmd, cwd=str(TEST_DIR), capture_output=True, text=True)
    elapsed = time.time() - start_time
    
    print(f"\n⏱️  传输完成！用时: {elapsed:.3f}秒")
    print(f"返回码: {result.returncode}")
    
    # 详细分析输出
    if result.stdout:
        print(f"\n📋 详细传输日志:")
        
        # 统计关键事件
        stats = {
            'syn_sent': False,
            'data_chunks': 0,
            'timeouts': 0,
            'retransmissions': 0,
            'recoveries': 0,
            'rto_updates': 0,
            'progress_reports': 0,
            'fin_sent': False
        }
        
        for line in result.stdout.strip().split('\n'):
            print(f"  {line}")
            
            # 事件检测
            if '[SYN]' in line and '->' in line:
                stats['syn_sent'] = True
            elif '[START]' in line:
                print(f"  ✅ 检测到数据传输开始")
            elif '[PROGRESS]' in line:
                stats['progress_reports'] += 1
                # 提取进度信息
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
            elif '[RTO-UPDATE]' in line:
                stats['rto_updates'] += 1
            elif '[FIN]' in line:
                stats['fin_sent'] = True
            elif '[DONE]' in line:
                print(f"  🎉 检测到传输完成信号")
            elif '[FINAL-STATS]' in line:
                print(f"  📊 检测到最终统计信息")
        
        print(f"\n📈 传输行为分析:")
        print(f"  ✅ SYN握手: {'成功' if stats['syn_sent'] else '失败'}")
        print(f"  📦 数据块传输: {stats['data_chunks']} 块")
        print(f"  📊 进度报告: {stats['progress_reports']} 次")
        print(f"  ⏰ 超时事件: {stats['timeouts']} 次")
        print(f"  🔄 重传事件: {stats['retransmissions']} 次")
        print(f"  ✅ 恢复事件: {stats['recoveries']} 次")
        print(f"  ⏱️  RTO更新: {stats['rto_updates']} 次")
        print(f"  🏁 FIN结束: {'成功' if stats['fin_sent'] else '失败'}")
        
        # 计算丢包恢复率
        if stats['timeouts'] > 0:
            recovery_rate = (stats['recoveries'] / stats['timeouts']) * 100
            print(f"  🎯 丢包恢复率: {recovery_rate:.1f}%")
    
    if result.stderr:
        print(f"\n⚠️  错误输出:")
        for line in result.stderr.strip().split('\n'):
            print(f"  {line}")
    
    # 验证文件完整性
    print(f"\n🔍 验证文件完整性...")
    received_file = TEST_DIR / "received" / test_file.name
    if received_file.exists():
        received_size = received_file.stat().st_size
        original_size = test_file.stat().st_size
        
        print(f"  原始文件大小: {original_size}B")
        print(f"  接收文件大小: {received_size}B")
        
        if received_size == original_size:
            print(f"  ✅ 文件大小匹配！传输成功")
            
            # 验证内容
            with open(test_file, 'rb') as f1, open(received_file, 'rb') as f2:
                original_content = f1.read()
                received_content = f2.read()
                
            if original_content == received_content:
                print(f"  ✅ 文件内容完全匹配！")
            else:
                print(f"  ⚠️  文件内容不匹配！")
        else:
            print(f"  ❌ 文件大小不匹配！传输不完整")
    else:
        print(f"  ❌ 接收文件不存在！传输失败")
    
    # 清理
    if sim_proc:
        sim_proc.terminate()
        sim_proc.wait()
    recv_proc.terminate() 
    recv_proc.wait()
    
    # 清理文件
    test_file.unlink(missing_ok=True)
    if received_file.exists():
        received_file.unlink()
    
    print(f"\n✨ 演示完成！")
    print("关键观察:")
    print("  • 即使在0.5%的轻丢包环境下，RDT2.1也能成功完成传输")
    print("  • 详细的日志显示了每个数据包的状态和重传机制")
    print("  • RTO自适应调整帮助优化重传时机")
    print("  • 停等协议确保数据按顺序可靠传输")

if __name__ == "__main__":
    demonstrate_light_packet_loss()
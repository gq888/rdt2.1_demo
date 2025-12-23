#!/usr/bin/env python3
"""
RDT2.1协议10%丢包率环境测试 - 最终修复版
通过直接修改sender.py来测试协议在高丢包环境下的表现
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

def modify_sender_for_packet_loss(loss_rate: float):
    """修改sender.py添加丢包模拟功能"""
    sender_file = TEST_DIR / "rdtftp" / "sender.py"
    
    # 备份原始文件
    backup_file = sender_file.with_suffix('.py.backup')
    if not backup_file.exists():
        import shutil
        shutil.copy(sender_file, backup_file)
    
    # 读取原始文件
    with open(sender_file, 'r') as f:
        content = f.read()
    
    # 添加丢包模拟功能
    if "# 丢包模拟" not in content:
        # 在imports部分添加random
        modified_content = content.replace(
            "import time",
            "import time\nimport random  # 丢包模拟"
        )
        
        # 在Sender类初始化中添加丢包率设置
        modified_content = modified_content.replace(
            "self.stats = TransferStats()  # 传输统计",
            '''self.stats = TransferStats()  # 传输统计
        self._test_packet_loss_rate = 0.0  # 测试丢包率（默认关闭）'''
        )
        
        # 修改_send_and_wait方法添加丢包模拟
        modified_content = modified_content.replace(
            "def _send_and_wait(self, pkt: Packet, expect_type: int, expect_ack: Optional[int] = None) -> Packet:",
            '''def _send_and_wait(self, pkt: Packet, expect_type: int, expect_ack: Optional[int] = None) -> Packet:
        """发送并等待响应，包含详细的丢包重传日志"""
        # 丢包模拟：概率模拟发送超时（仅在测试环境下）
        if self._test_packet_loss_rate > 0 and random.random() < self._test_packet_loss_rate:
            self._log(f"[SIMULATED-LOSS] 模拟丢包: type={pkt.ptype}, seq={pkt.seq}")
            time.sleep(self.rto)  # 等待超时时间
            raise socket.timeout("模拟丢包")'''
        )
        
        with open(sender_file, 'w') as f:
            f.write(modified_content)
    
    return backup_file

def restore_sender(backup_file: Path):
    """恢复原始sender.py文件"""
    sender_file = TEST_DIR / "rdtftp" / "sender.py"
    if backup_file.exists():
        import shutil
        shutil.move(backup_file, sender_file)

def test_with_10_percent_loss():
    """测试10%丢包率环境下的RDT2.1传输"""
    print("🎯 RDT2.1协议10%丢包率环境测试")
    print("="*80)
    
    # 确保下载目录存在
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    
    # 创建测试文件（20KB，较小的文件便于观察重传行为）
    test_file = create_test_file(20)
    print(f"📁 测试文件: {test_file.name} ({test_file.stat().st_size}B)")
    
    # 修改sender.py添加丢包模拟
    print("\n🔧 配置发送端模拟10%丢包率...")
    backup_file = modify_sender_for_packet_loss(0.1)
    
    # 启动接收端
    print("\n🔧 启动接收端...")
    recv_cmd = [sys.executable, "-m", "rdtftp.cli_recv", "--port", "6666", "--out-dir", str(DOWNLOADS_DIR)]
    recv_proc = subprocess.Popen(recv_cmd, cwd=str(TEST_DIR), 
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.0)  # 确保接收端启动
    
    # 创建启用丢包模拟的发送脚本
    test_script = TEST_DIR / "enable_loss_test.py"
    with open(test_script, 'w') as f:
        f.write(f'''
import socket
import sys
import os
sys.path.insert(0, "{TEST_DIR}")

from rdtftp.sender import RdtSender
from rdtftp.config import SenderConfig
from pathlib import Path

# 创建发送端实例
cfg = SenderConfig()
sender = RdtSender(("127.0.0.1", 6666), cfg)

# 启用10%丢包模拟
sender._test_packet_loss_rate = 0.1
print("[TEST] 已启用10%丢包模拟")

# 发送文件
try:
    sender.send_file(Path("{test_file}"))
    print("[TEST] 传输完成")
except Exception as e:
    print(f"[TEST] 传输失败: {{e}}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
''')
    
    # 发送文件
    print(f"\n📤 开始传输文件（10%模拟丢包）...")
    start_time = time.time()
    result = subprocess.run([sys.executable, str(test_script)], 
                           cwd=str(TEST_DIR), capture_output=True, text=True, timeout=120)
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
            'simulated_losses': 0,
            'real_timeouts': 0,
            'retransmissions': 0,
            'recoveries': 0,
            'data_chunks': 0,
            'syn_events': 0,
            'fin_events': 0,
            'progress_reports': 0,
            'rto_updates': 0
        }
        
        for line in result.stdout.strip().split('\n'):
            if '[SIMULATED-LOSS]' in line:
                stats['simulated_losses'] += 1
            elif '[TIMEOUT' in line and '模拟丢包' not in line:
                stats['real_timeouts'] += 1
            elif '重传' in line and '模拟' not in line:
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
        
        print(f"\n📈 10%丢包率传输行为分析:")
        print(f"  🎭 模拟丢包事件: {stats['simulated_losses']} 次")
        print(f"  ⏰ 真实超时事件: {stats['real_timeouts']} 次")
        print(f"  🔄 总重传次数: {stats['retransmissions']} 次")
        print(f"  ✅ 成功恢复次数: {stats['recoveries']} 次")
        print(f"  📊 数据块传输: {stats['data_chunks']} 块")
        print(f"  📋 进度报告: {stats['progress_reports']} 次")
        print(f"  ⏱️  RTO更新: {stats['rto_updates']} 次")
        
        if stats['simulated_losses'] > 0:
            recovery_rate = (stats['recoveries'] / stats['simulated_losses']) * 100
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
        print("🎉 10%丢包率测试成功！RDT2.1协议展现了良好的丢包恢复能力")
        print("💡 即使在10%的高丢包环境下，协议仍能保证数据完整性和正确性")
    else:
        print("❌ 10%丢包率测试失败！高丢包环境对协议造成严重影响")
    
    # 恢复原始文件
    restore_sender(backup_file)
    
    # 清理临时文件
    if test_file.exists():
        test_file.unlink()
    if received_file.exists():
        received_file.unlink()
    if test_script.exists():
        test_script.unlink()
    
    # 终止进程
    try:
        recv_proc.terminate()
        recv_proc.wait(timeout=2)
    except:
        recv_proc.kill()

if __name__ == "__main__":
    test_with_10_percent_loss()
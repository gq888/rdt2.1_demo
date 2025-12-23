#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDT2.1 详细握手分析测试
模拟真实的发送场景，包含网络模拟器
"""

import subprocess
import time
import sys
import socket
from pathlib import Path
import threading

# 测试目录
TEST_DIR = Path(__file__).parent
DOWNLOADS_DIR = TEST_DIR / "downloads_debug"

def capture_receiver_output(proc):
    """捕获接收端输出"""
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        print(f"[RECV-OUT] {line.strip()}")

def test_with_network_simulator():
    """使用网络模拟器测试握手"""
    print("🔍 测试带网络模拟器的RDT2.1握手...")
    
    # 确保下载目录存在
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    
    # 创建测试文件
    test_file = TEST_DIR / "test_small.txt"
    test_file.write_text("Hello RDT2.1!" * 100)  # 1.3KB
    
    # 启动接收端
    print("🚀 启动接收端...")
    recv_cmd = [sys.executable, "-m", "rdtftp.cli_recv", "--port", "6666", "--out-dir", str(DOWNLOADS_DIR)]
    recv_proc = subprocess.Popen(recv_cmd, cwd=str(TEST_DIR), 
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # 启动线程捕获接收端输出
    recv_thread = threading.Thread(target=capture_receiver_output, args=(recv_proc,))
    recv_thread.daemon = True
    recv_thread.start()
    
    time.sleep(1.0)
    
    # 检查接收端是否启动成功
    if recv_proc.poll() is not None:
        stdout, stderr = recv_proc.communicate()
        print(f"❌ 接收端启动失败")
        print(f"stdout: {stdout}")
        print(f"stderr: {stderr}")
        return False
    
    # 启动网络模拟器（0%丢包）
    print("🚀 启动网络模拟器（0%丢包）...")
    sim_cmd = [
        sys.executable, "network_simulator.py",
        "--port", "6665", "--target-port", "6666",
        "--loss", "0.0",  # 0%丢包率
        "--delay", "1", "--jitter", "0"
    ]
    sim_proc = subprocess.Popen(sim_cmd, cwd=str(TEST_DIR),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    time.sleep(2.0)  # 等待网络模拟器启动
    
    # 检查网络模拟器是否启动成功
    if sim_proc.poll() is not None:
        stdout, stderr = sim_proc.communicate()
        print(f"❌ 网络模拟器启动失败")
        print(f"stdout: {stdout}")
        print(f"stderr: {stderr}")
        recv_proc.terminate()
        return False
    
    try:
        # 测试端口连通性
        print("🔍 测试端口连通性...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        
        # 发送一个简单的探测包
        test_data = b"PROBE"
        sock.sendto(test_data, ("127.0.0.1", 6665))
        print(f"📤 发送探测包到 127.0.0.1:6665")
        
        try:
            resp, addr = sock.recvfrom(1024)
            print(f"📥 收到响应: {resp} from {addr}")
        except socket.timeout:
            print("⚠️  探测包超时（可能正常，因为网络模拟器只转发特定格式的包）")
        
        sock.close()
        
        # 尝试发送文件
        print(f"\n📤 尝试发送文件: {test_file.name}")
        send_cmd = [
            sys.executable, "-m", "rdtftp.cli_send",
            "--file", str(test_file),
            "--host", "127.0.0.1", 
            "--port", "6665",  # 发送到网络模拟器
            "--rto", "0.5",    # 增加RTO时间
            "--max-retry", "10"  # 减少重试次数避免长时间等待
        ]
        
        print(f"执行命令: {' '.join(send_cmd)}")
        
        start_time = time.time()
        result = subprocess.run(send_cmd, cwd=str(TEST_DIR), 
                               capture_output=True, text=True, timeout=30)
        elapsed = time.time() - start_time
        
        print(f"\n📊 发送结果:")
        print(f"返回码: {result.returncode}")
        print(f"用时: {elapsed:.2f}s")
        print(f"stdout:\n{result.stdout}")
        print(f"stderr:\n{result.stderr}")
        
        # 检查文件是否传输成功
        downloaded_file = DOWNLOADS_DIR / test_file.name
        if downloaded_file.exists():
            original_content = test_file.read_bytes()
            downloaded_content = downloaded_file.read_bytes()
            if original_content == downloaded_content:
                print("✅ 文件传输成功且内容一致")
                return True
            else:
                print("❌ 文件传输成功但内容不一致")
                return False
        else:
            print("❌ 文件未传输成功")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ 传输超时")
        return False
    except Exception as e:
        print(f"❌ 测试错误: {e}")
        return False
    finally:
        # 清理进程
        sim_proc.terminate()
        recv_proc.terminate()
        
        try:
            sim_proc.wait(timeout=2.0)
            recv_proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            sim_proc.kill()
            recv_proc.kill()
            sim_proc.wait()
            recv_proc.wait()
        
        # 清理测试文件
        if test_file.exists():
            test_file.unlink()

def main():
    """主测试函数"""
    print("="*60)
    print("🧪 RDT2.1 详细握手分析测试")
    print("="*60)
    
    success = test_with_network_simulator()
    
    print("\n" + "="*60)
    print("📊 测试结果:")
    print(f"   带网络模拟器的传输: {'✅ 成功' if success else '❌ 失败'}")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
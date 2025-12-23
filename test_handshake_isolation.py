#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDT2.1 SYN握手隔离测试
用于分析为什么即使在0%丢包率下也无法完成握手
"""

import socket
import subprocess
import time
import sys
from pathlib import Path

# 测试目录
TEST_DIR = Path(__file__).parent
DOWNLOADS_DIR = TEST_DIR / "downloads_handshake"

def test_basic_udp():
    """测试基础UDP通信是否正常"""
    print("🔍 测试基础UDP通信...")
    
    # 创建接收端
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock.bind(("127.0.0.1", 0))  # 让系统分配端口
    recv_port = recv_sock.getsockname()[1]
    recv_sock.settimeout(5.0)
    
    # 创建发送端
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send_sock.settimeout(1.0)
    
    try:
        # 发送测试数据
        test_data = b"Hello UDP!"
        send_sock.sendto(test_data, ("127.0.0.1", recv_port))
        print(f"📤 发送测试数据: {test_data} -> 127.0.0.1:{recv_port}")
        
        # 接收数据
        data, addr = recv_sock.recvfrom(1024)
        print(f"📥 接收测试数据: {data} from {addr}")
        
        if data == test_data:
            print("✅ 基础UDP通信正常")
            return True
        else:
            print("❌ 数据不匹配")
            return False
            
    except socket.timeout as e:
        print(f"❌ UDP通信超时: {e}")
        return False
    except Exception as e:
        print(f"❌ UDP通信错误: {e}")
        return False
    finally:
        recv_sock.close()
        send_sock.close()

def test_rdt_handshake():
    """测试RDT2.1握手过程"""
    print("\n🔍 测试RDT2.1握手过程...")
    
    # 确保下载目录存在
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    
    # 启动接收端
    print("🚀 启动接收端...")
    recv_cmd = [sys.executable, "-m", "rdtftp.cli_recv", "--port", "7777", "--out-dir", str(DOWNLOADS_DIR)]
    recv_proc = subprocess.Popen(recv_cmd, cwd=str(TEST_DIR), 
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    time.sleep(1.0)  # 等待接收端启动
    
    # 检查接收端是否启动成功
    if recv_proc.poll() is not None:
        stdout, stderr = recv_proc.communicate()
        print(f"❌ 接收端启动失败")
        print(f"stdout: {stdout}")
        print(f"stderr: {stderr}")
        return False
    
    try:
        # 创建简单的SYN包
        from rdtftp.protocol import Packet, PktType, FLAG_META_JSON
        import json
        
        meta = {
            "filename": "test.txt",
            "filesize": 100,
            "chunk_size": 1024,
            "sha256": "abc123"
        }
        
        syn = Packet(
            ptype=PktType.SYN,
            flags=FLAG_META_JSON,
            file_id=12345,
            payload=json.dumps(meta).encode("utf-8")
        )
        
        # 直接发送SYN包到接收端
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        
        syn_data = syn.encode()
        print(f"📤 发送SYN包 ({len(syn_data)} bytes) -> 127.0.0.1:7777")
        sock.sendto(syn_data, ("127.0.0.1", 7777))
        
        # 等待SYN-ACK响应
        try:
            resp, addr = sock.recvfrom(65535)
            print(f"📥 收到响应 ({len(resp)} bytes) from {addr}")
            
            # 尝试解码响应
            resp_pkt, ok = Packet.decode(resp)
            if ok and resp_pkt.ptype == PktType.SYN_ACK:
                print("✅ 收到SYN-ACK，握手成功!")
                
                # 解码响应内容
                if resp_pkt.payload:
                    try:
                        info = json.loads(resp_pkt.payload.decode("utf-8"))
                        print(f"   响应信息: {info}")
                    except:
                        pass
                
                return True
            else:
                print(f"❌ 收到非SYN-ACK响应: type={resp_pkt.ptype if ok else 'decode_failed'}")
                return False
                
        except socket.timeout:
            print("❌ SYN-ACK响应超时")
            return False
            
    except Exception as e:
        print(f"❌ 握手测试错误: {e}")
        return False
    finally:
        # 清理
        recv_proc.terminate()
        try:
            recv_proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            recv_proc.kill()
            recv_proc.wait()

def main():
    """主测试函数"""
    print("="*60)
    print("🧪 RDT2.1握手隔离测试")
    print("="*60)
    
    # 测试1: 基础UDP通信
    udp_ok = test_basic_udp()
    
    # 测试2: RDT2.1握手
    handshake_ok = test_rdt_handshake()
    
    print("\n" + "="*60)
    print("📊 测试结果总结:")
    print(f"   基础UDP通信: {'✅ 通过' if udp_ok else '❌ 失败'}")
    print(f"   RDT2.1握手: {'✅ 成功' if handshake_ok else '❌ 失败'}")
    
    if udp_ok and not handshake_ok:
        print("\n🔍 分析: UDP通信正常但RDT2.1握手失败")
        print("   可能原因:")
        print("   1. 接收端未正确绑定端口")
        print("   2. 接收端未正确处理SYN包")
        print("   3. 接收端发送SYN-ACK失败")
        print("   4. SYN包格式不符合协议要求")
    elif not udp_ok:
        print("\n🔍 分析: 基础UDP通信失败")
        print("   可能原因:")
        print("   1. 系统防火墙阻止UDP通信")
        print("   2. 端口被占用")
        print("   3. 网络配置问题")
    
    return udp_ok and handshake_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
# RDT2.1(停等式)可靠文件传输 - Python 实现

## 1. 环境
- Python 3.9+（建议 3.10/3.11）
- 纯标准库，无第三方依赖

## 2. 目录结构
```
rdt_course_project/
  rdtftp/
    protocol.py   # 报文格式、CRC32校验、编解码
    sender.py     # 发送端：停等+超时重传+自适应RTO
    receiver.py   # 接收端：按块写入+断点续传+校验
    cli_send.py   # 命令行发送端
    cli_recv.py   # 命令行接收端
    utils.py
  tests/
    tc_netem_example.sh
    quick_local_demo.py
```

## 3. 使用方法

### 3.1 启动接收端（服务器）
```bash
python -m rdtftp.cli_recv --port 9000 --out-dir ./downloads
```

### 3.2 启动发送端（客户端）
```bash
python -m rdtftp.cli_send --file ./test.bin --host 127.0.0.1 --port 9000
```

### 3.3 断点续传
默认开启续传。若想强制从0开始：
```bash
python -m rdtftp.cli_send --file ./test.bin --host 127.0.0.1 --port 9000 --no-resume
```

## 4. 测试脚本

### 4.1 本机快速演示
```bash
python tests/quick_local_demo.py
```

### 4.2 Linux tc/netem 注入丢包/延迟/乱序
见 `tests/tc_netem_example.sh`（需要 root 权限）。

### 4.3 网络模拟器测试脚本

#### 4.3.1 10% 丢包率测试
```bash
python test_10_percent_loss_demo.py
```
演示 RDT2.1 协议在 10% 丢包率环境下的表现，包含详细的重传日志和传输统计。

#### 4.3.2 数据包乱序测试
```bash
python test_packet_reordering_simple.py
```
测试 RDT2.1 协议处理数据包乱序的能力，验证接收文件的哈希一致性。

#### 4.3.3 断点续传测试
```bash
python test_breakpoint_resume_simple.py
```
演示断点续传功能：模拟传输中断后从断点继续传输，验证文件完整性。

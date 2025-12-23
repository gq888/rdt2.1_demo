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

## 5. 提交建议
- 报告 PDF：按“学号1_学号2_作业2_标题.pdf”命名
- 代码 zip：同命名规则
- 报告中插入 Wireshark 截图：可用 `Magic=0xCAFE` 字段快速定位本协议报文

#!/usr/bin/env bash
# 需要root权限：sudo bash tests/tc_netem_example.sh eth0
IFACE=${1:-eth0}

echo "[1] 清除旧规则"
sudo tc qdisc del dev "$IFACE" root 2>/dev/null || true

echo "[2] 注入：延迟200ms，丢包5%，乱序10%"
sudo tc qdisc add dev "$IFACE" root netem delay 200ms loss 5% reorder 10%

echo "[3] 查看规则"
sudo tc qdisc show dev "$IFACE"

echo "运行测试后，可用以下命令恢复："
echo "  sudo tc qdisc del dev $IFACE root"

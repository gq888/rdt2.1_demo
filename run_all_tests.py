#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDT2.1 主测试运行器
整合所有测试用例，提供统一的测试入口
"""

import sys
import time
import subprocess
from pathlib import Path

def run_test_script(script_name: str, description: str) -> tuple:
    """运行测试脚本并返回结果"""
    print(f"\n{'='*70}")
    print(f"🧪 运行测试: {description}")
    print(f"脚本: {script_name}")
    print('='*70)
    
    start_time = time.time()
    
    try:
        # 运行测试脚本
        result = subprocess.run(
            [sys.executable, script_name],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        
        elapsed = time.time() - start_time
        
        # 输出测试结果
        if result.stdout:
            print(result.stdout)
        
        if result.stderr:
            print("错误输出:")
            print(result.stderr)
        
        success = result.returncode == 0
        
        print(f"\n⏱️  运行时间: {elapsed:.2f}秒")
        print(f"📊 返回码: {result.returncode}")
        
        return success, elapsed
        
    except subprocess.TimeoutExpired:
        print(f"❌ 测试超时 (超过5分钟)")
        return False, 300
    except Exception as e:
        print(f"❌ 运行测试时出错: {e}")
        return False, 0

def main():
    """主函数 - 运行所有测试套件"""
    
    print("🚀 RDT2.1 可靠文件传输协议 - 完整测试套件")
    print("=" * 80)
    print("本测试套件包含以下测试场景:")
    print("  1. 正常网络环境测试")
    print("  2. 网络模拟测试（丢包、延迟、断网等）")
    print("  3. 断点续传测试")
    print("  4. 性能基准测试")
    print("=" * 80)
    
    # 测试套件配置
    test_suites = [
        {
            "script": "test_comprehensive.py",
            "description": "综合功能测试 - 正常网络环境下的基本功能验证",
            "category": "基础功能"
        },
        {
            "script": "test_network_simulation.py", 
            "description": "网络模拟测试 - 恶劣网络环境下的协议鲁棒性测试",
            "category": "网络模拟"
        },
        {
            "script": "tests/quick_local_demo.py",
            "description": "快速演示测试 - 项目自带的快速验证脚本",
            "category": "快速验证"
        }
    ]
    
    # 运行测试
    results = []
    total_start_time = time.time()
    
    for i, test_suite in enumerate(test_suites, 1):
        print(f"\n[{i}/{len(test_suites)}] 准备运行 {test_suite['category']} 测试...")
        
        # 检查测试脚本是否存在
        script_path = Path(__file__).parent / test_suite["script"]
        if not script_path.exists():
            print(f"⚠️  警告: 测试脚本 {test_suite['script']} 不存在，跳过此测试")
            results.append({
                "name": test_suite["description"],
                "success": False,
                "elapsed": 0,
                "reason": "脚本不存在"
            })
            continue
        
        success, elapsed = run_test_script(test_suite["script"], test_suite["description"])
        
        results.append({
            "name": test_suite["description"],
            "success": success,
            "elapsed": elapsed,
            "category": test_suite["category"]
        })
    
    # 统计结果
    total_elapsed = time.time() - total_start_time
    passed_tests = sum(1 for r in results if r["success"])
    total_tests = len(results)
    
    # 打印测试总结
    print("\n" + "=" * 80)
    print("📊 RDT2.1 测试总结报告")
    print("=" * 80)
    
    print(f"总测试时间: {total_elapsed:.2f}秒")
    print(f"测试通过率: {passed_tests}/{total_tests} ({passed_tests/total_tests*100:.1f}%)")
    
    print("\n详细结果:")
    print("-" * 80)
    
    for i, result in enumerate(results, 1):
        status = "✅ 通过" if result["success"] else "❌ 失败"
        print(f"{i}. [{status}] {result['name']}")
        print(f"   类别: {result['category']}")
        print(f"   用时: {result['elapsed']:.2f}秒")
        if not result["success"] and "reason" in result:
            print(f"   原因: {result['reason']}")
        print()
    
    # 建议和改进
    print("建议和改进:")
    print("-" * 80)
    
    if passed_tests == total_tests:
        print("🎉 所有测试通过！RDT2.1协议实现非常稳定可靠！")
        print("建议:")
        print("  - 可以进一步优化性能，提高传输速度")
        print("  - 考虑增加更多网络模拟场景")
        print("  - 可以添加并发传输测试")
    else:
        print("⚠️  部分测试失败，建议:")
        print("  - 检查网络模拟器的实现是否正确")
        print("  - 验证超时重传机制的配置")
        print("  - 确保断点续传功能的稳定性")
        print("  - 考虑增加错误处理和恢复机制")
    
    print("\n" + "=" * 80)
    
    if passed_tests == total_tests:
        print("🎊 恭喜！RDT2.1协议通过了完整的测试验证！")
        return 0
    else:
        print("❗ 测试中发现问题，建议修复后重新测试")
        return 1

if __name__ == "__main__":
    sys.exit(main())
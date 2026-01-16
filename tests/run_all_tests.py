#!/usr/bin/env python3
"""
测试脚本执行器
按照依赖关系和执行顺序运行所有测试脚本
"""

import subprocess
import sys
import time
import os
from pathlib import Path

# 设置项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
TESTS_DIR = PROJECT_ROOT / "tests"

def run_test_script(test_path: Path, description: str, timeout: int = 120):
    """运行单个测试脚本"""
    print(f"\n{'='*80}")
    print(f"🧪 运行测试: {description}")
    print(f"📁 脚本路径: {test_path}")
    print(f"⏱️  超时设置: {timeout}秒")
    print(f"{'='*80}")
    
    if not test_path.exists():
        print(f"❌ 测试脚本不存在: {test_path}")
        return False
    
    try:
        start_time = time.time()
        result = subprocess.run(
            [sys.executable, str(test_path)],
            cwd=str(test_path.parent),
            capture_output=True,
            text=True,
            timeout=timeout
        )
        elapsed = time.time() - start_time
        
        print(f"\n📊 测试结果:")
        print(f"  ⏱️  运行时间: {elapsed:.3f}秒")
        print(f"  🔙 返回码: {result.returncode}")
        
        if result.returncode == 0:
            print(f"  ✅ 测试通过！")
            return True
        else:
            print(f"  ❌ 测试失败！")
            if result.stderr:
                print(f"  📋 错误输出:")
                print(f"  {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"  ⚠️  测试超时 ({timeout}秒)")
        return False
    except Exception as e:
        print(f"  💥 运行异常: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 RDT2.1测试套件执行器")
    print("="*80)
    
    # 定义测试用例
    test_cases = [
        {
            "path": TESTS_DIR / "performance" / "quick_local_demo.py",
            "description": "基础性能测试 - 本机快速验证",
            "timeout": 30
        },
        {
            "path": TESTS_DIR / "network_simulation" / "test_10_percent_loss_demo.py",
            "description": "网络模拟测试 - 10%丢包率环境",
            "timeout": 120
        },
        {
            "path": TESTS_DIR / "packet_reordering" / "test_packet_reordering_simple.py",
            "description": "数据包乱序测试 - 网络抖动环境",
            "timeout": 120
        },
        {
            "path": TESTS_DIR / "breakpoint_resume" / "test_breakpoint_resume_simple.py",
            "description": "断点续传测试 - 传输中断恢复",
            "timeout": 180
        }
    ]
    
    # 执行测试
    results = []
    total_tests = len(test_cases)
    passed_tests = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📋 测试进度: {i}/{total_tests}")
        success = run_test_script(
            test_case["path"],
            test_case["description"],
            test_case["timeout"]
        )
        results.append({
            "description": test_case["description"],
            "success": success
        })
        if success:
            passed_tests += 1
        
        # 测试间隔
        if i < total_tests:
            print("\n⏳ 等待5秒后进行下一个测试...")
            time.sleep(5)
    
    # 生成测试报告
    print(f"\n{'='*80}")
    print("📊 测试总结报告")
    print(f"{'='*80}")
    print(f"  📋 总测试数: {total_tests}")
    print(f"  ✅ 通过测试: {passed_tests}")
    print(f"  ❌ 失败测试: {total_tests - passed_tests}")
    print(f"  📈 通过率: {(passed_tests/total_tests*100):.1f}%")
    
    print(f"\n📋 详细结果:")
    for i, result in enumerate(results, 1):
        status = "✅ 通过" if result["success"] else "❌ 失败"
        print(f"  {i:2d}. {status} - {result['description']}")
    
    # 整体结果
    print(f"\n{'='*80}")
    if passed_tests == total_tests:
        print("🎉 所有测试通过！RDT2.1协议功能正常")
        return 0
    else:
        print("⚠️  部分测试失败，请检查具体错误信息")
        return 1

if __name__ == "__main__":
    sys.exit(main())
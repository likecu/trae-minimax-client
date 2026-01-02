#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trae CN 启动器 - 带开发者工具和调试功能

使用方法：
    python3 launch_traе.py

功能：
1. 带 --inspect 启动（可连接调试器）
2. 带 --remote-debugging-port 启动（HTTP 调试端口）
3. 自动打开开发者工具

作者: AI Assistant
日期: 2025-01-02
"""

import os
import sys
import subprocess
import time
import signal
from datetime import datetime

# 配置
TRAE_APP_PATH = "/Volumes/600g/Applications/Trae CN.app"
DEBUG_PORT = 9222
REMOTE_DEBUG_PORT = 9229


def kill_existing_traе():
    """关闭已运行的 Trae CN"""
    print("🔍 检查已运行的 Trae CN...")

    try:
        # 查找 Trae CN 进程
        result = subprocess.run(
            ['pgrep', '-f', 'Trae CN'],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                if pid:
                    print(f"   关闭进程 {pid}...")
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                    except:
                        pass
            time.sleep(1)
            print("✅ 已关闭现有进程")
        else:
            print("   没有运行的 Trae CN 进程")

    except Exception as e:
        print(f"   检查进程时出错: {e}")


def launch_with_inspect():
    """带 Inspector 端口启动"""
    print("\n" + "=" * 60)
    print("🚀 启动 Trae CN (带调试端口)")
    print("=" * 60)

    cmd = [
        'open',
        '-n',
        TRAE_APP_PATH,
        '--args',
        f'--inspect={DEBUG_PORT}',
        f'--remote-debugging-port={REMOTE_DEBUG_PORT}',
        '--enable-logging',
        '--v=1'
    ]

    print(f"执行命令: {' '.join(cmd)}")

    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        print(f"\n✅ Trae CN 已启动")
        print(f"   调试端口: {DEBUG_PORT}")
        print(f"   远程调试端口: {REMOTE_DEBUG_PORT}")
        print(f"\n💡 提示:")
        print(f"   - 在 Chrome 中访问: chrome://inspect")
        print(f"   - 点击 'Configure' 添加: localhost:{DEBUG_PORT}")
        print(f"   - 按 Cmd+Option+I 打开开发者工具")

        # 等待启动
        time.sleep(3)
        return True

    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return False


def launch_with_devtools_open():
    """启动并自动打开开发者工具"""
    print("\n" + "=" * 60)
    print("🚀 启动 Trae CN (自动打开开发者工具)")
    print("=" * 60)

    cmd = [
        'open',
        '-n',
        TRAE_APP_PATH,
        '--args',
        '--inspect',
        '--dev',
        '--open-devtools'
    ]

    print(f"执行命令: {' '.join(cmd)}")

    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        print(f"\n✅ Trae CN 已启动")
        print(f"   开发者工具应该会自动打开")
        print(f"   如果没有打开，按 Cmd+Option+I")

        time.sleep(3)
        return True

    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return False


def launch_simple():
    """简单启动"""
    print("\n" + "=" * 60)
    print("🚀 启动 Trae CN")
    print("=" * 60)

    cmd = ['open', '-n', TRAE_APP_PATH]

    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("✅ Trae CN 已启动")
        print("💡 按 Cmd+Option+I 打开开发者工具")
        time.sleep(3)
        return True

    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return False


def create_traе_script():
    """创建可执行的 Trae CN 启动脚本"""
    script_content = '''#!/bin/bash
# Trae CN 启动脚本
# 用法: ./trae.sh [mode]
# mode: inspect, devtools, simple

APP_PATH="/Volumes/600g/Applications/Trae CN.app"

case "${1:-simple}" in
    inspect)
        echo "启动 Trae CN (调试模式)..."
        open -n "$APP_PATH" --args --inspect=9222
        ;;
    devtools)
        echo "启动 Trae CN (开发者模式)..."
        open -n "$APP_PATH" --args --inspect=9222 --dev
        ;;
    simple|*)
        echo "启动 Trae CN..."
        open -n "$APP_PATH"
        ;;
esac

echo "已启动！按 Cmd+Option+I 打开开发者工具"
'''

    script_path = os.path.expanduser("~/trae.sh")

    try:
        with open(script_path, 'w') as f:
            f.write(script_content)

        os.chmod(script_path, 0o755)
        print(f"\n✅ 创建启动脚本: {script_path}")
        print(f"   使用方法:")
        print(f"   ./trae.sh         # 简单启动")
        print(f"   ./trae.sh inspect # 调试模式")
        print(f"   ./trae.sh devtools # 开发者模式")

    except Exception as e:
        print(f"创建脚本失败: {e}")


def check_node_debugger():
    """检查是否有 Node.js 调试器可用"""
    print("\n📦 检查调试工具...")

    try:
        # 检查 Node.js
        result = subprocess.run(['which', 'node'], capture_output=True, text=True)
        if result.returncode == 0:
            print("   ✅ Node.js 已安装")
            print(f"   版本: {subprocess.run(['node', '--version'], capture_output=True, text=True).stdout.strip()}")

            # 安装 ndb（Node.js 调试器）
            print("\n💡 建议安装 ndb 以获得更好的调试体验:")
            print("   npm install -g ndb")

    except Exception as e:
        print(f"   ❌ Node.js 未安装")


def main():
    """主函数"""
    print("=" * 60)
    print("Trae CN 启动器")
    print("=" * 60)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 选项
    print("\n请选择启动模式:")
    print("  1. 简单启动 (按 Cmd+Option+I 打开开发者工具)")
    print("  2. 调试模式 (--inspect=9222)")
    print("  3. 开发者模式 (自动打开开发者工具)")
    print("  4. 创建启动脚本 (以后使用)")
    print("  5. 检查调试工具")

    choice = input("\n请选择 [1-5]: ").strip()

    if choice == '1':
        kill_existing_traе()
        launch_simple()
    elif choice == '2':
        kill_existing_traе()
        launch_with_inspect()
    elif choice == '3':
        kill_existing_traе()
        launch_with_devtools_open()
    elif choice == '4':
        create_traе_script()
    elif choice == '5':
        check_node_debugger()
    else:
        print("无效选择")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

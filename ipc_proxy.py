#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trae CN IPC 通信代理和拦截工具

通过监听 Trae CN 的 Unix Domain Socket 来拦截和分析 IPC 通信

工作原理：
1. 作为代理服务器监听原始 socket
2. 转发所有消息到 Trae CN
3. 记录所有通信内容
4. 实时显示协议格式

使用方法：
```python
from ipc_proxy import TraeIPCProxy

proxy = TraeIPCProxy()
proxy.start()

# 拦截的通信会显示在这里
# ...
proxy.stop()
```

作者: AI Assistant
日期: 2025-01-02
"""

import os
import sys
import json
import time
import socket
import struct
import threading
import logging
import subprocess
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import argparse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class IPCMessage:
    """IPC 消息"""
    direction: str  # "incoming" or "outgoing"
    timestamp: float = field(default_factory=time.time)
    raw_data: bytes = b''
    parsed_data: dict = field(default_factory=dict)
    size: int = 0


class TraeIPCProxy:
    """
    Trae CN IPC 通信代理

    功能：
    - 监听 Trae CN 的 socket 通信
    - 解析消息格式
    - 实时显示协议细节
    - 记录所有通信日志
    """

    def __init__(
        self,
        socket_path: str = None,
        listen_port: int = 12581,
        output_file: str = None
    ):
        """
        初始化代理

        Args:
            socket_path: Trae CN socket 路径
            listen_port: 代理监听端口
            output_file: 输出日志文件
        """
        if socket_path is None:
            socket_path = os.path.expanduser(
                "~/Library/Application Support/Trae CN/1.10-main.sock"
            )

        self.socket_path = socket_path
        self.listen_port = listen_port
        self.output_file = output_file

        self.running = False
        self.messages: List[IPCMessage] = []
        self.message_callback: Optional[Callable] = None

        # 代理 socket
        self.server_socket: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None
        self.trae_socket: Optional[socket.socket] = None

        # 日志文件
        self.log_file = None

    def _init_logging(self):
        """初始化日志文件"""
        if self.output_file:
            self.log_file = open(self.output_file, 'w', encoding='utf-8')

    def _log_message(self, message: IPCMessage):
        """记录消息到日志"""
        timestamp = datetime.fromtimestamp(message.timestamp).strftime('%H:%M:%S.%f')

        log_entry = {
            'timestamp': timestamp,
            'direction': message.direction,
            'size': message.size,
            'data': message.parsed_data
        }

        # 打印到控制台
        if message.direction == 'incoming':
            logger.info(f"📤 Trae CN → 客户端 ({message.size} bytes)")
        else:
            logger.info(f"📥 客户端 → Trae CN ({message.size} bytes)")

        # 打印解析后的数据
        if message.parsed_data:
            try:
                formatted = json.dumps(message.parsed_data, indent=2, ensure_ascii=False)
                for line in formatted.split('\n')[:10]:  # 限制输出行数
                    logger.info(f"   {line}")
            except:
                logger.info(f"   {message.parsed_data}")

        # 写入文件
        if self.log_file:
            self.log_file.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
            self.log_file.flush()

        # 存储消息
        self.messages.append(message)

        # 调用回调
        if self.message_callback:
            self.message_callback(message)

    def _parse_message(self, data: bytes) -> dict:
        """
        尝试解析消息

        尝试多种格式：
        1. VS Code IPC 格式（4字节长度前缀 + JSON）
        2. 标准 JSON 行格式
        3. 原始文本

        Args:
            data: 原始数据

        Returns:
            解析后的数据字典
        """
        result = {
            'raw_preview': data[:100].decode('utf-8', errors='replace'),
            'length': len(data)
        }

        # 尝试 VS Code IPC 格式（4字节大端序长度前缀）
        if len(data) >= 4:
            try:
                length = struct.unpack('>I', data[:4])[0]
                content = data[4:]
                if len(content) == length:
                    try:
                        json_data = json.loads(content.decode('utf-8'))
                        result['format'] = 'vscode_ipc'
                        result['header_length'] = 4
                        result['body_length'] = length
                        result['json'] = json_data
                        return result
                    except json.JSONDecodeError:
                        pass
            except struct.error:
                pass

        # 尝试标准 JSON 行格式
        try:
            text = data.decode('utf-8').strip()
            if text.startswith('{') and text.endswith('}'):
                json_data = json.loads(text)
                result['format'] = 'json_line'
                result['json'] = json_data
                return result
        except:
            pass

        # 尝试 JSON 数组
        try:
            text = data.decode('utf-8').strip()
            if text.startswith('[') and text.endswith(']'):
                json_data = json.loads(text)
                result['format'] = 'json_array'
                result['json'] = json_data
                return result
        except:
            pass

        result['format'] = 'unknown'
        return result

    def start(self, timeout: float = 10.0) -> bool:
        """
        启动代理

        连接到 Trae CN socket 并开始监听通信

        Args:
            timeout: 连接超时时间

        Returns:
            是否成功启动
        """
        # 检查 socket 是否存在
        if not os.path.exists(self.socket_path):
            logger.error(f"Socket 不存在: {self.socket_path}")
            return False

        logger.info(f"🔌 连接到 Trae CN socket: {self.socket_path}")

        try:
            # 连接到 Trae CN socket
            self.trae_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.trae_socket.settimeout(timeout)
            self.trae_socket.connect(self.socket_path)

            logger.info("✅ 成功连接到 Trae CN")

            self.running = True
            self._init_logging()

            # 启动监听线程
            listen_thread = threading.Thread(
                target=self._listen_loop,
                daemon=True
            )
            listen_thread.start()

            logger.info("🎧 开始监听 IPC 通信...")
            logger.info("   请在 Trae CN 中执行一些操作来触发通信")
            logger.info("   按 Ctrl+C 停止监听")

            # 保持主线程运行
            try:
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("\n⏹️  收到停止信号")
                self.stop()

            return True

        except Exception as e:
            logger.error(f"启动失败: {e}")
            return False

    def _listen_loop(self):
        """监听循环"""
        buffer = b''

        while self.running and self.trae_socket:
            try:
                # 接收数据
                self.trae_socket.settimeout(1.0)
                chunk = self.trae_socket.recv(4096)

                if not chunk:
                    logger.warning("连接已关闭")
                    break

                # 记录原始数据
                message = IPCMessage(
                    direction='incoming',
                    raw_data=chunk,
                    size=len(chunk)
                )

                # 尝试解析
                message.parsed_data = self._parse_message(chunk)

                # 记录消息
                self._log_message(message)

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"监听错误: {e}")
                break

    def send_message(self, data: dict):
        """
        发送消息到 Trae CN

        Args:
            data: 消息数据
        """
        if not self.trae_socket:
            logger.error("未连接")
            return

        try:
            # 序列化消息
            content = json.dumps(data, ensure_ascii=False)
            content_bytes = content.encode('utf-8')

            # 尝试添加长度前缀
            header = struct.pack('>I', len(content_bytes))
            message_bytes = header + content_bytes

            # 发送
            self.trae_socket.sendall(message_bytes)

            # 记录发送的消息
            message = IPCMessage(
                direction='outgoing',
                raw_data=message_bytes,
                size=len(message_bytes),
                parsed_data=self._parse_message(message_bytes)
            )
            self._log_message(message)

        except Exception as e:
            logger.error(f"发送失败: {e}")

    def stop(self):
        """停止代理"""
        self.running = False

        # 关闭 socket
        if self.trae_socket:
            try:
                self.trae_socket.close()
            except:
                pass

        # 关闭日志文件
        if self.log_file:
            self.log_file.close()

        logger.info("🛑 代理已停止")
        self._print_summary()

    def _print_summary(self):
        """打印通信汇总"""
        if not self.messages:
            logger.info("没有捕获到任何消息")
            return

        logger.info("\n" + "=" * 60)
        logger.info("通信汇总")
        logger.info("=" * 60)

        # 按格式分组
        formats = {}
        for msg in self.messages:
            fmt = msg.parsed_data.get('format', 'unknown')
            if fmt not in formats:
                formats[fmt] = 0
            formats[fmt] += 1

        logger.info(f"总消息数: {len(self.messages)}")
        for fmt, count in formats.items():
            logger.info(f"  {fmt}: {count} 条")

        # 尝试提取协议模板
        logger.info("\n检测到的协议格式:")
        for msg in self.messages:
            if msg.parsed_data.get('format') == 'vscode_ipc':
                json_data = msg.parsed_data.get('json', {})
                if json_data:
                    logger.info(f"  消息类型: {json_data.get('type', 'N/A')}")
                    logger.info(f"  方法: {json_data.get('method', 'N/A')}")
                    logger.info(f"  参数: {list(json_data.get('params', {}).keys())}")
                    break

    def get_messages(self) -> List[IPCMessage]:
        """获取所有消息"""
        return self.messages

    def clear_messages(self):
        """清空消息历史"""
        self.messages.clear()


class TraeIPCAnalyzer:
    """
    Trae CN IPC 通信分析器

    通过发送测试消息来探测协议格式
    """

    def __init__(self, socket_path: str = None):
        """初始化"""
        if socket_path is None:
            socket_path = os.path.expanduser(
                "~/Library/Application Support/Trae CN/1.10-main.sock"
            )
        self.socket_path = socket_path

    def test_protocol(self) -> dict:
        """
        测试协议格式

        尝试多种协议格式，看哪种能收到响应

        Returns:
            测试结果
        """
        results = {
            'socket_exists': os.path.exists(self.socket_path),
            'tests': []
        }

        if not results['socket_exists']:
            logger.error(f"Socket 不存在: {self.socket_path}")
            return results

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect(self.socket_path)

            logger.info("✅ 连接到 socket")

            # 测试消息列表
            test_messages = [
                {
                    'name': 'VS Code IPC (长度前缀)',
                    'data': b'\x00\x00\x00\x1b{"type":1,"method":"ping"}'
                },
                {
                    'name': 'VS Code IPC (带 ID)',
                    'data': b'\x00\x00\x00\x21{"id":"1","type":1,"method":"ping"}'
                },
                {
                    'name': 'JSON 行',
                    'data': b'{"type":1,"method":"ping"}\n'
                },
                {
                    'name': '简单 JSON',
                    'data': b'{"method":"ping"}'
                },
                {
                    'name': 'ping 文本',
                    'data': b'ping\n'
                },
                {
                    'name': 'VS Code 实际格式示例',
                    'data': b'\x00\x00\x00\x2f{"id":"1","type":1,"method":"$getConfiguration","params":{}}'
                }
            ]

            for test in test_messages:
                try:
                    logger.info(f"\n测试: {test['name']}")
                    logger.info(f"  发送: {test['data'][:50]}")

                    sock.sendall(test['data'])
                    response = sock.recv(4096)

                    logger.info(f"  响应: {response[:100]}")
                    logger.info(f"  长度: {len(response)} bytes")

                    results['tests'].append({
                        'name': test['name'],
                        'sent': len(test['data']),
                        'received': len(response),
                        'success': True
                    })

                    # 如果收到响应，尝试解析
                    if response:
                        try:
                            # 尝试去除长度前缀
                            if len(response) >= 4:
                                resp_length = struct.unpack('>I', response[:4])[0]
                                resp_content = response[4:]
                                if len(resp_content) == resp_length:
                                    logger.info(f"  (长度前缀验证通过)")
                                    json_data = json.loads(resp_content.decode('utf-8'))
                                    logger.info(f"  JSON: {json_data}")
                        except:
                            pass

                except socket.timeout:
                    logger.info("  响应: 超时")
                    results['tests'].append({
                        'name': test['name'],
                        'success': False,
                        'error': 'timeout'
                    })
                except Exception as e:
                    logger.info(f"  错误: {e}")
                    results['tests'].append({
                        'name': test['name'],
                        'success': False,
                        'error': str(e)
                    })

            sock.close()

        except Exception as e:
            logger.error(f"测试失败: {e}")
            results['error'] = str(e)

        return results


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Trae CN IPC 通信代理')
    parser.add_argument('--socket', '-s', help='Socket 路径')
    parser.add_argument('--test', '-t', action='store_true', help='运行协议测试')
    parser.add_argument('--port', '-p', type=int, default=12581, help='监听端口')
    parser.add_argument('--output', '-o', help='输出文件')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.test:
        # 运行协议测试
        print("=" * 60)
        print("协议格式测试")
        print("=" * 60)

        analyzer = TraeIPCAnalyzer(args.socket)
        results = analyzer.test_protocol()

        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)

        for test in results.get('tests', []):
            status = "✅" if test.get('success') else "❌"
            print(f"{status} {test['name']}")

    else:
        # 启动代理
        print("=" * 60)
        print("Trae CN IPC 通信代理")
        print("=" * 60)
        print("\n连接到 Trae CN 并监听 IPC 通信...")
        print("在 Trae CN 中执行操作以触发通信\n")

        proxy = TraeIPCProxy(
            socket_path=args.socket,
            listen_port=args.port,
            output_file=args.output
        )

        if proxy.start():
            print("\n✅ 代理运行中")
            print("   请在 Trae CN 中执行一些操作...")
        else:
            print("\n❌ 启动失败")


if __name__ == "__main__":
    main()

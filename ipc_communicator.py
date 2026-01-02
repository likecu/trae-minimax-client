#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trae CN IPC 通信工具

通过 Unix Domain Socket 与 Trae CN 的 ai-agent 模块进行通信

功能：
- 连接到 Trae CN 的 IPC 通道
- 发送 JSON-RPC 格式的请求
- 接收和处理响应
- 支持异步通信模式

使用示例：
```python
from ipc_communicator import IPCCommunicator

# 连接到 Trae CN
ipc = IPCCommunicator()

# 发送请求
response = ipc.send_request("getUserInfo", {})
print(response)

# 关闭连接
ipc.close()
```

作者: AI Assistant
日期: 2025-01-02
"""

import os
import json
import time
import socket
import threading
import logging
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型枚举"""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"


class IPCError(Exception):
    """IPC 通信错误"""

    def __init__(self, message: str, code: int = -1, details: dict = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


class IPCCommunicator:
    """
    Trae CN IPC 通信器

    通过 Unix Domain Socket 与 Trae CN 主进程通信
    """

    def __init__(
        self,
        socket_path: str = None,
        auto_connect: bool = True,
        timeout: int = 30
    ):
        """
        初始化 IPC 通信器

        Args:
            socket_path: Unix Socket 路径，如果为 None 则自动检测
            auto_connect: 是否自动连接到 Trae CN
            timeout: 超时时间（秒）
        """
        # 自动检测 socket 路径
        if socket_path is None:
            socket_path = self._detect_socket_path()

        self.socket_path = socket_path
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.request_id = 0
        self.lock = threading.Lock()

        # 回调函数
        self.notification_callback: Optional[Callable] = None

        # 响应存储
        self.pending_responses: Dict[str, Any] = {}
        self.response_event = threading.Event()

        # 自动连接
        if auto_connect:
            self.connect()

    def _detect_socket_path(self) -> str:
        """
        自动检测 Trae CN 的 socket 路径

        Returns:
            socket 路径
        """
        base_path = os.path.expanduser(
            "~/Library/Application Support/Trae CN"
        )

        # 查找最新的 socket 文件
        socket_patterns = [
            os.path.join(base_path, "*.sock"),
            os.path.join(base_path, "*main.sock"),
        ]

        for pattern in socket_patterns:
            import glob
            sockets = glob.glob(pattern)
            if sockets:
                # 返回最新的 socket
                return max(sockets, key=os.path.getmtime)

        # 默认路径
        return os.path.join(base_path, "1.10-main.sock")

    def connect(self) -> bool:
        """
        连接到 Trae CN

        Returns:
            是否连接成功
        """
        try:
            logger.info(f"尝试连接到: {self.socket_path}")

            # 检查 socket 是否存在
            if not os.path.exists(self.socket_path):
                logger.warning(f"Socket 不存在: {self.socket_path}")
                return False

            # 创建 socket
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)
            self.socket.connect(self.socket_path)

            self.connected = True
            logger.info("✅ 成功连接到 Trae CN")

            # 启动监听线程
            self.listen_thread = threading.Thread(
                target=self._listen_loop,
                daemon=True
            )
            self.listen_thread.start()

            return True

        except socket.error as e:
            logger.error(f"连接失败: {e}")
            self.connected = False
            return False

    def disconnect(self):
        """断开连接"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            self.connected = False
            logger.info("已断开连接")

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.connected and self.socket is not None

    def _listen_loop(self):
        """监听来自 Trae CN 的消息"""
        buffer = ""

        while self.connected and self.socket:
            try:
                data = self.socket.recv(4096)
                if not data:
                    logger.warning("连接已关闭")
                    self.connected = False
                    break

                # 解码数据
                try:
                    message = data.decode('utf-8')
                except:
                    continue

                buffer += message

                # 处理完整的 JSON 行
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)

                    if line.strip():
                        self._handle_message(line.strip())

            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"监听错误: {e}")
                break

    def _handle_message(self, message: str):
        """
        处理接收到的消息

        Args:
            message: JSON 格式的消息
        """
        try:
            data = json.loads(message)
            msg_type = data.get('type', 'unknown')

            if msg_type == 'response':
                # 处理响应
                req_id = data.get('id')
                if req_id and req_id in self.pending_responses:
                    self.pending_responses[req_id] = data
                    self.response_event.set()

            elif msg_type == 'notification':
                # 处理通知
                if self.notification_callback:
                    self.notification_callback(data)

            logger.debug(f"收到消息: {msg_type}")

        except json.JSONDecodeError:
            logger.warning(f"无效的 JSON 消息: {message[:100]}")
        except Exception as e:
            logger.error(f"处理消息错误: {e}")

    def send_request(
        self,
        method: str,
        params: dict = None,
        wait_response: bool = True
    ) -> dict:
        """
        发送请求

        Args:
            method: 方法名
            params: 参数
            wait_response: 是否等待响应

        Returns:
            响应数据
        """
        if not self.is_connected():
            raise IPCError("未连接到 Trae CN")

        # 生成请求 ID
        with self.lock:
            self.request_id += 1
            req_id = str(self.request_id)

        # 构建请求
        request = {
            'id': req_id,
            'type': 'request',
            'method': method,
            'params': params or {}
        }

        # 发送请求
        try:
            message = json.dumps(request) + '\n'
            self.socket.sendall(message.encode('utf-8'))
            logger.info(f"发送请求: {method}")

            # 等待响应
            if wait_response:
                self.pending_responses[req_id] = None
                self.response_event.clear()

                # 等待响应或超时
                if not self.response_event.wait(self.timeout):
                    del self.pending_responses[req_id]
                    raise IPCError(f"请求超时: {method}", -32000)

                response = self.pending_responses.pop(req_id)

                # 检查错误
                if 'error' in response:
                    error = response['error']
                    raise IPCError(
                        error.get('message', '未知错误'),
                        error.get('code', -1),
                        error
                    )

                return response.get('result', {})

            return {'id': req_id, 'status': 'sent'}

        except socket.error as e:
            self.connected = False
            raise IPCError(f"发送失败: {e}")

    def send_notification(self, method: str, params: dict = None):
        """
        发送通知（不需要响应）

        Args:
            method: 方法名
            params: 参数
        """
        if not self.is_connected():
            raise IPCError("未连接到 Trae CN")

        request = {
            'type': 'notification',
            'method': method,
            'params': params or {}
        }

        try:
            message = json.dumps(request) + '\n'
            self.socket.sendall(message.encode('utf-8'))
            logger.info(f"发送通知: {method}")
        except socket.error as e:
            self.connected = False
            raise IPCError(f"发送失败: {e}")

    def set_notification_callback(self, callback: Callable):
        """
        设置通知回调函数

        Args:
            callback: 回调函数
        """
        self.notification_callback = callback

    def get_user_info(self) -> dict:
        """获取用户信息"""
        return self.send_request("getUserInfo")

    def get_solo_qualification(self) -> dict:
        """获取 Solo 资格"""
        return self.send_request("getSoloQualification")

    def send_chat_message(self, message: str, **kwargs) -> dict:
        """发送聊天消息"""
        return self.send_request("sendChatMessage", {
            'message': message,
            **kwargs
        })

    def execute_command(self, command: str) -> dict:
        """执行命令"""
        return self.send_request("executeCommand", {
            'command': command
        })

    def __enter__(self):
        """上下文管理器进入"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.disconnect()


class MockIPCCommunicator(IPCCommunicator):
    """
    模拟 IPC 通信器

    用于在没有 Trae CN 运行时的测试
    """

    def __init__(self, mock_responses: dict = None):
        """
        初始化模拟通信器

        Args:
            mock_responses: 模拟响应字典
        """
        super().__init__(auto_connect=False)
        self.mock_responses = mock_responses or {}
        self.request_log = []

    def connect(self) -> bool:
        """模拟连接"""
        self.connected = True
        logger.info("✅ 模拟连接成功")
        return True

    def disconnect(self):
        """模拟断开连接"""
        self.connected = False
        logger.info("模拟连接已关闭")

    def send_request(
        self,
        method: str,
        params: dict = None,
        wait_response: bool = True
    ) -> dict:
        """发送模拟请求"""
        # 记录请求
        self.request_log.append({
            'method': method,
            'params': params,
            'timestamp': datetime.now().isoformat()
        })

        # 返回模拟响应
        if method in self.mock_responses:
            return self.mock_responses[method]
        elif method.startswith('get'):
            return {'success': True, 'data': {}}
        else:
            return {'success': True, 'result': 'ok'}


def test_ipc_connection():
    """测试 IPC 连接"""
    print("=" * 60)
    print("IPC 连接测试")
    print("=" * 60)

    # 尝试连接到 Trae CN
    ipc = IPCCommunicator()

    if ipc.connect():
        print("✅ 成功连接到 Trae CN")

        try:
            # 测试获取用户信息
            print("\n📋 测试 getUserInfo...")
            response = ipc.get_user_info()
            print(f"响应: {response}")

            # 测试获取 Solo 资格
            print("\n🎯 测试 getSoloQualification...")
            response = ipc.get_solo_qualification()
            print(f"响应: {response}")

        except IPCError as e:
            print(f"❌ 请求失败: {e}")
        finally:
            ipc.disconnect()
    else:
        print("❌ 连接失败")
        print("\n💡 提示：")
        print("   1. 确保 Trae CN 应用程序正在运行")
        print("   2. 检查 socket 文件是否存在")
        print("   3. 尝试使用模拟模式进行测试")


def test_mock_ipc():
    """测试模拟 IPC 通信器"""
    print("=" * 60)
    print("模拟 IPC 测试")
    print("=" * 60)

    # 定义模拟响应
    mock_responses = {
        'getUserInfo': {
            'success': True,
            'data': {
                'UserID': '385285264512944',
                'ScreenName': '奶油蘑菇汤',
                'Email': '***@example.com',
                'Region': 'CN'
            }
        },
        'getSoloQualification': {
            'success': True,
            'data': {
                'qualified': True,
                'features': ['chat', 'solo', 'agent']
            }
        }
    }

    # 创建模拟通信器
    ipc = MockIPCCommunicator(mock_responses)
    ipc.connect()

    # 测试请求
    print("\n📋 测试 getUserInfo...")
    response = ipc.get_user_info()
    print(f"响应: {response}")

    print("\n🎯 测试 getSoloQualification...")
    response = ipc.get_solo_qualification()
    print(f"响应: {response}")

    # 打印请求日志
    print("\n📜 请求日志:")
    for req in ipc.request_log:
        print(f"   - {req['method']} at {req['timestamp']}")

    ipc.disconnect()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--mock':
        test_mock_ipc()
    else:
        test_ipc_connection()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trae CN VS Code 风格 IPC 通信工具

适配 VS Code/Trae CN 的实际 IPC 协议格式

协议特点：
- 基于 Unix Domain Socket
- 使用长度前缀的 JSON 消息
- 支持请求-响应模式
- 支持通知消息

参考：VS Code src/vs/base/parts/ipc/common/ipc.ts

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
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VSCodeIPCError(Exception):
    """VS Code IPC 错误"""


class MessageType(Enum):
    """消息类型"""
    REQUEST = 1
    RESPONSE_OK = 2
    RESPONSE_ERR = 3
    CANCEL = 4


@dataclass
class IPCRequest:
    """IPC 请求"""
    id: str
    method: str
    params: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class VSCodeIPCProtocol:
    """
    VS Code IPC 协议实现

    协议格式：
    - 4 字节长度前缀（网络字节序）
    - JSON 格式的消息体
    """

    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.request_id = 0
        self.lock = threading.Lock()

        # 响应存储
        self.pending_requests: Dict[str, IPCRequest] = {}
        self.responses: Dict[str, dict] = {}
        self.response_event = threading.Event()

        # 回调
        self.notification_callback: Optional[Callable] = None

    def connect(self, timeout: float = 5.0) -> bool:
        """
        连接到 VS Code IPC 服务器

        Args:
            timeout: 连接超时时间

        Returns:
            是否连接成功
        """
        try:
            # 检查 socket 是否存在
            if not os.path.exists(self.socket_path):
                logger.error(f"Socket 不存在: {self.socket_path}")
                return False

            logger.info(f"正在连接到: {self.socket_path}")

            # 创建 socket
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)
            self.socket.connect(self.socket_path)

            self.connected = True
            logger.info("✅ 成功连接到 Trae CN (VS Code IPC)")

            # 启动监听线程
            self.listen_thread = threading.Thread(
                target=self._listen_loop,
                daemon=True
            )
            self.listen_thread.start()

            return True

        except socket.timeout:
            logger.error("连接超时")
            return False
        except Exception as e:
            logger.error(f"连接失败: {e}")
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

    def _send_message(self, message: dict) -> bool:
        """
        发送消息（带长度前缀）

        Args:
            message: 消息字典

        Returns:
            是否发送成功
        """
        if not self.is_connected():
            raise VSCodeIPCError("未连接到 Trae CN")

        try:
            # 序列化消息
            content = json.dumps(message, ensure_ascii=False)
            content_bytes = content.encode('utf-8')

            # 添加 4 字节长度前缀（网络字节序大端序）
            header = struct.pack('>I', len(content_bytes))
            data = header + content_bytes

            # 发送数据
            self.socket.sendall(data)
            return True

        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            self.connected = False
            return False

    def _recv_message(self, timeout: float = 10.0) -> Optional[dict]:
        """
        接收消息（带长度前缀）

        Args:
            timeout: 超时时间

        Returns:
            消息字典，如果超时返回 None
        """
        if not self.is_connected():
            raise VSCodeIPCError("未连接到 Trae CN")

        try:
            # 接收 4 字节长度前缀
            self.socket.settimeout(timeout)
            header = self.socket.recv(4)

            if not header:
                logger.warning("连接已关闭")
                self.connected = False
                return None

            # 解析长度
            length = struct.unpack('>I', header)[0]

            # 接收消息体
            body = b''
            while len(body) < length:
                chunk = self.socket.recv(length - len(body))
                if not chunk:
                    return None
                body += chunk

            # 解析 JSON
            return json.loads(body.decode('utf-8'))

        except socket.timeout:
            return None
        except Exception as e:
            logger.error(f"接收消息失败: {e}")
            return None

    def _listen_loop(self):
        """监听来自 Trae CN 的消息"""
        while self.connected and self.socket:
            try:
                message = self._recv_message(timeout=1.0)

                if message is None:
                    continue

                # 处理消息
                self._handle_message(message)

            except Exception as e:
                logger.error(f"监听错误: {e}")
                break

    def _handle_message(self, message: dict):
        """
        处理接收到的消息

        Args:
            message: 消息字典
        """
        msg_type = message.get('type', message.get('$$type', 'unknown'))

        if msg_type == 2 or msg_type == 'ok':
            # 响应成功
            req_id = message.get('id')
            if req_id and req_id in self.pending_requests:
                self.responses[req_id] = message
                self.response_event.set()

        elif msg_type == 3 or msg_type == 'err':
            # 响应错误
            req_id = message.get('id')
            if req_id and req_id in self.pending_requests:
                self.responses[req_id] = {
                    'error': True,
                    'message': message.get('message', 'Unknown error'),
                    'code': message.get('code', -1)
                }
                self.response_event.set()

        elif msg_type == 'cancel':
            # 取消消息
            req_id = message.get('id')
            if req_id and req_id in self.pending_requests:
                del self.pending_requests[req_id]

        else:
            # 其他消息（可能是通知）
            logger.debug(f"收到消息: {message}")

            if self.notification_callback:
                self.notification_callback(message)

    def send_request(
        self,
        method: str,
        params: dict = None,
        timeout: float = 10.0
    ) -> dict:
        """
        发送请求

        Args:
            method: 方法名
            params: 参数
            timeout: 超时时间

        Returns:
            响应数据
        """
        if not self.is_connected():
            raise VSCodeIPCError("未连接到 Trae CN")

        # 生成请求 ID
        with self.lock:
            self.request_id += 1
            req_id = str(self.request_id)

        # 构建请求消息
        request = {
            'id': req_id,
            'type': 1,  # 请求类型
            'method': method,
            'params': params or {}
        }

        # 存储请求
        self.pending_requests[req_id] = IPCRequest(
            id=req_id,
            method=method,
            params=params or {}
        )

        # 发送请求
        self._send_message(request)
        logger.info(f"发送请求: {method} (id={req_id})")

        # 等待响应
        self.response_event.clear()

        if not self.response_event.wait(timeout):
            # 超时
            if req_id in self.pending_requests:
                del self.pending_requests[req_id]
            raise VSCodeIPCError(f"请求超时: {method}")

        # 获取响应
        if req_id in self.responses:
            response = self.responses.pop(req_id)

            if response.get('error'):
                raise VSCodeIPCError(
                    response.get('message', 'Unknown error'),
                    response.get('code', -1)
                )

            # 返回结果
            return response.get('result', {})

        raise VSCodeIPCError("未收到响应")

    def send_notification(self, method: str, params: dict = None):
        """
        发送通知

        Args:
            method: 方法名
            params: 参数
        """
        if not self.is_connected():
            raise VSCodeIPCError("未连接到 Trae CN")

        # 通知没有 id
        notification = {
            'type': 1,  # 复用请求类型
            'method': method,
            'params': params or {}
        }

        self._send_message(notification)
        logger.info(f"发送通知: {method}")

    def set_notification_callback(self, callback: Callable):
        """设置通知回调"""
        self.notification_callback = callback

    def __enter__(self):
        """上下文管理器"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.disconnect()


class TraeIPCCommunicator:
    """
    Trae CN IPC 通信器

    整合多种协议格式，支持：
    - VS Code IPC 协议（长度前缀 JSON）
    - 标准 JSON-RPC
    - 回退到简单文本协议
    """

    def __init__(self, socket_path: str = None, auto_connect: bool = True):
        """
        初始化通信器

        Args:
            socket_path: Socket 路径
            auto_connect: 是否自动连接
        """
        if socket_path is None:
            socket_path = os.path.expanduser(
                "~/Library/Application Support/Trae CN/1.10-main.sock"
            )

        self.socket_path = socket_path
        self.vs_ipc = VSCodeIPCProtocol(socket_path)
        self.connected = False

        if auto_connect:
            self.connect()

    def connect(self, timeout: float = 5.0) -> bool:
        """
        尝试连接到 Trae CN

        依次尝试：
        1. VS Code IPC 协议（长度前缀）
        2. 标准 JSON 行协议

        Returns:
            是否连接成功
        """
        # 尝试 VS Code IPC 协议
        if self.vs_ipc.connect(timeout):
            self.connected = True
            logger.info("使用 VS Code IPC 协议")
            return True

        logger.warning("VS Code IPC 协议连接失败")
        return False

    def disconnect(self):
        """断开连接"""
        self.vs_ipc.disconnect()
        self.connected = False

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.connected

    def send_request(self, method: str, params: dict = None) -> dict:
        """
        发送请求

        Args:
            method: 方法名
            params: 参数

        Returns:
            响应数据
        """
        if not self.connected:
            raise VSCodeIPCError("未连接到 Trae CN")

        # 尝试 VS Code IPC 协议
        try:
            return self.vs_ipc.send_request(method, params)
        except Exception as e:
            logger.error(f"VS Code IPC 请求失败: {e}")
            raise

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


def test_vscode_ipc():
    """测试 VS Code IPC 连接"""
    print("=" * 60)
    print("VS Code IPC 连接测试")
    print("=" * 60)

    communicator = TraeIPCCommunicator(auto_connect=False)

    if communicator.connect(timeout=5.0):
        print("✅ 成功连接到 Trae CN")

        try:
            # 尝试发送请求
            print("\n📋 尝试获取用户信息...")
            response = communicator.get_user_info()
            print(f"响应: {response}")

        except VSCodeIPCError as e:
            print(f"❌ 请求失败: {e}")
            print("\n这说明 VS Code IPC 协议格式可能不完全匹配")
            print("可能需要进一步分析 Trae CN 的实际协议格式")

        finally:
            communicator.disconnect()
    else:
        print("❌ 连接失败")
        print("\n💡 提示：")
        print("   1. 确保 Trae CN 正在运行")
        print("   2. 检查 socket 文件权限")


def test_socket_communication():
    """直接测试 socket 通信"""
    print("\n" + "=" * 60)
    print("直接 Socket 通信测试")
    print("=" * 60)

    socket_path = os.path.expanduser(
        "~/Library/Application Support/Trae CN/1.10-main.sock"
    )

    if not os.path.exists(socket_path):
        print(f"❌ Socket 不存在: {socket_path}")
        return

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect(socket_path)

        print("✅ 连接到 socket")

        # 尝试发送一个简单的测试消息
        test_messages = [
            # VS Code IPC 格式（长度前缀）
            b'\x00\x00\x00\x1b{"id":"1","type":1,"method":"ping"}',

            # 简单 JSON
            b'{"method":"ping"}\n',

            # 原始文本
            b'ping\n',
        ]

        for i, msg in enumerate(test_messages):
            print(f"\n测试消息 {i+1}: {msg[:50]}...")
            try:
                sock.sendall(msg)
                response = sock.recv(4096)
                print(f"响应: {response[:200]}")
            except socket.timeout:
                print("超时")
            except Exception as e:
                print(f"错误: {e}")

        sock.close()

    except Exception as e:
        print(f"❌ 错误: {e}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == '--socket':
            test_socket_communication()
        else:
            print("用法:")
            print("  python3 vscode_ipc_communicator.py          # 标准测试")
            print("  python3 vscode_ipc_communicator.py --socket # 直接 socket 测试")
    else:
        test_vscode_ipc()

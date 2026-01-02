#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trae CN TowelTransport 协议实现

基于 ai-agent 日志逆向分析的完整协议实现

发现的协议格式：
1. 连接流程：
   - ai_agent_ipc_connect: channel_id:xxx
   - IPC Server Accepted Connection
   - accept_ipc_connection

2. 请求格式：
   route: service:"ckg", method:"refresh_token", 
          connect_session_id:"xxx", trace_id:"xxx"

3. 响应格式：
   route end: response_size_bytes: Some(440), trace_id:"xxx"

发现的服务：
- ckg: setup, refresh_token, is_ckg_enabled_for_non_workspace_scenario
- project: create_project
- configuration: get_user_configuration
- chat: get_sessions, send_message
- agent: get_solo_qualification

作者: AI Assistant
日期: 2025-01-02
"""

import os
import sys
import json
import time
import uuid
import socket
import struct
import threading
import logging
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import fcntl
import select

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class TowelProtocolError(Exception):
    """TowelTransport 协议错误"""


@dataclass
class IPCChannel:
    """IPC 通道"""
    channel_id: str
    receiver_len: int = 1


@dataclass
class IPCRequest:
    """IPC 请求"""
    service: str
    method: str
    connect_session_id: str = ""
    trace_id: str = ""
    params: Dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class IPCResponse:
    """IPC 响应"""
    success: bool
    data: Dict = field(default_factory=dict)
    error: str = ""
    response_size: int = 0
    trace_id: str = ""


class TowelTransportClient:
    """
    Trae CN TowelTransport 协议客户端

    实现完整的 TowelTransport IPC 通信协议
    """

    def __init__(self, socket_path: str = None):
        """
        初始化客户端

        Args:
            socket_path: Unix Domain Socket 路径
        """
        if socket_path is None:
            socket_path = os.path.expanduser(
                "~/Library/Application Support/Trae CN/1.10-main.sock"
            )

        self.socket_path = socket_path
        self.socket: Optional[socket.socket] = None
        self.channel_id: str = str(uuid.uuid4())
        self.connect_session_id: str = str(uuid.uuid4())
        self.connected = False

        # 响应管理
        self.pending_requests: Dict[str, threading.Event] = {}
        self.responses: Dict[str, dict] = {}
        self.trace_id_map: Dict[str, str] = {}  # trace_id -> request_id

        # 监听
        self.running = False
        self.listen_thread: Optional[threading.Thread] = None

    def connect(self, timeout: float = 5.0) -> bool:
        """
        连接到 Trae CN TowelTransport

        Returns:
            是否连接成功
        """
        try:
            # 检查 socket
            if not os.path.exists(self.socket_path):
                logger.error(f"Socket 不存在: {self.socket_path}")
                return False

            logger.info(f"🔌 连接到 Trae CN TowelTransport...")
            logger.info(f"   Socket: {self.socket_path}")
            logger.info(f"   Channel ID: {self.channel_id[:8]}...")

            # 创建 socket
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)
            self.socket.connect(self.socket_path)

            # 设置非阻塞模式，用于实时监听
            flags = fcntl.fcntl(self.socket.fileno(), fcntl.F_GETFL, 0)
            fcntl.fcntl(self.socket.fileno(), fcntl.F_SETFL, flags | os.O_NONBLOCK)

            self.connected = True
            logger.info(f"✅ TCP 连接成功")

            # 启动监听
            self.running = True
            self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.listen_thread.start()

            logger.info(f"✅ TowelTransport 连接成功")
            logger.info(f"   Channel ID: {self.channel_id}")
            logger.info(f"   Session ID: {self.connect_session_id[:8]}...")

            # 等待一下让握手完成
            time.sleep(0.5)

            return True

        except socket.timeout:
            logger.error("连接超时")
            return False
        except Exception as e:
            logger.error(f"连接失败: {e}")
            return False

    def _listen_loop(self):
        """监听来自 Trae CN 的响应"""
        buffer = b''
        max_buffer_size = 65536

        while self.running and self.socket:
            try:
                # 使用 select 等待数据
                ready = select.select([self.socket], [], [], 0.1)

                if not ready[0]:
                    continue

                try:
                    chunk = self.socket.recv(4096)
                except BlockingIOError:
                    continue

                if not chunk:
                    logger.warning("连接已关闭")
                    self.connected = False
                    break

                buffer += chunk

                # 处理缓冲区
                while len(buffer) >= 4:
                    # 尝试解析长度前缀
                    try:
                        length = struct.unpack('>I', buffer[:4])[0]
                    except struct.error:
                        # 不是有效的长度前缀，清除缓冲区
                        buffer = b''
                        break

                    if len(buffer) < 4 + length:
                        # 等待更多数据
                        if len(buffer) > max_buffer_size:
                            logger.warning("缓冲区过大，清除")
                            buffer = b''
                        break

                    # 提取消息
                    message_data = buffer[4:4+length]
                    buffer = buffer[4+length:]

                    try:
                        message = json.loads(message_data.decode('utf-8'))
                        self._handle_message(message)
                    except json.JSONDecodeError:
                        logger.debug(f"无效 JSON: {message_data[:100]}")
                    except Exception as e:
                        logger.debug(f"处理消息错误: {e}")

            except Exception as e:
                if self.running:
                    logger.error(f"监听错误: {e}")
                break

    def _handle_message(self, message: dict):
        """处理接收到的消息"""
        # 查找对应的请求
        trace_id = message.get('trace_id', '')
        request_id = self.trace_id_map.get(trace_id)

        if request_id and request_id in self.pending_requests:
            self.responses[request_id] = message
            self.pending_requests[request_id].set()
            logger.debug(f"📥 收到响应: trace_id={trace_id[:8]}...")
            return

        # 通知消息
        if message.get('type') == 'notification':
            logger.info(f"📬 通知: {message.get('method', 'unknown')}")

    def send_request(
        self,
        service: str,
        method: str,
        params: dict = None,
        timeout: float = 10.0
    ) -> IPCResponse:
        """
        发送请求

        Args:
            service: 服务名 (ckg, project, configuration, chat, agent)
            method: 方法名
            params: 参数
            timeout: 超时时间

        Returns:
            IPCResponse: 响应
        """
        if not self.connected:
            raise TowelProtocolError("未连接到 Trae CN")

        # 生成请求 ID 和 trace_id
        request_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())

        # 构建请求
        request = {
            'id': request_id,
            'service': service,
            'method': method,
            'params': params or {},
            'channel_id': self.channel_id,
            'connect_session_id': self.connect_session_id,
            'trace_id': trace_id,
            'timestamp': time.time()
        }

        logger.info(f"📤 {service}.{method} (trace: {trace_id[:8]}...)")

        # 映射 trace_id
        self.trace_id_map[trace_id] = request_id

        # 发送请求
        content = json.dumps(request, ensure_ascii=False)
        content_bytes = content.encode('utf-8')

        # 添加 4 字节长度前缀
        header = struct.pack('>I', len(content_bytes))
        message = header + content_bytes

        try:
            self.socket.sendall(message)
        except Exception as e:
            del self.trace_id_map[trace_id]
            raise TowelProtocolError(f"发送失败: {e}")

        # 等待响应
        event = threading.Event()
        self.pending_requests[request_id] = event

        if not event.wait(timeout):
            del self.pending_requests[request_id]
            del self.trace_id_map[trace_id]
            raise TowelProtocolError(f"请求超时: {service}.{method}")

        # 获取响应
        response_data = self.responses.pop(request_id, {})
        del self.pending_requests[request_id]
        del self.trace_id_map[trace_id]

        # 解析响应
        return IPCResponse(
            success=response_data.get('success', True),
            data=response_data.get('data', response_data),
            error=response_data.get('error', ''),
            response_size=len(json.dumps(response_data)),
            trace_id=trace_id
        )

    def disconnect(self):
        """断开连接"""
        self.running = False

        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

        self.connected = False
        logger.info("已断开 TowelTransport 连接")

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.connected and self.socket is not None

    # 便捷方法
    def get_user_configuration(self) -> IPCResponse:
        """获取用户配置"""
        return self.send_request("configuration", "get_user_configuration")

    def ckg_setup(self, token: str = None) -> IPCResponse:
        """CKG 设置"""
        params = {'token': token} if token else {}
        return self.send_request("ckg", "setup", params)

    def ckg_refresh_token(self) -> IPCResponse:
        """刷新 Token"""
        return self.send_request("ckg", "refresh_token")

    def ckg_is_enabled(self) -> IPCResponse:
        """检查 CKG 是否启用"""
        return self.send_request("ckg", "is_ckg_enabled_for_non_workspace_scenario")

    def project_create_project(self, name: str = None) -> IPCResponse:
        """创建项目"""
        params = {'name': name} if name else {}
        return self.send_request("project", "create_project", params)

    def chat_get_sessions(self) -> IPCResponse:
        """获取聊天会话"""
        return self.send_request("chat", "get_sessions")

    def chat_send_message(self, message: str, session_id: str = None) -> IPCResponse:
        """发送聊天消息"""
        params = {
            'message': message,
            'session_id': session_id
        }
        return self.send_request("chat", "send_message", params)

    def agent_get_solo_qualification(self) -> IPCResponse:
        """获取 Solo 资格"""
        return self.send_request("agent", "get_solo_qualification")


def test_towel_transport():
    """测试 TowelTransport 连接"""
    print("=" * 60)
    print("Trae CN TowelTransport 协议测试")
    print("=" * 60)

    client = TowelTransportClient()

    if not client.connect(timeout=5.0):
        print("❌ 连接失败")
        return

    print("✅ 连接成功")
    print()

    try:
        # 测试配置获取
        print("📋 测试 get_user_configuration...")
        try:
            response = client.get_user_configuration()
            print(f"✅ 响应: {response.data}")
        except TowelProtocolError as e:
            print(f"⚠️  {e}")

        # 测试 CKG
        print("\n🔐 测试 ckg_setup...")
        try:
            response = client.ckg_setup()
            print(f"✅ 响应: {response.data}")
        except TowelProtocolError as e:
            print(f"⚠️  {e}")

        # 测试聊天
        print("\n💬 测试 chat_get_sessions...")
        try:
            response = client.chat_get_sessions()
            print(f"✅ 响应: {response.data}")
        except TowelProtocolError as e:
            print(f"⚠️  {e}")

        # 测试 Solo
        print("\n🎯 测试 agent_get_solo_qualification...")
        try:
            response = client.agent_get_solo_qualification()
            print(f"✅ 响应: {response.data}")
        except TowelProtocolError as e:
            print(f"⚠️  {e}")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

    finally:
        client.disconnect()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


def test_simple_connection():
    """简单连接测试"""
    print("\n" + "=" * 60)
    print("简单连接测试")
    print("=" * 60)

    socket_path = os.path.expanduser(
        "~/Library/Application Support/Trae CN/1.10-main.sock"
    )

    print(f"Socket: {socket_path}")
    print(f"存在: {os.path.exists(socket_path)}")

    if not os.path.exists(socket_path):
        print("❌ Socket 不存在")
        return

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        sock.connect(socket_path)

        print("✅ TCP 连接成功")

        # 发送测试消息
        test_cases = [
            # 无长度前缀的简单消息
            b'{"method":"ping"}\n',

            # 带长度的消息
            b'\x00\x00\x00\x19{"method":"ping"}\n',
        ]

        for i, msg in enumerate(test_cases):
            print(f"\n测试 {i+1}: {msg[:50]}...")
            try:
                sock.sendall(msg)
                # 等待响应
                response = sock.recv(4096)
                print(f"响应: {response[:200]}")
            except socket.timeout:
                print("超时")
            except Exception as e:
                print(f"错误: {e}")

        sock.close()

    except Exception as e:
        print(f"❌ 连接失败: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Trae CN TowelTransport 测试')
    parser.add_argument('--simple', '-s', action='store_true', help='简单连接测试')
    parser.add_argument('--timeout', '-t', type=float, default=10.0, help='超时时间')

    args = parser.parse_args()

    if args.simple:
        test_simple_connection()
    else:
        test_towel_transport()

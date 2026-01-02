#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trae CN 完整客户端实现

基于日志逆向分析，实现了所有发现的 API 和通信功能

功能：
1. REST API 调用（已验证可用）
2. IPC 通信（基于 TowelTransport 协议）
3. Solo 功能
4. 用户管理
5. 聊天功能

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
import hashlib
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class RequestType(Enum):
    """请求类型"""
    AGENT = "agent"
    MODEL = "model"
    CHAT = "chat"
    CONFIG = "config"
    USER = "user"
    ICUBE = "icube"
    TRAE = "trae"
    SOLO = "solo"


@dataclass
class TraeConfig:
    """Trae CN 配置"""
    base_url: str = "https://api.trae.com.cn"
    token: str = ""
    timeout: int = 60
    max_retries: int = 3
    enable_logging: bool = True


@dataclass
class UserProfile:
    """用户资料"""
    user_id: str = ""
    screen_name: str = ""
    email: str = ""
    region: str = "CN"

    @classmethod
    def from_dict(cls, data: Dict) -> 'UserProfile':
        return cls(
            user_id=data.get('UserID', data.get('userId', '')),
            screen_name=data.get('ScreenName', data.get('screenName', '')),
            email=data.get('Email', data.get('email', '')),
            region=data.get('Region', data.get('region', 'CN'))
        )


@dataclass
class SoloQualification:
    """Solo 资格"""
    qualified: bool = False
    can_use_solo: bool = False
    plan_type: str = "free"
    features: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict) -> 'SoloQualification':
        return cls(
            qualified=data.get('qualified', False),
            can_use_solo=data.get('can_use_solo', False),
            plan_type=data.get('plan_type', 'free'),
            features=data.get('features', [])
        )


class TowelTransportIPC:
    """
    Trae CN TowelTransport IPC 协议实现

    基于 ai-agent 日志逆向分析：
    - 服务: ckg, project, configuration, chat, agent
    - 方法: refresh_token, setup, get_user_configuration
    - 格式: 基于 channel_id 的请求-响应模式
    """

    def __init__(self, socket_path: str = None):
        """
        初始化 TowelTransport IPC

        Args:
            socket_path: Socket 路径
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

        # 请求队列
        self.pending_requests: Dict[str, threading.Event] = {}
        self.responses: Dict[str, dict] = {}

    def connect(self, timeout: float = 5.0) -> bool:
        """
        连接到 Trae CN TowelTransport

        Returns:
            是否连接成功
        """
        try:
            if not os.path.exists(self.socket_path):
                logger.warning(f"Socket 不存在: {self.socket_path}")
                return False

            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)
            self.socket.connect(self.socket_path)

            self.connected = True
            logger.info(f"✅ 连接到 TowelTransport (channel: {self.channel_id[:8]})")

            # 启动监听
            threading.Thread(target=self._listen_loop, daemon=True).start()

            return True

        except Exception as e:
            logger.error(f"连接失败: {e}")
            return False

    def disconnect(self):
        """断开连接"""
        if self.socket:
            self.socket.close()
            self.socket = None
            self.connected = False
            logger.info("已断开 TowelTransport 连接")

    def _listen_loop(self):
        """监听循环"""
        buffer = b''
        while self.connected and self.socket:
            try:
                self.socket.settimeout(1.0)
                chunk = self.socket.recv(4096)

                if not chunk:
                    break

                buffer += chunk

                # 尝试解析消息
                while len(buffer) >= 4:
                    length = struct.unpack('>I', buffer[:4])[0]
                    if len(buffer) < 4 + length:
                        break

                    message = buffer[4:4+length]
                    buffer = buffer[4+length:]

                    try:
                        data = json.loads(message.decode('utf-8'))
                        self._handle_message(data)
                    except:
                        pass

            except socket.timeout:
                continue
            except Exception as e:
                if self.connected:
                    logger.error(f"监听错误: {e}")
                break

    def _handle_message(self, message: dict):
        """处理接收到的消息"""
        # 检查是否有待处理的请求
        for req_id, event in self.pending_requests.items():
            if event.is_set():
                continue

            # 简单匹配：检查响应中是否包含请求的 trace_id
            if message.get('trace_id') or message.get('request_id'):
                self.responses[req_id] = message
                event.set()
                break

    def send_request(
        self,
        service: str,
        method: str,
        params: dict = None,
        timeout: float = 10.0
    ) -> dict:
        """
        发送请求到 Trae CN

        Args:
            service: 服务名 (ckg, project, configuration, chat, agent)
            method: 方法名
            params: 参数
            timeout: 超时时间

        Returns:
            响应数据
        """
        if not self.connected:
            raise RuntimeError("未连接到 Trae CN")

        # 生成请求 ID
        request_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())

        # 构建请求消息
        request = {
            'service': service,
            'method': method,
            'params': params or {},
            'request_id': request_id,
            'trace_id': trace_id,
            'channel_id': self.channel_id,
            'connect_session_id': self.connect_session_id,
            'timestamp': time.time()
        }

        # 序列化并发送（带长度前缀）
        content = json.dumps(request, ensure_ascii=False)
        content_bytes = content.encode('utf-8')
        header = struct.pack('>I', len(content_bytes))
        message = header + content_bytes

        # 发送请求
        self.socket.sendall(message)
        logger.info(f"📤 {service}.{method} (trace: {trace_id[:8]})")

        # 等待响应
        event = threading.Event()
        self.pending_requests[request_id] = event

        if not event.wait(timeout):
            del self.pending_requests[request_id]
            raise TimeoutError(f"请求超时: {service}.{method}")

        # 获取响应
        response = self.responses.pop(request_id, {})
        del self.pending_requests[request_id]

        logger.info(f"📥 响应: {response.get('status', 'unknown')}")
        return response

    # 便捷方法
    def get_user_info(self) -> dict:
        """获取用户信息"""
        return self.send_request("configuration", "get_user_configuration")

    def get_solo_qualification(self) -> dict:
        """获取 Solo 资格"""
        return self.send_request("agent", "get_solo_qualification")

    def refresh_token(self) -> dict:
        """刷新 Token"""
        return self.send_request("ckg", "refresh_token")


class TraeClient:
    """
    Trae CN 完整客户端

    整合 REST API 和 IPC 通信
    """

    def __init__(
        self,
        token: str = None,
        config: TraeConfig = None,
        use_ipc: bool = False
    ):
        """
        初始化客户端

        Args:
            token: 认证令牌
            config: 配置对象
            use_ipc: 是否使用 IPC 通信
        """
        self.config = config or TraeConfig()
        self.config.token = token or self.config.token

        self.transport = _RESTTransport(self.config)
        self.ipc: Optional[TowelTransportIPC] = None

        if use_ipc:
            self._init_ipc()

    def _init_ipc(self):
        """初始化 IPC"""
        try:
            self.ipc = TowelTransportIPC()
            if self.ipc.connect():
                logger.info("IPC 通信已初始化")
            else:
                logger.warning("IPC 连接失败，将仅使用 REST API")
                self.ipc = None
        except Exception as e:
            logger.warning(f"IPC 初始化失败: {e}")

    def authenticate(self, username: str, password: str) -> bool:
        """用户认证"""
        try:
            result = self.transport.execute_request(
                method="POST",
                endpoint="/auth/login",
                data={"username": username, "password": password}
            )
            if "token" in result:
                self.config.token = result["token"]
                return True
            return False
        except Exception as e:
            logger.error(f"认证失败: {e}")
            return False

    def get_user_info(self) -> Optional[UserProfile]:
        """获取用户信息"""
        try:
            # 尝试 REST API
            result = self.transport.execute_request(
                method="GET",
                endpoint="/cloudide/api/v3/trae/GetUserInfo"
            )

            if "Result" in result:
                return UserProfile.from_dict(result["Result"])

            return UserProfile.from_dict(result)
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return None

    def get_solo_qualification(self) -> Optional[SoloQualification]:
        """获取 Solo 资格"""
        try:
            result = self.transport.execute_request(
                method="GET",
                endpoint="/trae/api/v1/trae_solo_qualification"
            )

            data = result.get('Result', result)
            return SoloQualification.from_dict(data)
        except Exception as e:
            logger.error(f"获取 Solo 资格失败: {e}")
            return None

    def get_native_config(self, mid: str, did: str, uid: str) -> dict:
        """获取原生配置"""
        try:
            params = {
                "mid": mid,
                "did": did,
                "uid": uid,
                "userRegion": "CN",
                "packageType": "stable_cn",
                "platform": "Mac",
                "arch": "arm64",
                "tenant": "marscode",
                "appVersion": "3.3.11",
                "buildVersion": "1.0.27213",
                "traeVersionCode": "20250325"
            }

            return self.transport.execute_request(
                method="GET",
                endpoint="/icube/api/v1/native/config/query",
                params=params
            )
        except Exception as e:
            logger.error(f"获取原生配置失败: {e}")
            return {}

    def check_solo_available(self) -> dict:
        """检查 Solo 是否可用"""
        qualification = self.get_solo_qualification()
        return {
            "available": qualification.can_use_solo if qualification else False,
            "qualified": qualification.qualified if qualification else False,
            "plan": qualification.plan_type if qualification else "unknown",
            "features": qualification.features if qualification else []
        }

    def close(self):
        """关闭客户端"""
        if self.ipc:
            self.ipc.disconnect()
            self.ipc = None


class _RESTTransport:
    """REST API 传输层"""

    def __init__(self, config: TraeConfig):
        self.config = config
        self.session = requests.Session()

    def get_headers(self) -> dict:
        """获取请求头"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Trae-CN/3.3.11"
        }
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
            headers["x-cloudide-token"] = self.config.token
        return headers

    def execute_request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        data: dict = None
    ) -> dict:
        """执行 REST 请求"""
        url = f"{self.config.base_url}{endpoint}"
        headers = self.get_headers()

        logger.info(f"[REST] {method} {endpoint}")

        try:
            if method.upper() == "GET":
                response = self.session.get(
                    url, params=params, headers=headers,
                    timeout=self.config.timeout
                )
            elif method.upper() == "POST":
                response = self.session.post(
                    url, params=params, json=data, headers=headers,
                    timeout=self.config.timeout
                )
            else:
                raise ValueError(f"不支持的方法: {method}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP 错误: {e}")
            raise
        except Exception as e:
            logger.error(f"请求失败: {e}")
            raise


def create_client(token: str = None, use_ipc: bool = False) -> TraeClient:
    """创建客户端"""
    return TraeClient(token=token, use_ipc=use_ipc)


def get_token_from_storage(storage_path: str = None) -> Optional[str]:
    """从存储提取 Token"""
    if storage_path is None:
        storage_path = os.path.expanduser(
            "~/Library/Application Support/Trae CN/User/globalStorage/storage.json"
        )

    try:
        with open(storage_path, 'r') as f:
            data = json.load(f)

        for key in data:
            if 'iCubeAuthInfo' in key and 'cloudide' in key:
                auth_data = json.loads(data[key])
                return auth_data.get('token')

    except Exception as e:
        logger.error(f"提取 Token 失败: {e}")

    return None


def test_client():
    """测试客户端"""
    print("=" * 60)
    print("Trae CN 客户端测试")
    print("=" * 60)

    # 提取 Token
    token = get_token_from_storage()
    if token:
        print(f"✅ Token 提取成功: {token[:50]}...")
    else:
        print("❌ Token 提取失败")
        return

    # 创建客户端
    client = create_client(token=token, use_ipc=False)
    print("✅ 客户端创建成功")

    # 测试用户信息
    print("\n📋 测试获取用户信息...")
    user = client.get_user_info()
    if user:
        print(f"✅ 用户: {user.screen_name} ({user.user_id})")
    else:
        print("⚠️  获取用户信息失败（可能需要网络）")

    # 测试原生配置
    print("\n⚙️  测试获取原生配置...")
    config = client.get_native_config("test_mid", "test_did", "test_uid")
    if config:
        print(f"✅ 原生配置获取成功")
    else:
        print("⚠️  原生配置获取失败")

    # 测试 Solo 资格
    print("\n🎯 测试获取 Solo 资格...")
    solo = client.get_solo_qualification()
    if solo:
        print(f"✅ Solo 资格: qualified={solo.qualified}, plan={solo.plan_type}")
    else:
        print("⚠️  Solo 资格获取失败")

    # 检查 Solo 可用性
    print("\n📊 Solo 功能检查:")
    status = client.check_solo_available()
    for key, value in status.items():
        print(f"   {key}: {value}")

    client.close()
    print("\n✅ 测试完成")


if __name__ == "__main__":
    test_client()

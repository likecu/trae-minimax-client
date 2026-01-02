#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trae CN 客户端逆向通信模块

本模块逆向分析了 Trae CN 客户端与云端代理服务器之间的通信协议，
实现了核心的认证、请求管理、AI 交互和 Solo 功能。

主要功能：
1. 统一的请求管理器 (TransportManager)
2. Bearer Token 认证机制
3. AI 聊天和模型管理接口
4. Solo 功能完整支持
5. 用户信息管理
6. IPC 通信支持（通过 ipc_communicator）
7. 请求追踪和性能监控

作者: AI Assistant
日期: 2025-01-02
"""

import os
import sys
import json
import time
import uuid
import hmac
import hashlib
import requests
import sseclient
from typing import Optional, Dict, Any, Generator, Callable, List
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from abc import ABC, abstractmethod
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class RequestType(Enum):
    """请求类型枚举"""
    AGENT = "agent"
    MODEL = "model"
    CHAT = "chat"
    CONFIG = "config"
    USER = "user"
    ICUBE = "icube"
    TRAE = "trae"
    SOLO = "solo"


class ModelProvider(Enum):
    """模型提供商枚举"""
    MINIMAX = "minimax"
    SILICONFLOW = "siliconflow"
    NOVITA = "novita"
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    VOLCENGINE = "volcengine"


@dataclass
class TraeConfig:
    """Trae CN 客户端配置类"""
    base_url: str = "https://api.trae.com.cn"
    token: str = ""
    timeout: int = 60
    max_retries: int = 3
    retry_delay: float = 1.0
    enable_logging: bool = True
    use_ipc: bool = False
    socket_path: str = None


@dataclass
class RequestContext:
    """请求上下文类"""
    request_id: str
    request_type: RequestType
    start_time: float = field(default_factory=time.time)
    cost_ms: int = 0
    status: str = "pending"
    trace_id: str = ""


class TraeAPIError(Exception):
    """Trae CN API 调用异常类"""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        request_id: Optional[str] = None,
        response: Optional[Dict] = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.request_id = request_id
        self.response = response or {}


class SoloQualification:
    """Solo 资格信息类"""

    def __init__(self, data: Dict):
        self.qualified = data.get('qualified', False)
        self.features = data.get('features', [])
        self.max_sessions = data.get('max_sessions', 1)
        self.current_sessions = data.get('current_sessions', 0)
        self.expires_at = data.get('expires_at')
        self.plan_type = data.get('plan_type', 'free')
        self.can_use_solo = data.get('can_use_solo', False)
        self.solo_config = data.get('solo_config', {})

    def __repr__(self):
        return f"<SoloQualification qualified={self.qualified} plan={self.plan_type}>"


class UserProfile:
    """用户资料类"""

    def __init__(self, data: Dict):
        self.user_id = data.get('UserID', data.get('userId', ''))
        self.screen_name = data.get('ScreenName', data.get('screenName', ''))
        self.email = data.get('Email', data.get('email', ''))
        self.avatar_url = data.get('AvatarUrl', data.get('avatarUrl', ''))
        self.region = data.get('Region', data.get('region', 'CN'))
        self.ai_region = data.get('AIRegion', data.get('ai_region', 'CN'))
        self.gender = data.get('Gender', data.get('gender', 0))
        self.description = data.get('Description', data.get('description', ''))
        self.tenant_id = data.get('TenantID', data.get('tenantId', ''))
        self.register_time = data.get('RegisterTime', data.get('registerTime'))
        self.last_login_time = data.get('LastLoginTime', data.get('lastLoginTime'))
        self.last_login_type = data.get('LastLoginType', data.get('lastLoginType', ''))
        self.audit_status = data.get('AuditInfo', {}).get('audit_status', 2)

    def __repr__(self):
        return f"<UserProfile name={self.screen_name} id={self.user_id}>"


class AuthManager:
    """认证管理器类"""

    def __init__(self, config: TraeConfig):
        self.config = config
        self.current_token = config.token
        self.token_expired_at: Optional[datetime] = None
        self.refresh_token: Optional[str] = None
        self._user_info: Optional[Dict] = None
        self._user_profile: Optional[UserProfile] = None

    def get_auth_headers(self) -> Dict[str, str]:
        """获取认证请求头"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Trae-CN/3.3.11"
        }

        if self.current_token:
            headers["Authorization"] = f"Bearer {self.current_token}"
            headers["x-cloudide-token"] = self.current_token

        return headers

    def is_token_valid(self) -> bool:
        """检查当前令牌是否有效"""
        if not self.current_token:
            return False

        if self.token_expired_at:
            now = datetime.now(timezone.utc)
            if now >= self.token_expired_at:
                logger.warning("Token 已过期，需要刷新")
                return False

        return True

    def update_token_info(
        self,
        token: str,
        expired_at: str,
        refresh_token: Optional[str] = None,
        refresh_expired_at: Optional[str] = None
    ) -> None:
        """更新令牌信息"""
        self.current_token = token
        if expired_at:
            self.token_expired_at = datetime.fromisoformat(expired_at.replace('Z', '+00:00'))
        self.refresh_token = refresh_token
        logger.info(f"Token 已更新，将于 {expired_at} 过期")

    def get_user_info(self) -> Optional[Dict]:
        """获取当前用户信息"""
        return self._user_info

    def set_user_info(self, user_info: Dict) -> None:
        """设置用户信息"""
        self._user_info = user_info
        logger.info(f"用户信息已更新: {user_info.get('ScreenName', 'Unknown')}")

    def get_user_profile(self) -> Optional[UserProfile]:
        """获取用户资料对象"""
        return self._user_profile

    def set_user_profile(self, profile_data: Dict) -> None:
        """设置用户资料"""
        self._user_profile = UserProfile(profile_data)
        logger.info(f"用户资料已更新: {self._user_profile.screen_name}")


class TransportManager:
    """传输管理器类"""

    def __init__(self, config: Optional[TraeConfig] = None):
        self.config = config or TraeConfig()
        self.auth_manager = AuthManager(self.config)
        self.session = requests.Session()
        self.request_history: list = []
        self._executor = ThreadPoolExecutor(max_workers=5)

    def execute_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        request_type: RequestType = RequestType.ICUBE,
        stream: bool = False,
        timeout: Optional[int] = None
    ) -> Dict:
        """执行 API 请求"""
        request_id = str(uuid.uuid4())
        context = RequestContext(
            request_id=request_id,
            request_type=request_type
        )

        url = f"{self.config.base_url}{endpoint}"
        headers = self.auth_manager.get_auth_headers()

        timeout = timeout or self.config.timeout

        if self.config.enable_logging:
            logger.info(
                f"[TransportManager] executeRequest, {request_type.value} {endpoint}, {request_id}"
            )

        try:
            start_time = time.time()

            if method.upper() == "GET":
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                    stream=stream
                )
            elif method.upper() == "POST":
                response = self.session.post(
                    url,
                    params=params,
                    json=data,
                    headers=headers,
                    timeout=timeout,
                    stream=stream
                )
            elif method.upper() == "PUT":
                response = self.session.put(
                    url,
                    params=params,
                    json=data,
                    headers=headers,
                    timeout=timeout
                )
            elif method.upper() == "DELETE":
                response = self.session.delete(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout
                )
            else:
                raise ValueError(f"不支持的 HTTP 方法: {method}")

            response.raise_for_status()

            cost_ms = int((time.time() - start_time) * 1000)
            context.cost_ms = cost_ms
            context.status = "success"

            if self.config.enable_logging:
                logger.info(
                    f"[TransportManager] executeRequest success, "
                    f"{request_type.value} {endpoint}, {request_id}, cost: {cost_ms}"
                )

            result = response.json() if not stream else response

            self._record_request(context, result)

            return result

        except requests.exceptions.HTTPError as e:
            context.status = "http_error"
            self._record_request(context, {"error": str(e)})

            error_msg = f"HTTP Error: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            raise TraeAPIError(
                message=error_msg,
                status_code=e.response.status_code,
                request_id=request_id
            )

        except requests.exceptions.Timeout as e:
            context.status = "timeout"
            self._record_request(context, {"error": "Request timeout"})
            raise TraeAPIError(
                message=f"请求超时: {endpoint}",
                request_id=request_id
            )

        except requests.exceptions.RequestException as e:
            context.status = "request_error"
            self._record_request(context, {"error": str(e)})
            raise TraeAPIError(
                message=f"请求失败: {str(e)}",
                request_id=request_id
            )

    def _record_request(self, context: RequestContext, result: Dict) -> None:
        """记录请求信息到历史"""
        self.request_history.append({
            "request_id": context.request_id,
            "request_type": context.request_type.value,
            "status": context.status,
            "cost_ms": context.cost_ms,
            "timestamp": datetime.now().isoformat(),
            "result": result
        })

    def get_request_history(self) -> list:
        """获取请求历史记录"""
        return self.request_history

    def clear_history(self) -> None:
        """清空请求历史记录"""
        self.request_history.clear()
        logger.info("请求历史记录已清空")


class ModelService:
    """模型服务类"""

    def __init__(self, transport: TransportManager):
        self.transport = transport
        self.selected_model: str = "MiniMax-M2.1"
        self.model_list: Optional[list] = None

    def get_model_list(self) -> list:
        """获取可用模型列表"""
        try:
            result = self.transport.execute_request(
                method="POST",
                endpoint="/model/list",
                request_type=RequestType.MODEL
            )
            self.model_list = result.get("models", [])
            return self.model_list
        except TraeAPIError as e:
            logger.error(f"获取模型列表失败: {e}")
            return []

    def get_model_selection_modes(self) -> Dict:
        """获取模型选择模式"""
        try:
            result = self.transport.execute_request(
                method="POST",
                endpoint="/model/selection/modes",
                request_type=RequestType.MODEL
            )
            return result
        except TraeAPIError as e:
            logger.error(f"获取模型选择模式失败: {e}")
            return {}

    def select_model(self, model_name: str) -> bool:
        """选择指定的 AI 模型"""
        if self.model_list:
            model_exists = any(
                m.get("name") == model_name or m.get("id") == model_name
                for m in self.model_list
            )
            if not model_exists:
                logger.warning(f"模型 {model_name} 不在可用模型列表中")
                return False

        self.selected_model = model_name
        logger.info(f"已选择模型: {model_name}")
        return True

    def get_selected_model(self) -> str:
        """获取当前选中的模型名称"""
        return self.selected_model


class SoloService:
    """Solo 功能服务类

    提供 Solo 模式的所有功能，包括：
    - 资格验证
    - 会话管理
    - 模式控制
    """

    def __init__(self, transport: TransportManager):
        self.transport = transport
        self._qualification: Optional[SoloQualification] = None
        self._solo_mode = False
        self._sessions: list = []

    def get_qualification(self) -> Optional[SoloQualification]:
        """
        获取 Solo 资格信息

        Returns:
            SoloQualification: 资格信息对象，如果获取失败返回 None
        """
        try:
            result = self.transport.execute_request(
                method="GET",
                endpoint="/trae/api/v1/trae_solo_qualification",
                request_type=RequestType.SOLO
            )

            # 解析结果
            data = result.get('Result', result)
            self._qualification = SoloQualification(data)

            logger.info(f"Solo 资格: {self._qualification}")
            return self._qualification

        except TraeAPIError as e:
            logger.error(f"获取 Solo 资格失败: {e}")
            return None

    def is_qualified(self) -> bool:
        """检查是否有 Solo 资格"""
        if not self._qualification:
            self.get_qualification()
        return self._qualification.qualified if self._qualification else False

    def can_use_solo(self) -> bool:
        """检查是否可以使用 Solo 模式"""
        if not self._qualification:
            self.get_qualification()
        return self._qualification.can_use_solo if self._qualification else False

    def enable_solo_mode(self) -> bool:
        """
        启用 Solo 模式

        Returns:
            bool: 是否成功启用
        """
        if not self.can_use_solo():
            logger.warning("没有 Solo 资格，无法启用 Solo 模式")
            return False

        try:
            result = self.transport.execute_request(
                method="POST",
                endpoint="/trae/api/v1/trae_solo/enable",
                request_type=RequestType.SOLO
            )

            self._solo_mode = result.get('enabled', True)
            logger.info(f"Solo 模式已启用: {self._solo_mode}")
            return self._solo_mode

        except TraeAPIError as e:
            logger.error(f"启用 Solo 模式失败: {e}")
            return False

    def disable_solo_mode(self) -> bool:
        """
        禁用 Solo 模式

        Returns:
            bool: 是否成功禁用
        """
        try:
            result = self.transport.execute_request(
                method="POST",
                endpoint="/trae/api/v1/trae_solo/disable",
                request_type=RequestType.SOLO
            )

            self._solo_mode = False
            logger.info("Solo 模式已禁用")
            return True

        except TraeAPIError as e:
            logger.error(f"禁用 Solo 模式失败: {e}")
            return False

    def get_sessions(self) -> list:
        """
        获取 Solo 会话列表

        Returns:
            list: 会话列表
        """
        try:
            result = self.transport.execute_request(
                method="GET",
                endpoint="/trae/api/v1/trae_solo/sessions",
                request_type=RequestType.SOLO
            )

            self._sessions = result.get('sessions', [])
            return self._sessions

        except TraeAPIError as e:
            logger.error(f"获取 Solo 会话失败: {e}")
            return []

    def create_session(self, name: str = None) -> Optional[Dict]:
        """
        创建新的 Solo 会话

        Args:
            name: 会话名称

        Returns:
            Dict: 创建的会话信息
        """
        try:
            result = self.transport.execute_request(
                method="POST",
                endpoint="/trae/api/v1/trae_solo/sessions",
                data={"name": name} if name else {},
                request_type=RequestType.SOLO
            )

            session = result.get('session', {})
            self._sessions.append(session)
            logger.info(f"创建 Solo 会话成功: {session.get('id')}")
            return session

        except TraeAPIError as e:
            logger.error(f"创建 Solo 会话失败: {e}")
            return None

    def end_session(self, session_id: str) -> bool:
        """
        结束 Solo 会话

        Args:
            session_id: 会话 ID

        Returns:
            bool: 是否成功结束
        """
        try:
            result = self.transport.execute_request(
                method="DELETE",
                endpoint=f"/trae/api/v1/trae_solo/sessions/{session_id}",
                request_type=RequestType.SOLO
            )

            # 从会话列表中移除
            self._sessions = [s for s in self._sessions if s.get('id') != session_id]
            logger.info(f"结束 Solo 会话: {session_id}")
            return True

        except TraeAPIError as e:
            logger.error(f"结束 Solo 会话失败: {e}")
            return False

    def get_solo_status(self) -> Dict:
        """
        获取 Solo 状态信息

        Returns:
            Dict: 状态信息
        """
        return {
            "qualified": self.is_qualified(),
            "can_use": self.can_use_solo(),
            "mode_enabled": self._solo_mode,
            "sessions_count": len(self._sessions),
            "qualification": self._qualification.__dict__ if self._qualification else None
        }


class ICubeService:
    """iCube 服务类"""

    def __init__(self, transport: TransportManager):
        self.transport = transport
        self._cached_config: Optional[Dict] = None

    def get_native_config(
        self,
        mid: str,
        did: str,
        uid: str,
        user_region: str = "CN",
        package_type: str = "stable_cn",
        platform: str = "Mac",
        arch: str = "arm64",
        app_version: str = "3.3.11",
        build_version: str = "1.0.27213"
    ) -> Dict:
        """获取原生配置信息"""
        params = {
            "mid": mid,
            "did": did,
            "uid": uid,
            "userRegion": user_region,
            "packageType": package_type,
            "platform": platform,
            "arch": arch,
            "tenant": "marscode",
            "appVersion": app_version,
            "buildVersion": build_version,
            "traeVersionCode": "20250325"
        }

        result = self.transport.execute_request(
            method="GET",
            endpoint="/icube/api/v1/native/config/query",
            params=params,
            request_type=RequestType.ICUBE
        )

        self._cached_config = result
        return result

    def get_release_notes(
        self,
        version: str = "3.3.11",
        pkg: str = "stable_cn",
        language: str = "zh-cn",
        platform: str = "Mac",
        arch: str = "arm64"
    ) -> Dict:
        """获取发布说明"""
        params = {
            "v": version,
            "pkg": pkg,
            "language": language,
            "platform": platform,
            "arch": arch
        }

        return self.transport.execute_request(
            method="GET",
            endpoint="/icube/api/v1/release/note",
            params=params,
            request_type=RequestType.ICUBE
        )

    def get_user_info(self) -> Dict:
        """获取当前用户信息（从云端）"""
        result = self.transport.execute_request(
            method="GET",
            endpoint="/cloudide/api/v3/trae/GetUserInfo",
            request_type=RequestType.USER
        )

        if "Result" in result:
            self.transport.auth_manager.set_user_info(result["Result"])
            return result["Result"]

        return result

    def get_user_profile(self) -> Optional[UserProfile]:
        """获取完整用户资料"""
        result = self.get_user_info()
        if result:
            profile = UserProfile(result)
            self.transport.auth_manager.set_user_profile(result)
            return profile
        return None

    def get_user_data(self) -> Dict:
        """获取用户数据"""
        try:
            result = self.transport.execute_request(
                method="GET",
                endpoint="/icube/api/v1/user",
                request_type=RequestType.USER
            )
            return result
        except TraeAPIError as e:
            logger.error(f"获取用户数据失败: {e}")
            return {}

    def get_control_url(self) -> str:
        """获取控制 URL"""
        try:
            result = self.transport.execute_request(
                method="GET",
                endpoint="/icube/api/v1/control-url/latest",
                request_type=RequestType.ICUBE
            )
            return result.get('url', result.get('control_url', ''))
        except TraeAPIError as e:
            logger.error(f"获取控制 URL 失败: {e}")
            return ""

    def get_agent_list(self) -> list:
        """获取可用代理列表"""
        result = self.transport.execute_request(
            method="POST",
            endpoint="/agent/list",
            request_type=RequestType.AGENT
        )

        return result.get("agents", [])

    def check_update(
        self,
        mid: str,
        did: str,
        uid: str,
        pid: str = "7409949320595642651",
        branch: str = "release_desktop_yoma_cn"
    ) -> Dict:
        """检查应用更新"""
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
            "traeVersionCode": "20250325",
            "pid": pid,
            "branch": branch
        }

        return self.transport.execute_request(
            method="GET",
            endpoint="/icube/api/v1/package/check_update",
            params=params,
            request_type=RequestType.ICUBE
        )


class ChatService:
    """聊天服务类"""

    def __init__(self, transport: TransportManager):
        self.transport = transport
        self.current_session_id: Optional[str] = None
        self.message_history: list = []
        self._stream_callbacks: list = []

    def send_message(
        self,
        message: str,
        session_id: Optional[str] = None,
        model: str = "MiniMax-M2.1",
        stream: bool = True,
        context: Optional[Dict] = None
    ) -> Dict:
        """发送聊天消息"""
        payload = {
            "message": message,
            "model": model,
            "stream": stream,
            "sessionId": session_id or self.current_session_id,
            "context": context or {}
        }

        if self.message_history:
            payload["history"] = self.message_history[-10:]

        result = self.transport.execute_request(
            method="POST",
            endpoint="/chat/completions",
            data=payload,
            request_type=RequestType.CHAT,
            stream=stream
        )

        self.message_history.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat()
        })

        if "response" in result:
            self.message_history.append({
                "role": "assistant",
                "content": result["response"],
                "timestamp": datetime.now().isoformat()
            })

        return result

    def send_message_stream(
        self,
        message: str,
        session_id: Optional[str] = None,
        model: str = "MiniMax-M2.1",
        context: Optional[Dict] = None
    ) -> Generator[Dict, None, None]:
        """发送聊天消息并接收流式响应"""
        payload = {
            "message": message,
            "model": model,
            "stream": True,
            "sessionId": session_id or self.current_session_id,
            "context": context or {}
        }

        if self.message_history:
            payload["history"] = self.message_history[-10:]

        response = self.transport.execute_request(
            method="POST",
            endpoint="/chat/completions",
            data=payload,
            request_type=RequestType.CHAT,
            stream=True
        )

        if hasattr(response, 'iter_lines'):
            client = sseclient.SSEClient(response)
            for event in client:
                if event.data:
                    try:
                        data = json.loads(event.data)
                        yield data

                        for callback in self._stream_callbacks:
                            callback(data)
                    except json.JSONDecodeError:
                        pass

    def register_stream_callback(self, callback: Callable[[Dict], None]) -> None:
        """注册流式响应回调函数"""
        self._stream_callbacks.append(callback)

    def clear_history(self) -> None:
        """清空消息历史记录"""
        self.message_history.clear()
        logger.info("消息历史记录已清空")

    def get_history(self) -> list:
        """获取消息历史记录"""
        return self.message_history

    def get_sessions(self) -> list:
        """获取聊天会话列表"""
        try:
            result = self.transport.execute_request(
                method="GET",
                endpoint="/chat/sessions",
                request_type=RequestType.CHAT
            )
            return result.get('sessions', [])
        except TraeAPIError as e:
            logger.error(f"获取聊天会话列表失败: {e}")
            return []

    def get_messages(self, session_id: str) -> list:
        """获取指定会话的消息"""
        try:
            result = self.transport.execute_request(
                method="GET",
                endpoint=f"/chat/sessions/{session_id}/messages",
                request_type=RequestType.CHAT
            )
            return result.get('messages', [])
        except TraeAPIError as e:
            logger.error(f"获取消息失败: {e}")
            return []


class TraeClient:
    """Trae CN 客户端主类"""

    def __init__(
        self,
        token: Optional[str] = None,
        config: Optional[TraeConfig] = None,
        use_ipc: bool = False
    ):
        """
        初始化 Trae CN 客户端

        Args:
            token: 认证令牌
            config: TraeConfig 配置对象
            use_ipc: 是否使用 IPC 通信
        """
        if token:
            os.environ["TRAE_TOKEN"] = token

        self.config = config or TraeConfig()
        self.config.token = self.config.token or os.environ.get("TRAE_TOKEN", "")
        self.config.use_ipc = use_ipc

        self.transport = TransportManager(self.config)
        self.auth = self.transport.auth_manager
        self.models = ModelService(self.transport)
        self.icube = ICubeService(self.transport)
        self.chat = ChatService(self.transport)
        self.solo = SoloService(self.transport)

        self.ipc_communicator = None
        if use_ipc:
            self._init_ipc()

    def _init_ipc(self):
        """初始化 IPC 通信"""
        try:
            from ipc_communicator import IPCCommunicator

            self.ipc_communicator = IPCCommunicator(
                socket_path=self.config.socket_path,
                auto_connect=True
            )

            if self.ipc_communicator.is_connected():
                logger.info("IPC 通信已初始化")
            else:
                logger.warning("IPC 连接失败，将仅使用 REST API")
                self.ipc_communicator = None

        except ImportError:
            logger.warning("ipc_communicator 模块未找到，将仅使用 REST API")
        except Exception as e:
            logger.warning(f"IPC 初始化失败: {e}")
            self.ipc_communicator = None

    def authenticate(self, username: str, password: str) -> bool:
        """用户认证"""
        try:
            result = self.transport.execute_request(
                method="POST",
                endpoint="/auth/login",
                data={
                    "username": username,
                    "password": password
                },
                request_type=RequestType.USER
            )

            if "token" in result:
                self.auth.update_token_info(
                    token=result["token"],
                    expired_at=result.get("expiredAt", ""),
                    refresh_token=result.get("refreshToken")
                )
                self.config.token = result["token"]
                return True

            return False

        except TraeAPIError:
            return False

    def refresh_token(self) -> bool:
        """刷新认证令牌"""
        if not self.auth.refresh_token:
            logger.warning("没有刷新令牌可用")
            return False

        try:
            result = self.transport.execute_request(
                method="POST",
                endpoint="/auth/refresh",
                data={"refreshToken": self.auth.refresh_token},
                request_type=RequestType.USER
            )

            if "token" in result:
                self.auth.update_token_info(
                    token=result["token"],
                    expired_at=result.get("expiredAt", ""),
                    refresh_token=result.get("refreshToken")
                )
                self.config.token = result["token"]
                return True

            return False

        except TraeAPIError:
            return False

    def chat_with_minimax(
        self,
        message: str,
        session_id: Optional[str] = None,
        stream: bool = True
    ) -> Dict:
        """使用 MiniMax-M2.1 模型进行聊天"""
        model = self.models.get_selected_model()
        return self.chat.send_message(
            message=message,
            session_id=session_id,
            model=model,
            stream=stream
        )

    def get_user_info(self) -> Optional[UserProfile]:
        """获取当前用户资料"""
        return self.icube.get_user_profile()

    def get_solo_qualification(self) -> Optional[SoloQualification]:
        """获取 Solo 资格"""
        return self.solo.get_qualification()

    def check_solo_available(self) -> Dict:
        """检查 Solo 功能可用性"""
        qualification = self.get_solo_qualification()
        return {
            "available": self.solo.can_use_solo(),
            "qualified": self.solo.is_qualified(),
            "qualification": qualification.__dict__ if qualification else None
        }

    def start_solo_session(self, name: str = None) -> Optional[Dict]:
        """开始 Solo 会话"""
        if not self.solo.can_use_solo():
            logger.warning("没有 Solo 资格，无法开始会话")
            return None

        # 启用 Solo 模式
        self.solo.enable_solo_mode()

        # 创建会话
        return self.solo.create_session(name)

    def end_solo_session(self, session_id: str) -> bool:
        """结束 Solo 会话"""
        return self.solo.end_session(session_id)

    def get_performance_report(self) -> Dict:
        """获取性能报告"""
        history = self.transport.get_request_history()

        if not history:
            return {"total_requests": 0, "avg_cost_ms": 0, "success_rate": 0}

        total_requests = len(history)
        successful_requests = sum(1 for r in history if r["status"] == "success")
        total_cost = sum(r["cost_ms"] for r in history)

        return {
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "failed_requests": total_requests - successful_requests,
            "success_rate": successful_requests / total_requests * 100,
            "avg_cost_ms": total_cost / total_requests,
            "request_history": history[-20:]
        }

    def close(self):
        """关闭客户端连接"""
        if self.ipc_communicator:
            self.ipc_communicator.disconnect()
            self.ipc_communicator = None
        logger.info("客户端已关闭")


def create_client(token: str = None, use_ipc: bool = False) -> TraeClient:
    """创建 Trae CN 客户端的便捷函数"""
    return TraeClient(token=token, use_ipc=use_ipc)


def get_token_from_storage(storage_path: str = None) -> Optional[str]:
    """从 Trae CN 存储中提取 Token"""
    if storage_path is None:
        storage_path = os.path.expanduser(
            "~/Library/Application Support/Trae CN/User/globalStorage/storage.json"
    )

    try:
        with open(storage_path, 'r') as f:
            data = json.load(f)

        # 查找 iCubeAuthInfo
        auth_key = None
        for key in data:
            if 'iCubeAuthInfo' in key and 'cloudide' in key:
                auth_key = key
                break

        if not auth_key:
            logger.error("未找到认证信息")
            return None

        auth_data = json.loads(data[auth_key])
        token = auth_data.get('token')

        if token:
            logger.info(f"成功从 {storage_path} 提取 Token")
            return token

    except Exception as e:
        logger.error(f"提取 Token 失败: {e}")

    return None


if __name__ == "__main__":
    print("Trae CN 客户端逆向通信模块")
    print("=" * 50)
    print()
    print("使用方法:")
    print("  1. 设置环境变量: export TRAE_TOKEN='your_token'")
    print("  2. 或从存储提取: token = get_token_from_storage()")
    print("  3. 导入模块: from trae_client import TraeClient, create_client")
    print("  4. 创建客户端: client = create_client('your_token')")
    print("  5. 调用 API: response = client.chat.send_message('你好')")
    print()
    print("可用服务:")
    print("  - client.transport: 传输管理器")
    print("  - client.auth: 认证管理器")
    print("  - client.models: 模型服务")
    print("  - client.icube: iCube 服务（用户信息、配置）")
    print("  - client.chat: 聊天服务")
    print("  - client.solo: Solo 功能（新增！）")
    print()
    print("Solo 功能示例:")
    print("  - client.get_solo_qualification()  # 获取 Solo 资格")
    print("  - client.check_solo_available()    # 检查是否可用")
    print("  - client.start_solo_session()      # 开始 Solo 会话")
    print("  - client.end_solo_session(id)      # 结束会话")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trae CN 客户端逆向通信模块

本模块逆向分析了 Trae CN 客户端与云端代理服务器之间的通信协议，
实现了核心的认证、请求管理和 AI 交互功能。

主要功能：
1. 统一的请求管理器 (TransportManager)
2. Bearer Token 认证机制
3. AI 聊天和模型管理接口
4. 配置和用户信息查询
5. 请求追踪和性能监控

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
from typing import Optional, Dict, Any, Generator, Callable
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
    """
    请求类型枚举
    
    定义了 Trae CN 客户端与云端交互的所有请求类型
    """
    AGENT = "agent"
    MODEL = "model"
    CHAT = "chat"
    CONFIG = "config"
    USER = "user"
    ICUBE = "icube"
    TRAE = "trae"


class ModelProvider(Enum):
    """
    模型提供商枚举
    
    支持的 AI 模型提供商列表
    """
    MINIMAX = "minimax"
    SILICONFLOW = "siliconflow"
    NOVITA = "novita"
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    VOLCENGINE = "volcengine"


@dataclass
class TraeConfig:
    """
    Trae CN 客户端配置类
    
    Attributes:
        base_url: API 基础 URL 地址
        token: 认证令牌
        timeout: 请求超时时间（秒）
        max_retries: 最大重试次数
        retry_delay: 重试延迟时间（秒）
        enable_logging: 是否启用请求日志
    """
    base_url: str = "https://api.trae.com.cn"
    token: str = ""
    timeout: int = 60
    max_retries: int = 3
    retry_delay: float = 1.0
    enable_logging: bool = True


@dataclass
class RequestContext:
    """
    请求上下文类
    
    用于追踪和管理单个请求的上下文信息
    
    Attributes:
        request_id: 唯一请求标识符
        request_type: 请求类型
        start_time: 请求开始时间戳
        cost_ms: 请求耗时（毫秒）
        status: 请求状态
        trace_id: 追踪 ID
    """
    request_id: str
    request_type: RequestType
    start_time: float = field(default_factory=time.time)
    cost_ms: int = 0
    status: str = "pending"
    trace_id: str = ""


class TraeAPIError(Exception):
    """
    Trae CN API 调用异常类
    
    Attributes:
        status_code: HTTP 状态码
        error_code: API 错误码
        message: 错误描述信息
        request_id: 关联的请求 ID
        response: 原始响应数据
    """
    
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


class AuthManager:
    """
    认证管理器类
    
    负责管理 Trae CN 客户端的认证流程，包括：
    - Token 获取和刷新
    - 认证状态追踪
    - 请求签名生成
    
    Attributes:
        config: TraeConfig 配置对象
        current_token: 当前有效的认证令牌
        token_expired_at: 令牌过期时间
        refresh_token: 刷新令牌
    """
    
    def __init__(self, config: TraeConfig):
        """
        初始化认证管理器
        
        Args:
            config: TraeConfig 配置对象，包含认证所需的配置信息
        """
        self.config = config
        self.current_token = config.token
        self.token_expired_at: Optional[datetime] = None
        self.refresh_token: Optional[str] = None
        self._user_info: Optional[Dict] = None
    
    def get_auth_headers(self) -> Dict[str, str]:
        """
        获取认证请求头
        
        Returns:
            Dict[str, str]: 包含认证信息的请求头字典
                - Authorization: Bearer 令牌认证头
                - x-cloudide-token: CloudIDE 特定令牌
                - Content-Type: 内容类型
        """
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Trae-CN/3.3.16"
        }
        
        if self.current_token:
            headers["Authorization"] = f"Bearer {self.current_token}"
            headers["x-cloudide-token"] = self.current_token
        
        return headers
    
    def is_token_valid(self) -> bool:
        """
        检查当前令牌是否有效
        
        Returns:
            bool: 令牌有效返回 True，否则返回 False
        """
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
        """
        更新令牌信息
        
        Args:
            token: 新获取的访问令牌
            expired_at: 令牌过期时间（ISO 格式字符串）
            refresh_token: 刷新令牌
            refresh_expired_at: 刷新令牌过期时间
        """
        self.current_token = token
        self.token_expired_at = datetime.fromisoformat(expired_at.replace('Z', '+00:00'))
        self.refresh_token = refresh_token
        logger.info(f"Token 已更新，将于 {expired_at} 过期")
    
    def get_user_info(self) -> Optional[Dict]:
        """
        获取当前用户信息
        
        Returns:
            Optional[Dict]: 用户信息字典，包含以下字段：
                - userId: 用户 ID
                - screenName: 用户显示名称
                - email: 邮箱（脱敏）
                - avatarUrl: 头像 URL
                - region: 地区信息
        """
        return self._user_info
    
    def set_user_info(self, user_info: Dict) -> None:
        """
        设置用户信息
        
        Args:
            user_info: 用户信息字典
        """
        self._user_info = user_info
        logger.info(f"用户信息已更新: {user_info.get('ScreenName', 'Unknown')}")


class TransportManager:
    """
    传输管理器类
    
    Trae CN 核心通信组件，负责：
    - 统一管理所有 API 请求
    - 请求追踪和性能监控
    - 错误处理和重试机制
    - 请求日志记录
    
    Attributes:
        config: TraeConfig 配置对象
        auth_manager: AuthManager 认证管理器实例
        session: requests 会话对象
        request_history: 请求历史记录
    """
    
    def __init__(self, config: Optional[TraeConfig] = None):
        """
        初始化传输管理器
        
        Args:
            config: TraeConfig 配置对象，如果未提供则使用默认配置
        """
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
        """
        执行 API 请求
        
        这是 TransportManager 的核心方法，处理所有 API 通信
        
        Args:
            method: HTTP 方法（GET, POST, PUT, DELETE）
            endpoint: API 端点路径
            params: URL 查询参数
            data: 请求体数据
            request_type: 请求类型枚举
            stream: 是否使用流式响应
            timeout: 请求超时时间（秒）
        
        Returns:
            Dict: API 响应数据
        
        Raises:
            TraeAPIError: 当 API 调用失败时抛出
        """
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
        """
        记录请求信息到历史
        
        Args:
            context: RequestContext 请求上下文
            result: 响应结果
        """
        self.request_history.append({
            "request_id": context.request_id,
            "request_type": context.request_type.value,
            "status": context.status,
            "cost_ms": context.cost_ms,
            "timestamp": datetime.now().isoformat(),
            "result": result
        })
    
    def get_request_history(self) -> list:
        """
        获取请求历史记录
        
        Returns:
            list: 所有请求的历史记录列表
        """
        return self.request_history
    
    def clear_history(self) -> None:
        """
        清空请求历史记录
        """
        self.request_history.clear()
        logger.info("请求历史记录已清空")


class ModelService:
    """
    模型服务类
    
    负责管理 AI 模型的获取、选择和配置
    
    Attributes:
        transport: TransportManager 传输管理器实例
        selected_model: 当前选中的模型名称
        model_list: 可用模型列表缓存
    """
    
    def __init__(self, transport: TransportManager):
        """
        初始化模型服务
        
        Args:
            transport: TransportManager 传输管理器实例
        """
        self.transport = transport
        self.selected_model: str = "MiniMax-M2.1"
        self.model_list: Optional[list] = None
    
    def get_model_list(self) -> list:
        """
        获取可用模型列表
        
        Returns:
            list: 可用模型配置列表
        """
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
        """
        获取模型选择模式
        
        Returns:
            Dict: 模型选择模式配置
        """
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
        """
        选择指定的 AI 模型
        
        Args:
            model_name: 模型名称，如 "MiniMax-M2.1"
        
        Returns:
            bool: 选择成功返回 True，否则返回 False
        """
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
        """
        获取当前选中的模型名称
        
        Returns:
            str: 当前模型名称
        """
        return self.selected_model


class ICubeService:
    """
    iCube 服务类
    
    提供 Trae CN 核心功能的 API 接口，包括：
    - 配置查询
    - 发布说明获取
    - 用户信息管理
    - 代理列表管理
    
    Attributes:
        transport: TransportManager 传输管理器实例
    """
    
    def __init__(self, transport: TransportManager):
        """
        初始化 iCube 服务
        
        Args:
            transport: TransportManager 传输管理器实例
        """
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
        app_version: str = "3.3.16",
        build_version: str = "1.0.27484"
    ) -> Dict:
        """
        获取原生配置信息
        
        Args:
            mid: 机器标识符
            did: 设备标识符
            uid: 用户标识符
            user_region: 用户地区
            package_type: 包类型
            platform: 平台
            arch: 架构
            app_version: 应用版本
            build_version: 构建版本
        
        Returns:
            Dict: 原生配置信息
        """
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
        version: str = "3.3.16",
        pkg: str = "stable_cn",
        language: str = "zh-cn",
        platform: str = "Mac",
        arch: str = "arm64"
    ) -> Dict:
        """
        获取发布说明
        
        Args:
            version: 应用版本
            pkg: 包类型
            language: 语言
            platform: 平台
            arch: 架构
        
        Returns:
            Dict: 发布说明信息
        """
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
        """
        获取当前用户信息
        
        Returns:
            Dict: 用户信息，包含以下字段：
                - ScreenName: 显示名称
                - UserID: 用户 ID
                - Email: 邮箱
                - AvatarUrl: 头像 URL
                - Region: 地区
        """
        result = self.transport.execute_request(
            method="GET",
            endpoint="/cloudide/api/v3/trae/GetUserInfo",
            request_type=RequestType.USER
        )
        
        if "Result" in result:
            self.transport.auth_manager.set_user_info(result["Result"])
            return result["Result"]
        
        return result
    
    def get_agent_list(self) -> list:
        """
        获取可用代理列表
        
        Returns:
            list: 代理配置列表
        """
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
        """
        检查应用更新
        
        Args:
            mid: 机器标识符
            did: 设备标识符
            uid: 用户标识符
            pid: 产品 ID
            branch: 分支名称
        
        Returns:
            Dict: 更新检查结果
        """
        params = {
            "mid": mid,
            "did": did,
            "uid": uid,
            "userRegion": "CN",
            "packageType": "stable_cn",
            "platform": "Mac",
            "arch": "arm64",
            "tenant": "marscode",
            "appVersion": "3.3.16",
            "buildVersion": "1.0.27484",
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
    """
    聊天服务类
    
    负责 AI 聊天的核心功能，包括：
    - 消息发送和接收
    - 流式响应处理
    - 会话管理
    - 上下文追踪
    
    Attributes:
        transport: TransportManager 传输管理器实例
        current_session_id: 当前会话 ID
        message_history: 消息历史记录
    """
    
    def __init__(self, transport: TransportManager):
        """
        初始化聊天服务
        
        Args:
            transport: TransportManager 传输管理器实例
        """
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
        """
        发送聊天消息
        
        Args:
            message: 用户消息内容
            session_id: 会话 ID
            model: 使用的模型名称
            stream: 是否使用流式响应
            context: 附加上下文信息
        
        Returns:
            Dict: 聊天响应结果
        """
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
        """
        发送聊天消息并接收流式响应
        
        Args:
            message: 用户消息内容
            session_id: 会话 ID
            model: 使用的模型名称
            context: 附加上下文信息
        
        Yields:
            Dict: 流式响应数据块
        """
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
        """
        注册流式响应回调函数
        
        Args:
            callback: 回调函数，接收响应数据块
        """
        self._stream_callbacks.append(callback)
    
    def clear_history(self) -> None:
        """
        清空消息历史记录
        """
        self.message_history.clear()
        logger.info("消息历史记录已清空")
    
    def get_history(self) -> list:
        """
        获取消息历史记录
        
        Returns:
            list: 消息历史列表
        """
        return self.message_history


class TraeClient:
    """
    Trae CN 客户端主类
    
    整合所有服务，提供统一的客户端接口
    
    Attributes:
        config: TraeConfig 配置对象
        transport: TransportManager 传输管理器
        auth: AuthManager 认证管理器
        models: ModelService 模型服务
        icube: ICubeService iCube 服务
        chat: ChatService 聊天服务
    """
    
    def __init__(self, token: Optional[str] = None, config: Optional[TraeConfig] = None):
        """
        初始化 Trae CN 客户端
        
        Args:
            token: 认证令牌，如果未提供则尝试从环境变量读取
            config: TraeConfig 配置对象
        """
        if token:
            os.environ["TRAE_TOKEN"] = token
        
        self.config = config or TraeConfig()
        self.config.token = self.config.token or os.environ.get("TRAE_TOKEN", "")
        
        self.transport = TransportManager(self.config)
        self.auth = self.transport.auth_manager
        self.models = ModelService(self.transport)
        self.icube = ICubeService(self.transport)
        self.chat = ChatService(self.transport)
    
    def authenticate(self, username: str, password: str) -> bool:
        """
        用户认证
        
        Args:
            username: 用户名
            password: 密码
        
        Returns:
            bool: 认证成功返回 True，否则返回 False
        """
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
        """
        刷新认证令牌
        
        Returns:
            bool: 刷新成功返回 True，否则返回 False
        """
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
        """
        使用 MiniMax-M2.1 模型进行聊天
        
        Args:
            message: 用户消息
            session_id: 会话 ID
            stream: 是否使用流式响应
        
        Returns:
            Dict: 聊天响应结果
        """
        model = self.models.get_selected_model()
        return self.chat.send_message(
            message=message,
            session_id=session_id,
            model=model,
            stream=stream
        )
    
    def get_performance_report(self) -> Dict:
        """
        获取性能报告
        
        Returns:
            Dict: 性能报告，包含请求统计信息
        """
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


def create_client(token: str = None) -> TraeClient:
    """
    创建 Trae CN 客户端的便捷函数
    
    Args:
        token: 认证令牌
    
    Returns:
        TraeClient: 配置好的客户端实例
    """
    return TraeClient(token=token)


if __name__ == "__main__":
    print("Trae CN 客户端逆向通信模块")
    print("=" * 50)
    print("使用方法:")
    print("  1. 设置环境变量: export TRAE_TOKEN='your_token'")
    print("  2. 导入模块: from trae_client import TraeClient, create_client")
    print("  3. 创建客户端: client = create_client('your_token')")
    print("  4. 调用 API: response = client.chat.send_message('你好')")
    print()
    print("可用服务:")
    print("  - client.transport: 传输管理器")
    print("  - client.auth: 认证管理器")
    print("  - client.models: 模型服务")
    print("  - client.icube: iCube 服务")
    print("  - client.chat: 聊天服务")

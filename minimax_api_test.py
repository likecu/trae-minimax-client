#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MiniMax-M2.1 API 测试脚本
用于测试和验证MiniMax官方开放平台的API访问

使用方法：
1. 获取API Key: https://platform.minimaxi.com/user-center/basic-information
2. 设置环境变量: export MINIMAX_API_KEY="your_api_key"
3. 运行脚本: python3 minimax_api_test.py

作者: AI Assistant
日期: 2025-01-02
"""

import os
import sys
import json
import time
import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class MiniMaxConfig:
    """
    MiniMax API配置类
    
    Attributes:
        api_key: MiniMax开放平台API密钥
        base_url: API基础URL地址
        model: 使用的模型名称
        timeout: 请求超时时间（秒）
    """
    api_key: str
    base_url: str = "https://api.minimax.chat/v1"
    model: str = "MiniMax-M2.1"
    timeout: int = 60


class MiniMaxAPIError(Exception):
    """
    MiniMax API调用异常类
    
    Attributes:
        status_code: HTTP状态码
        error_code: API错误码
        message: 错误描述信息
    """
    
    def __init__(self, status_code: int, error_code: str, message: str):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        super().__init__(f"API Error [{status_code}][{error_code}]: {message}")


class MiniMaxClient:
    """
    MiniMax API客户端类
    
    用于与MiniMax开放平台进行交互，支持文本生成等操作
    
    Attributes:
        config: MiniMaxConfig配置对象
        session: requests会话对象
    
    Examples:
        >>> client = MiniMaxClient(api_key="your_api_key")
        >>> response = client.generate_text("你好，请介绍一下你自己")
        >>> print(response.text)
    """
    
    def __init__(self, api_key: Optional[str] = None, config: Optional[MiniMaxConfig] = None):
        """
        初始化MiniMax API客户端
        
        Args:
            api_key: API密钥，如果未提供则从环境变量MINIMAX_API_KEY读取
            config: MiniMaxConfig配置对象，如果提供则忽略api_key参数
        
        Raises:
            ValueError: 当未提供api_key且环境变量中也不存在时
        """
        if config is not None:
            self.config = config
        else:
            if api_key is None:
                api_key = os.environ.get("MINIMAX_API_KEY")
                if api_key is None:
                    raise ValueError(
                        "API key not provided. Please set MINIMAX_API_KEY environment variable "
                        "or pass api_key parameter."
                    )
            self.config = MiniMaxConfig(api_key=api_key)
        
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "MiniMax-Python-SDK/1.0"
        })
    
    def _make_request(
        self, 
        endpoint: str, 
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        发送API请求的内部方法
        
        Args:
            endpoint: API端点路径
            method: HTTP请求方法（GET/POST）
            data: 请求数据字典
        
        Returns:
            Dict: API响应数据
        
        Raises:
            MiniMaxAPIError: 当API调用失败时
            requests.RequestException: 当网络请求失败时
        """
        url = f"{self.config.base_url}{endpoint}"
        
        try:
            if method.upper() == "GET":
                response = self.session.get(url, timeout=self.config.timeout)
            else:
                response = self.session.post(
                    url, 
                    json=data, 
                    timeout=self.config.timeout
                )
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            error_info = {}
            try:
                error_info = response.json()
            except (json.JSONDecodeError, AttributeError):
                error_info = {"message": str(e)}
            
            raise MiniMaxAPIError(
                status_code=response.status_code,
                error_code=error_info.get("error_code", "UNKNOWN"),
                message=error_info.get("message", str(e))
            )
    
    def list_models(self) -> Dict[str, Any]:
        """
        获取可用的模型列表
        
        Returns:
            Dict: 模型列表响应数据
        """
        return self._make_request("/models", "GET")
    
    def generate_text(
        self,
        prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stream: bool = False,
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成文本（同步调用）
        
        Args:
            prompt: 用户输入的提示词
            max_tokens: 最大生成token数量
            temperature: 温度参数（0-1），越高越有创造性
            stream: 是否使用流式响应
            system_prompt: 系统提示词
        
        Returns:
            Dict: 生成的文本响应
        
        Examples:
            >>> client = MiniMaxClient()
            >>> result = client.generate_text("用Python写一个快速排序算法")
            >>> print(result["choices"][0]["message"]["content"])
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        data = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream
        }
        
        return self._make_request("/text/generate", "POST", data)
    
    def chat_completion(
        self,
        messages: list,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        聊天补全接口（OpenAI兼容格式）
        
        Args:
            messages: 消息列表，每条消息包含role和content
            max_tokens: 最大生成token数量
            temperature: 温度参数
            stream: 是否使用流式响应
        
        Returns:
            Dict: 聊天补全响应
        
        Examples:
            >>> messages = [
            ...     {"role": "system", "content": "你是一个编程助手"},
            ...     {"role": "user", "content": "写一个Python函数计算斐波那契数列"}
            ... ]
            >>> response = client.chat_completion(messages)
        """
        data = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream
        }
        
        return self._make_request("/chat/completions", "POST", data)


def test_api_connection():
    """
    测试API连接和基本功能
    
    Returns:
        bool: 测试是否成功
    """
    print("=" * 60)
    print("MiniMax API 连接测试")
    print("=" * 60)
    
    try:
        client = MiniMaxClient()
        
        # 测试1: 列出可用模型
        print("\n[测试1] 获取模型列表...")
        models_response = client.list_models()
        print(f"✓ 模型列表获取成功")
        print(f"  可用模型: {json.dumps(models_response, ensure_ascii=False, indent=2)}")
        
        # 测试2: 文本生成测试
        print("\n[测试2] 文本生成测试...")
        test_prompt = "请用一句话介绍你自己。"
        response = client.generate_text(test_prompt, max_tokens=100)
        
        if response.get("choices") and len(response["choices"]) > 0:
            generated_text = response["choices"][0]["message"]["content"]
            print(f"✓ 文本生成成功")
            print(f"  输入: {test_prompt}")
            print(f"  输出: {generated_text}")
        else:
            print(f"✗ 响应格式异常: {json.dumps(response, ensure_ascii=False, indent=2)}")
            return False
        
        return True
        
    except ValueError as e:
        print(f"✗ 配置错误: {e}")
        print("\n请设置环境变量: export MINIMAX_API_KEY='your_api_key'")
        print("或直接在代码中传入api_key参数")
        return False
    except MiniMaxAPIError as e:
        print(f"✗ API调用失败: {e}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"✗ 网络请求失败: {e}")
        return False
    except Exception as e:
        print(f"✗ 未知错误: {e}")
        return False


def test_with_custom_model():
    """
    测试使用特定模型
    
    Args:
        model_name: 要测试的模型名称
    """
    print("\n" + "=" * 60)
    print("MiniMax-M2.1 专项测试")
    print("=" * 60)
    
    try:
        # 使用MiniMax-M2.1模型
        config = MiniMaxConfig(
            api_key=os.environ.get("MINIMAX_API_KEY", ""),
            model="MiniMax-M2.1"
        )
        client = MiniMaxClient(config=config)
        
        print(f"\n使用模型: {config.model}")
        
        # 代码生成测试
        code_prompt = """请用Python写一个简单的HTTP服务器，
要求：
1. 使用Flask框架
2. 提供一个GET接口 /hello
3. 返回JSON格式的问候信息
4. 包含错误处理"""
        
        print("\n[代码生成测试]")
        response = client.generate_text(
            prompt=code_prompt,
            max_tokens=1024,
            temperature=0.3
        )
        
        if response.get("choices"):
            code_output = response["choices"][0]["message"]["content"]
            print("✓ 代码生成成功")
            print(f"\n生成的代码:\n{code_output}")
        else:
            print(f"✗ 响应异常: {response}")
            
    except Exception as e:
        print(f"✗ 测试失败: {e}")


if __name__ == "__main__":
    print("\nMiniMax API 测试工具")
    print("-" * 60)
    
    # 检查API Key
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        print("⚠️  警告: 未设置MINIMAX_API_KEY环境变量")
        print("请先获取API Key: https://platform.minimaxi.com/user-center/basic-information")
        print("然后设置环境变量: export MINIMAX_API_KEY='your_api_key'")
        sys.exit(1)
    
    # 执行测试
    success = test_api_connection()
    
    if success:
        test_with_custom_model()
        print("\n" + "=" * 60)
        print("✓ 所有测试完成")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("✗ 测试失败，请检查配置和网络连接")
        print("=" * 60)
        sys.exit(1)

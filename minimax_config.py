#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MiniMax-M2.1 API 配置文件
用于配置MiniMax官方API访问参数

使用方法：
1. 将此文件重命名为 config.py
2. 修改 API_KEY 为你的实际密钥
3. 在 minimax_api_test.py 中导入此配置

获取API Key: https://platform.minimaxi.com/user-center/basic-information

作者: AI Assistant
日期: 2025-01-02
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class MiniMaxConfig:
    """
    MiniMax API配置类
    
    Attributes:
        api_key: MiniMax开放平台API密钥
        base_url: API基础URL地址
        model: 使用的模型名称
        timeout: 请求超时时间（秒）
        max_tokens: 默认最大token数量
        temperature: 默认温度参数
    """
    api_key: str = ""
    base_url: str = "https://api.minimaxi.chat/v1"
    model: str = "MiniMax-M2.1"
    timeout: int = 60
    max_tokens: int = 4096
    temperature: float = 0.7


def load_config() -> MiniMaxConfig:
    """
    加载配置文件
    
    优先级：
    1. 环境变量 MINIMAX_API_KEY
    2. 当前文件中的配置
    
    Returns:
        MiniMaxConfig: 配置对象
    """
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    
    return MiniMaxConfig(
        api_key=api_key,
        base_url="https://api.minimaxi.chat/v1",
        model="MiniMax-M2.1",
        timeout=60,
        max_tokens=4096,
        temperature=0.7
    )


def validate_config(config: MiniMaxConfig) -> tuple[bool, str]:
    """
    验证配置是否有效
    
    Args:
        config: MiniMaxConfig配置对象
    
    Returns:
        tuple: (是否有效, 错误信息)
    """
    if not config.api_key:
        return False, "API Key未设置，请设置环境变量MINIMAX_API_KEY或直接在config.py中修改"
    
    if len(config.api_key) < 10:
        return False, "API Key长度无效，请检查是否配置正确"
    
    if not config.base_url.startswith("https://"):
        return False, "API地址必须使用HTTPS协议"
    
    return True, ""


# 便捷函数：快速创建客户端
def create_client(api_key: Optional[str] = None) -> 'MiniMaxClient':
    """
    创建MiniMax API客户端的便捷函数
    
    Args:
        api_key: 可选的API密钥，如果未提供则从环境变量读取
    
    Returns:
        MiniMaxClient: API客户端实例
    """
    from minimax_api_test import MiniMaxClient
    
    if api_key is None:
        api_key = os.environ.get("MINIMAX_API_KEY", "")
    
    return MiniMaxClient(api_key=api_key)


if __name__ == "__main__":
    config = load_config()
    is_valid, error_msg = validate_config(config)
    
    if is_valid:
        print("✓ 配置验证通过")
        print(f"  API地址: {config.base_url}")
        print(f"  使用模型: {config.model}")
        print(f"  超时时间: {config.timeout}秒")
    else:
        print(f"✗ 配置验证失败: {error_msg}")

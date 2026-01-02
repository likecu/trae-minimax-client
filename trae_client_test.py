#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trae CN 客户端测试套件

本模块提供对 Trae CN 逆向客户端的全面测试，包括：
- 认证测试
- API 接口测试
- 性能测试
- 错误处理测试
- 集成测试

作者: AI Assistant
日期: 2025-01-02
"""

import os
import sys
import json
import time
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from typing import Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trae_client import (
    TraeClient,
    TraeConfig,
    TransportManager,
    AuthManager,
    ModelService,
    ICubeService,
    ChatService,
    RequestType,
    ModelProvider,
    TraeAPIError,
    RequestContext,
    create_client
)


class TestTraeConfig(unittest.TestCase):
    """
    测试 TraeConfig 配置类
    """
    
    def test_default_config(self):
        """测试默认配置值"""
        config = TraeConfig()
        self.assertEqual(config.base_url, "https://api.trae.com.cn")
        self.assertEqual(config.timeout, 60)
        self.assertEqual(config.max_retries, 3)
        self.assertTrue(config.enable_logging)
    
    def test_custom_config(self):
        """测试自定义配置值"""
        config = TraeConfig(
            base_url="https://custom.api.com",
            token="test_token",
            timeout=120,
            max_retries=5
        )
        self.assertEqual(config.base_url, "https://custom.api.com")
        self.assertEqual(config.token, "test_token")
        self.assertEqual(config.timeout, 120)
        self.assertEqual(config.max_retries, 5)


class TestAuthManager(unittest.TestCase):
    """
    测试 AuthManager 认证管理器
    """
    
    def setUp(self):
        """设置测试环境"""
        self.config = TraeConfig(token="test_token")
        self.auth = AuthManager(self.config)
    
    def test_get_auth_headers(self):
        """测试获取认证请求头"""
        headers = self.auth.get_auth_headers()
        
        self.assertIn("Content-Type", headers)
        self.assertIn("Authorization", headers)
        self.assertEqual(headers["Authorization"], "Bearer test_token")
        self.assertEqual(headers["Content-Type"], "application/json")
    
    def test_is_token_valid_with_valid_token(self):
        """测试有效令牌的验证"""
        self.assertTrue(self.auth.is_token_valid())
    
    def test_is_token_valid_with_empty_token(self):
        """测试空令牌的验证"""
        auth = AuthManager(TraeConfig(token=""))
        self.assertFalse(auth.is_token_valid())
    
    def test_update_token_info(self):
        """测试更新令牌信息"""
        self.auth.update_token_info(
            token="new_token",
            expired_at="2026-01-15T17:29:52.162Z",
            refresh_token="refresh_token"
        )
        
        self.assertEqual(self.auth.current_token, "new_token")
        self.assertEqual(self.auth.refresh_token, "refresh_token")
        self.assertIsNotNone(self.auth.token_expired_at)
    
    def test_set_and_get_user_info(self):
        """测试用户信息的设置和获取"""
        user_info = {
            "ScreenName": "测试用户",
            "UserID": "12345",
            "Email": "test@example.com"
        }
        
        self.auth.set_user_info(user_info)
        self.assertEqual(self.auth.get_user_info(), user_info)


class TestRequestContext(unittest.TestCase):
    """
    测试 RequestContext 请求上下文类
    """
    
    def test_create_context(self):
        """测试创建请求上下文"""
        context = RequestContext(
            request_id="test-123",
            request_type=RequestType.CHAT
        )
        
        self.assertEqual(context.request_id, "test-123")
        self.assertEqual(context.request_type, RequestType.CHAT)
        self.assertEqual(context.status, "pending")
        self.assertGreater(context.start_time, 0)
    
    def test_context_update(self):
        """测试更新请求上下文"""
        context = RequestContext(
            request_id="test-456",
            request_type=RequestType.MODEL
        )
        
        context.status = "success"
        context.cost_ms = 150
        
        self.assertEqual(context.status, "success")
        self.assertEqual(context.cost_ms, 150)


class TestTransportManager(unittest.TestCase):
    """
    测试 TransportManager 传输管理器
    """
    
    def setUp(self):
        """设置测试环境"""
        self.config = TraeConfig(
            token="test_token",
            enable_logging=False
        )
        self.transport = TransportManager(self.config)
    
    @patch('trae_client.requests.Session.post')
    def test_execute_post_request(self, mock_post):
        """测试执行 POST 请求"""
        mock_response = Mock()
        mock_response.json.return_value = {"result": "success"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        result = self.transport.execute_request(
            method="POST",
            endpoint="/test",
            data={"key": "value"},
            request_type=RequestType.CHAT
        )
        
        self.assertEqual(result, {"result": "success"})
        mock_post.assert_called_once()
    
    @patch('trae_client.requests.Session.get')
    def test_execute_get_request(self, mock_get):
        """测试执行 GET 请求"""
        mock_response = Mock()
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = self.transport.execute_request(
            method="GET",
            endpoint="/test",
            params={"page": 1},
            request_type=RequestType.MODEL
        )
        
        self.assertEqual(result, {"data": "test"})
        mock_get.assert_called_once()
    
    @patch('trae_client.requests.Session.post')
    def test_request_history_tracking(self, mock_post):
        """测试请求历史记录"""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        self.transport.execute_request(
            method="POST",
            endpoint="/test",
            request_type=RequestType.ICUBE
        )
        
        history = self.transport.get_request_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "success")
    
    def test_clear_history(self):
        """测试清空历史记录"""
        self.transport.request_history.append({"test": "data"})
        self.transport.clear_history()
        self.assertEqual(len(self.transport.request_history), 0)


class TestModelService(unittest.TestCase):
    """
    测试 ModelService 模型服务
    """
    
    def setUp(self):
        """设置测试环境"""
        self.config = TraeConfig(token="test_token")
        self.transport = TransportManager(self.config)
        self.model_service = ModelService(self.transport)
    
    @patch.object(TransportManager, 'execute_request')
    def test_get_model_list(self, mock_execute):
        """测试获取模型列表"""
        mock_execute.return_value = {
            "models": [
                {"name": "MiniMax-M2.1", "id": "minimax-m2.1"},
                {"name": "DeepSeek-V2.5", "id": "deepseek-v2.5"}
            ]
        }
        
        models = self.model_service.get_model_list()
        
        self.assertEqual(len(models), 2)
        self.assertEqual(models[0]["name"], "MiniMax-M2.1")
    
    @patch.object(TransportManager, 'execute_request')
    def test_select_model(self, mock_execute):
        """测试选择模型"""
        mock_execute.return_value = {}
        self.model_service.model_list = [
            {"name": "MiniMax-M2.1", "id": "minimax-m2.1"}
        ]
        
        result = self.model_service.select_model("MiniMax-M2.1")
        
        self.assertTrue(result)
        self.assertEqual(self.model_service.selected_model, "MiniMax-M2.1")
    
    def test_select_nonexistent_model(self):
        """测试选择不存在的模型"""
        self.model_service.model_list = [
            {"name": "MiniMax-M2.1", "id": "minimax-m2.1"}
        ]
        
        result = self.model_service.select_model("Unknown-Model")
        
        self.assertFalse(result)


class TestICubeService(unittest.TestCase):
    """
    测试 ICubeService 服务
    """
    
    def setUp(self):
        """设置测试环境"""
        self.config = TraeConfig(token="test_token")
        self.transport = TransportManager(self.config)
        self.icube_service = ICubeService(self.transport)
    
    @patch.object(TransportManager, 'execute_request')
    def test_get_user_info(self, mock_execute):
        """测试获取用户信息"""
        mock_execute.return_value = {
            "Result": {
                "ScreenName": "测试用户",
                "UserID": "12345",
                "AvatarUrl": "https://example.com/avatar.png"
            }
        }
        
        user_info = self.icube_service.get_user_info()
        
        self.assertEqual(user_info["ScreenName"], "测试用户")
        self.assertEqual(user_info["UserID"], "12345")
    
    @patch.object(TransportManager, 'execute_request')
    def test_get_agent_list(self, mock_execute):
        """测试获取代理列表"""
        mock_execute.return_value = {
            "agents": [
                {"id": "agent1", "name": "默认代理"},
                {"id": "agent2", "name": "代码助手"}
            ]
        }
        
        agents = self.icube_service.get_agent_list()
        
        self.assertEqual(len(agents), 2)
        self.assertEqual(agents[0]["id"], "agent1")


class TestChatService(unittest.TestCase):
    """
    测试 ChatService 聊天服务
    """
    
    def setUp(self):
        """设置测试环境"""
        self.config = TraeConfig(token="test_token")
        self.transport = TransportManager(self.config)
        self.chat_service = ChatService(self.transport)
    
    @patch.object(TransportManager, 'execute_request')
    def test_send_message(self, mock_execute):
        """测试发送消息"""
        mock_execute.return_value = {
            "response": "你好！有什么可以帮助你的吗？"
        }
        
        result = self.chat_service.send_message(
            message="你好",
            model="MiniMax-M2.1"
        )
        
        self.assertEqual(result["response"], "你好！有什么可以帮助你的吗？")
    
    @patch.object(TransportManager, 'execute_request')
    def test_message_history_tracking(self, mock_execute):
        """测试消息历史记录"""
        mock_execute.return_value = {"response": "回复"}
        
        self.chat_service.message_history = []
        
        self.chat_service.send_message("第一条消息", model="MiniMax-M2.1")
        self.chat_service.send_message("第二条消息", model="MiniMax-M2.1")
        
        history = self.chat_service.get_history()
        
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0]["content"], "第一条消息")
        self.assertEqual(history[1]["content"], "回复")
        self.assertEqual(history[2]["content"], "第二条消息")
        self.assertEqual(history[3]["content"], "回复")
    
    def test_clear_history(self):
        """测试清空历史记录"""
        self.chat_service.message_history = [
            {"role": "user", "content": "test"}
        ]
        
        self.chat_service.clear_history()
        
        self.assertEqual(len(self.chat_service.message_history), 0)
    
    def test_register_stream_callback(self):
        """测试注册流式回调"""
        callback = Mock()
        
        self.chat_service.register_stream_callback(callback)
        
        self.assertEqual(len(self.chat_service._stream_callbacks), 1)


class TestTraeClient(unittest.TestCase):
    """
    测试 TraeClient 主客户端类
    """
    
    def setUp(self):
        """设置测试环境"""
        self.client = TraeClient(token="test_token")
    
    @patch.object(TransportManager, 'execute_request')
    def test_authenticate(self, mock_execute):
        """测试用户认证"""
        mock_execute.return_value = {
            "token": "new_token",
            "expiredAt": "2026-01-15T17:29:52.162Z",
            "refreshToken": "refresh_token"
        }
        
        result = self.client.authenticate("user", "password")
        
        self.assertTrue(result)
        self.assertEqual(self.client.config.token, "new_token")
    
    @patch.object(TransportManager, 'execute_request')
    def test_get_performance_report(self, mock_execute):
        """测试性能报告生成"""
        mock_execute.return_value = {}
        
        self.client.transport.request_history = [
            {"status": "success", "cost_ms": 100},
            {"status": "success", "cost_ms": 200},
            {"status": "error", "cost_ms": 50}
        ]
        
        report = self.client.get_performance_report()
        
        self.assertEqual(report["total_requests"], 3)
        self.assertEqual(report["successful_requests"], 2)
        self.assertAlmostEqual(report["success_rate"], 66.67, places=1)


class TestCreateClient(unittest.TestCase):
    """
    测试 create_client 便捷函数
    """
    
    @patch.dict(os.environ, {"TRAE_TOKEN": "env_token"})
    def test_create_client_from_env(self):
        """测试从环境变量创建客户端"""
        client = create_client()
        
        self.assertIsInstance(client, TraeClient)
        self.assertEqual(client.config.token, "env_token")
    
    def test_create_client_with_token(self):
        """测试使用令牌创建客户端"""
        client = create_client(token="direct_token")
        
        self.assertIsInstance(client, TraeClient)
        self.assertEqual(client.config.token, "direct_token")


class IntegrationTestCase(unittest.TestCase):
    """
    集成测试用例
    
    注意：这些测试需要有效的 API 令牌才能运行
    """
    
    @unittest.skipUnless(
        os.environ.get("TRAE_TOKEN"),
        "需要设置 TRAE_TOKEN 环境变量"
    )
    def test_live_authentication(self):
        """测试实时认证（需要有效令牌）"""
        token = os.environ.get("TRAE_TOKEN")
        client = TraeClient(token=token)
        
        self.assertTrue(client.auth.is_token_valid())
    
    @unittest.skipUnless(
        os.environ.get("TRAE_TOKEN"),
        "需要设置 TRAE_TOKEN 环境变量"
    )
    def test_live_user_info(self):
        """测试获取用户信息（需要有效令牌）"""
        token = os.environ.get("TRAE_TOKEN")
        client = TraeClient(token=token)
        
        user_info = client.icube.get_user_info()
        
        self.assertIn("UserID", user_info)
        self.assertIn("ScreenName", user_info)


def run_tests():
    """
    运行所有测试
    
    Returns:
        unittest.TestResult: 测试结果
    """
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestTraeConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestAuthManager))
    suite.addTests(loader.loadTestsFromTestCase(TestRequestContext))
    suite.addTests(loader.loadTestsFromTestCase(TestTransportManager))
    suite.addTests(loader.loadTestsFromTestCase(TestModelService))
    suite.addTests(loader.loadTestsFromTestCase(TestICubeService))
    suite.addTests(loader.loadTestsFromTestCase(TestChatService))
    suite.addTests(loader.loadTestsFromTestCase(TestTraeClient))
    suite.addTests(loader.loadTestsFromTestCase(TestCreateClient))
    suite.addTests(loader.loadTestsFromTestCase(IntegrationTestCase))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == "__main__":
    print("=" * 60)
    print("Trae CN 客户端测试套件")
    print("=" * 60)
    print()
    
    result = run_tests()
    
    print()
    print("=" * 60)
    print(f"测试结果: {result.testsRun} 个测试运行")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)} 个")
    print(f"失败: {len(result.failures)} 个")
    print(f"错误: {len(result.errors)} 个")
    print("=" * 60)

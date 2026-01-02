#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trae CN ai-agent 通信协议分析器

通过实际连接 IPC Socket 分析 TowelTransport 协议
并测试各个服务的可用方法

使用方法:
    python3 ai_agent_analyzer.py [--socket SOCKET_PATH]
"""

import os
import sys
import json
import time
import uuid
import socket
import struct
import threading
import argparse
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ProtocolMessage:
    """协议消息"""
    raw: bytes = None
    parsed: dict = None
    timestamp: float = None


class AiAgentProtocolAnalyzer:
    """
    ai-agent 通信协议分析器
    
    通过实际连接和测试来发现协议格式
    """
    
    # 已知的服务和方法
    KNOWN_SERVICES = {
        "ckg": [
            "setup",
            "refresh_token", 
            "is_ckg_enabled_for_non_workspace_scenario",
            "get_solo_qualification"
        ],
        "project": [
            "create_project",
            "get_project_info"
        ],
        "configuration": [
            "get_user_configuration",
            "get_user_info"
        ],
        "chat": [
            "get_sessions",
            "send_message",
            "create_session"
        ],
        "agent": [
            "get_solo_qualification",
            "get_agent_status",
            "execute_command"
        ]
    }
    
    # 可能的协议格式
    PROTOCOL_FORMATS = [
        # 格式1: 4字节长度前缀 + JSON
        {
            "name": "length_prefixed_json",
            "encode": lambda msg: struct.pack('>I', len(msg)) + msg.encode('utf-8'),
            "decode": lambda data: json.loads(data[4:].decode('utf-8')) if len(data) >= 4 else None
        },
        # 格式2: 简单换行分隔
        {
            "name": "newline_delimited",
            "encode": lambda msg: (msg + '\n').encode('utf-8'),
            "decode": lambda data: json.loads(data.decode('utf-8').strip()) if data else None
        },
        # 格式3: 原始 JSON
        {
            "name": "raw_json",
            "encode": lambda msg: msg.encode('utf-8'),
            "decode": lambda data: json.loads(data.decode('utf-8')) if data else None
        }
    ]
    
    def __init__(self, socket_path: str = None):
        """
        初始化分析器
        
        Args:
            socket_path: Unix Domain Socket 路径
        """
        if socket_path is None:
            socket_path = os.path.expanduser(
                "~/Library/Application Support/Trae CN/1.10-main.sock"
            )
        
        self.socket_path = socket_path
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.message_history: List[ProtocolMessage] = []
        
    def connect(self, timeout: float = 5.0) -> bool:
        """
        连接到 ai-agent IPC Socket
        
        Returns:
            bool: 是否连接成功
        """
        try:
            if not os.path.exists(self.socket_path):
                logger.error(f"❌ Socket 不存在: {self.socket_path}")
                return False
            
            logger.info(f"🔌 尝试连接到: {self.socket_path}")
            
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)
            self.socket.connect(self.socket_path)
            
            self.connected = True
            logger.info(f"✅ 连接成功!")
            
            return True
            
        except socket.timeout:
            logger.error("❌ 连接超时")
            return False
        except Exception as e:
            logger.error(f"❌ 连接失败: {e}")
            return False
    
    def disconnect(self):
        """断开连接"""
        if self.socket:
            self.socket.close()
            self.socket = None
            self.connected = False
            logger.info("已断开连接")
    
    def send_and_receive(
        self, 
        message: dict, 
        protocol_format: dict,
        timeout: float = 3.0
    ) -> Optional[dict]:
        """
        发送消息并接收响应
        
        Args:
            message: 发送的消息
            protocol_format: 协议格式
            timeout: 超时时间
            
        Returns:
            Optional[dict]: 响应消息
        """
        if not self.connected:
            logger.error("未连接")
            return None
        
        try:
            # 序列化消息
            content = json.dumps(message, ensure_ascii=False)
            encoded = protocol_format["encode"](content)
            
            # 发送
            self.socket.sendall(encoded)
            logger.debug(f"📤 发送: {content[:100]}...")
            
            # 接收
            self.socket.settimeout(timeout)
            response = self.socket.recv(8192)
            
            if not response:
                logger.warning("空响应")
                return None
            
            # 解析响应
            parsed = protocol_format["decode"](response)
            
            if parsed:
                logger.debug(f"📥 收到: {str(parsed)[:100]}...")
                self.message_history.append(ProtocolMessage(
                    raw=response,
                    parsed=parsed,
                    timestamp=time.time()
                ))
            
            return parsed
            
        except socket.timeout:
            logger.warning("响应超时")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"通信错误: {e}")
            return None
    
    def test_protocol_format(self) -> Optional[dict]:
        """
        测试不同的协议格式
        
        Returns:
            Optional[dict]: 可用的协议格式
        """
        logger.info("\n" + "="*60)
        logger.info("测试协议格式")
        logger.info("="*60)
        
        for fmt in self.PROTOCOL_FORMATS:
            logger.info(f"\n测试格式: {fmt['name']}")
            
            # 发送握手消息
            handshake = {
                "type": "handshake",
                "client": "python_analyzer",
                "version": "1.0",
                "timestamp": time.time()
            }
            
            response = self.send_and_receive(handshake, fmt, timeout=2.0)
            
            if response:
                logger.info(f"✅ 格式 {fmt['name']} 可用!")
                return fmt
        
        logger.error("❌ 没有可用的协议格式")
        return None
    
    def discover_services(self, protocol_format: dict):
        """
        发现可用的服务和方法
        
        Args:
            protocol_format: 协议格式
        """
        logger.info("\n" + "="*60)
        logger.info("发现服务和方法")
        logger.info("="*60)
        
        for service, methods in self.KNOWN_SERVICES.items():
            logger.info(f"\n服务: {service}")
            
            for method in methods:
                request = {
                    "service": service,
                    "method": method,
                    "params": {},
                    "request_id": str(uuid.uuid4()),
                    "timestamp": time.time()
                }
                
                response = self.send_and_receive(request, protocol_format, timeout=2.0)
                
                if response:
                    logger.info(f"  ✅ {method}: 可用")
                    logger.debug(f"     响应: {response}")
                else:
                    logger.warning(f"  ⚠️  {method}: 无响应")
    
    def test_chat_and_agent_services(self, protocol_format: dict):
        """
        测试 chat 和 agent 服务（Solo 功能相关）
        
        Args:
            protocol_format: 协议格式
        """
        logger.info("\n" + "="*60)
        logger.info("测试 Chat 和 Agent 服务")
        logger.info("="*60)
        
        # 测试 Chat 服务
        logger.info("\n💬 Chat 服务:")
        
        chat_requests = [
            {"method": "get_sessions", "params": {}},
            {"method": "get_sessions", "params": {"limit": 10}},
        ]
        
        for req in chat_requests:
            request = {
                "service": "chat",
                "method": req["method"],
                "params": req["params"],
                "request_id": str(uuid.uuid4()),
                "timestamp": time.time()
            }
            
            response = self.send_and_receive(request, protocol_format, timeout=3.0)
            
            if response:
                logger.info(f"  ✅ get_sessions: 成功")
                logger.info(f"     数据: {json.dumps(response, indent=2, ensure_ascii=False)[:200]}")
            else:
                logger.warning(f"  ⚠️  get_sessions: 无响应")
        
        # 测试 Agent 服务
        logger.info("\n🤖 Agent 服务:")
        
        agent_requests = [
            {"method": "get_solo_qualification", "params": {}},
            {"method": "get_agent_status", "params": {}},
        ]
        
        for req in agent_requests:
            request = {
                "service": "agent",
                "method": req["method"],
                "params": req["params"],
                "request_id": str(uuid.uuid4()),
                "timestamp": time.time()
            }
            
            response = self.send_and_receive(request, protocol_format, timeout=3.0)
            
            if response:
                logger.info(f"  ✅ {req['method']}: 成功")
                logger.info(f"     数据: {json.dumps(response, indent=2, ensure_ascii=False)[:200]}")
            else:
                logger.warning(f"  ⚠️  {req['method']}: 无响应")
    
    def test_ipc_message_format(self):
        """
        测试 VSCode IPC 消息格式
        """
        logger.info("\n" + "="*60)
        logger.info("测试 VSCode IPC 消息格式")
        logger.info("="*60)
        
        # VSCode 使用 4 字节长度前缀 + JSON-RPC 风格消息
        # 消息格式: [type, id, channel, method, arg]
        
        test_messages = [
            # 简单 ping
            ([0, 1, "", "ping", []], "Ping"),
            # 获取配置
            ([100, 2, "configuration", "get_user_configuration", []], "get_user_configuration"),
            # Chat 会话
            ([102, 3, "chat", "get_sessions", []], "chat.get_sessions"),
            # Agent Solo
            ([100, 4, "agent", "get_solo_qualification", []], "agent.get_solo_qualification"),
        ]
        
        for msg, name in test_messages:
            try:
                # 序列化
                content = json.dumps(msg)
                encoded = struct.pack('>I', len(content)) + content.encode('utf-8')
                
                # 发送
                self.socket.sendall(encoded)
                logger.info(f"📤 发送 {name}: {msg}")
                
                # 接收
                self.socket.settimeout(2.0)
                response = self.socket.recv(8192)
                
                if response:
                    logger.info(f"📥 响应 {name}: {response[:200]}")
                else:
                    logger.warning(f"⚠️  {name}: 空响应")
                    
            except Exception as e:
                logger.error(f"❌ {name}: {e}")
    
    def run_full_analysis(self):
        """运行完整分析"""
        logger.info("="*60)
        logger.info("Trae CN ai-agent 通信协议分析")
        logger.info("="*60)
        logger.info(f"Socket: {self.socket_path}")
        logger.info(f"存在: {os.path.exists(self.socket_path)}")
        
        if not self.connect():
            logger.error("无法连接到 ai-agent")
            return
        
        try:
            # 测试协议格式
            protocol_format = self.test_protocol_format()
            
            if not protocol_format:
                # 如果标准格式不工作，尝试 VSCode IPC 格式
                logger.info("\n尝试 VSCode IPC 格式...")
                self.test_ipc_message_format()
                return
            
            # 发现服务
            self.discover_services(protocol_format)
            
            # 重点测试 Chat 和 Agent
            self.test_chat_and_agent_services(protocol_format)
            
            # 保存消息历史
            self.save_message_history()
            
        finally:
            self.disconnect()
    
    def save_message_history(self):
        """保存消息历史到文件"""
        if not self.message_history:
            return
        
        output_file = "/Volumes/600g/app1/env-fix/trae_asar/message_history.json"
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump([
                    {
                        "timestamp": msg.timestamp,
                        "parsed": msg.parsed
                    }
                    for msg in self.message_history
                ], f, indent=2, ensure_ascii=False)
            
            logger.info(f"\n💾 消息历史已保存到: {output_file}")
            
        except Exception as e:
            logger.error(f"保存失败: {e}")


class SimpleIPCTester:
    """
    简单 IPC 测试器
    
    直接测试各种消息格式
    """
    
    def __init__(self, socket_path: str = None):
        if socket_path is None:
            socket_path = os.path.expanduser(
                "~/Library/Application Support/Trae CN/1.10-main.sock"
            )
        self.socket_path = socket_path
    
    def test_connection(self):
        """测试连接"""
        print("\n" + "="*60)
        print("IPC 连接测试")
        print("="*60)
        
        if not os.path.exists(self.socket_path):
            print(f"❌ Socket 不存在: {self.socket_path}")
            return
        
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect(self.socket_path)
            
            print(f"✅ 连接成功!")
            
            # 测试不同的消息格式
            test_cases = [
                {
                    "name": "VSCode IPC (长度前缀)",
                    "data": json.dumps([100, 1, "agent", "get_solo_qualification", []]),
                    "encoded": lambda d: struct.pack('>I', len(d)) + d.encode('utf-8')
                },
                {
                    "name": "JSON-RPC 风格",
                    "data": json.dumps({
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "agent/get_solo_qualification",
                        "params": {}
                    }),
                    "encoded": lambda d: d.encode('utf-8')
                },
                {
                    "name": "简单对象",
                    "data": json.dumps({
                        "service": "agent",
                        "method": "get_solo_qualification"
                    }),
                    "encoded": lambda d: d.encode('utf-8')
                }
            ]
            
            for tc in test_cases:
                print(f"\n测试: {tc['name']}")
                try:
                    encoded = tc["encoded"](tc["data"])
                    print(f"  发送: {tc['data'][:100]}...")
                    sock.sendall(encoded)
                    
                    # 接收响应
                    response = sock.recv(8192)
                    print(f"  收到: {response[:200]}")
                    
                except socket.timeout:
                    print("  ⚠️  超时")
                except Exception as e:
                    print(f"  ❌ 错误: {e}")
            
            sock.close()
            
        except Exception as e:
            print(f"❌ 连接失败: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Trae CN ai-agent 通信协议分析器'
    )
    parser.add_argument(
        '--socket', '-s',
        help='Unix Domain Socket 路径'
    )
    parser.add_argument(
        '--simple', '-S',
        action='store_true',
        help='简单连接测试'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='详细输出'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    socket_path = args.socket
    if socket_path is None:
        socket_path = os.path.expanduser(
            "~/Library/Application Support/Trae CN/1.10-main.sock"
        )
    
    if args.simple:
        tester = SimpleIPCTester(socket_path)
        tester.test_connection()
    else:
        analyzer = AiAgentProtocolAnalyzer(socket_path)
        analyzer.run_full_analysis()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Trae与外部系统交互监控工具
用于监控Trae应用与外部系统的交互过程，获取token等认证信息

使用说明：
1. 确保已安装mitmproxy：pip install mitmproxy
2. 运行Clash，确保代理已启动
3. 运行此脚本：python trae_token_monitor.py
4. 将Trae应用的代理设置为：http://localhost:8080
5. 观察终端输出，获取token信息
"""

import sys
import json
from mitmproxy import http
from mitmproxy.tools.main import mitmdump

class TraeTokenMonitor:
    """
    Trae与外部系统交互监控类
    用于拦截和分析Trae应用的网络请求，提取token等认证信息
    """
    
    def __init__(self):
        """
        初始化监控器
        """
        self.token_list = []
        self.interaction_count = 0
        self.important_domains = [
            "api.trae.local",
            "auth.trae.local",
            "trae.local",
            "api.github.com",
            "github.com",
            "oauth2.googleapis.com"
        ]
    
    def request(self, flow: http.HTTPFlow) -> None:
        """
        处理请求
        
        Args:
            flow: HTTP请求流对象
        """
        self.interaction_count += 1
        
        # 获取域名
        domain = flow.request.host
        
        # 显示所有请求，便于调试
        print(f"\n[请求 #{self.interaction_count}] - {domain}")
        print(f"URL: {flow.request.url}")
        print(f"方法: {flow.request.method}")
        
        # 检查所有请求头，便于调试
        print("请求头:")
        for key, value in flow.request.headers.items():
            print(f"  {key}: {value}")
            # 检查所有请求头中的认证信息
            if "token" in key.lower() or "auth" in key.lower() or key.lower() == "authorization":
                print(f"  \033[94m[调试] 可能的认证头: {key}: {value}\033[0m")
                self._extract_token(value, f"请求头-{key}")
        
        # 检查Cookie中的认证信息
        if "Cookie" in flow.request.headers:
            cookies = flow.request.headers["Cookie"]
            print(f"Cookie: {cookies}")
            self._extract_token_from_cookie(cookies)
        
        # 检查请求体中的认证信息（POST/PUT请求）
        if flow.request.method in ["POST", "PUT", "PATCH"] and flow.request.content:
            try:
                body = flow.request.text
                print(f"请求体: {body[:200]}..." if len(body) > 200 else f"请求体: {body}")
                self._extract_token_from_body(body)
            except Exception as e:
                print(f"解析请求体失败: {e}")
        
        print("-" * 50)
    
    def response(self, flow: http.HTTPFlow) -> None:
        """
        处理响应
        
        Args:
            flow: HTTP响应流对象
        """
        # 获取域名
        domain = flow.request.host
        
        # 显示所有响应，便于调试
        print(f"\n[响应 #{self.interaction_count}] - {domain}")
        print(f"状态码: {flow.response.status_code}")
        
        # 检查所有响应头，便于调试
        print("响应头:")
        for key, value in flow.response.headers.items():
            print(f"  {key}: {value}")
            # 检查所有响应头中的认证信息
            if key.lower() == "set-cookie":
                print(f"  \033[94m[调试] Set-Cookie: {value}\033[0m")
                self._extract_token_from_cookie(value)
            elif "token" in key.lower() or "auth" in key.lower():
                print(f"  \033[94m[调试] 可能的认证响应头: {key}: {value}\033[0m")
                self._extract_token(value, f"响应头-{key}")
        
        # 检查响应体中的认证信息
        if flow.response.content:
            try:
                body = flow.response.text
                # 打印所有响应体的前300个字符，便于调试
                content_type = flow.response.headers.get("Content-Type", "")
                print(f"响应体 (Content-Type: {content_type}):")
                if len(body) > 300:
                    print(f"  {body[:300]}...")
                else:
                    print(f"  {body}")
                
                # 从所有响应体中提取token，不仅限于JSON
                self._extract_token_from_body(body)
            except Exception as e:
                print(f"  解析响应体失败: {e}")
        
        print("=" * 50)
    
    def _extract_token(self, auth_header: str, source: str) -> None:
        """
        从认证头中提取token
        
        Args:
            auth_header: 认证头字符串
            source: token来源
        """
        # 扩展token类型
        token_types = ["Bearer", "Token", "Auth", "API-Key", "Api-Key", "X-Token", "Authorization", "x-auth-token"]
        
        for token_type in token_types:
            if token_type.lower() in auth_header.lower():
                # 处理不同格式的认证头
                if auth_header.startswith(token_type):
                    token = auth_header[len(token_type):].strip()
                else:
                    # 查找token_type: token格式
                    import re
                    match = re.search(rf'{token_type}:\s*([^\s,]+)', auth_header, re.IGNORECASE)
                    if match:
                        token = match.group(1)
                    else:
                        continue
                
                if token and token not in self.token_list:
                    self.token_list.append(token)
                    print(f"\033[92m[发现Token]\033[0m 类型: {token_type}, 来源: {source}")
                    print(f"\033[93mToken值: {token}\033[0m")
                break
    
    def _extract_token_from_cookie(self, cookie_string: str) -> None:
        """
        从Cookie字符串中提取token
        
        Args:
            cookie_string: Cookie字符串
        """
        cookie_pairs = cookie_string.split("; ")
        for pair in cookie_pairs:
            if "=" in pair:
                key, value = pair.split("=", 1)
                # 扩展token相关Cookie名
                token_cookie_names = [
                    "token", "auth", "access_token", "session", "sid", "trae_token",
                    "accessToken", "auth_token", "session_id", "user_token", "api_token",
                    "x-token", "x_auth_token", "authorization", "auth-token", "jwt",
                    "refresh_token", "id_token", "csrf_token", "csrf"
                ]
                if any(token_name in key.lower() for token_name in token_cookie_names):
                    if value and value not in self.token_list:
                        self.token_list.append(value)
                        print(f"\033[92m[发现Cookie Token]\033[0m")
                        print(f"\033[93m{key}: {value}\033[0m")
    
    def _extract_token_from_body(self, body: str) -> None:
        """
        从请求/响应体中提取token
        
        Args:
            body: 请求或响应体字符串
        """
        try:
            # 尝试解析JSON
            data = json.loads(body)
            
            # 递归查找token字段
            def find_tokens(obj, path=""):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        current_path = f"{path}.{key}" if path else key
                        if isinstance(value, (dict, list)):
                            find_tokens(value, current_path)
                        elif isinstance(value, str):
                            # 扩展token相关字段名
                            token_field_names = [
                                "token", "access_token", "refresh_token", "auth_token", "api_key", "secret",
                                "accessToken", "refreshToken", "authToken", "apiKey", "ApiKey",
                                "x_token", "x-auth-token", "authorization", "auth", "session",
                                "session_id", "user_token", "app_token", "device_token", "oauth_token",
                                "id_token", "jwt", "csrf_token", "csrf", "ticket", "sid"
                            ]
                            
                            # 检查字段名是否包含token相关关键词
                            if any(token_field in key.lower() for token_field in token_field_names):
                                if value and value not in self.token_list:
                                    self.token_list.append(value)
                                    print(f"\033[92m[发现Body Token]\033[0m 路径: {current_path}")
                                    print(f"\033[93m{key}: {value}\033[0m")
                            
                            # 检查值是否符合token格式（长字符串、包含特定字符等）
                            elif len(value) > 15:  # 更长的token阈值
                                import re
                                # 常见token格式：JWT、UUID、随机长字符串等
                                if re.match(r'^[a-zA-Z0-9_\-\.+/=]{15,}$', value):
                                    if value not in self.token_list:
                                        self.token_list.append(value)
                                        print(f"\033[92m[发现疑似Token]\033[0m 路径: {current_path}")
                                        print(f"\033[93m{key}: {value}\033[0m")
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        current_path = f"{path}[{i}]" if path else f"[{i}]"
                        find_tokens(item, current_path)
            
            find_tokens(data)
        except json.JSONDecodeError:
            # 不是JSON，尝试直接查找token模式
            import re
            # 扩展token正则模式
            token_patterns = [
                r"(?:token|access_token|refresh_token|auth_token|api_key|secret|jwt|session|sid)\s*[:=]\s*['\"]([^'\"]+)['\"]",
                r"(?:Bearer|Token|Auth|API-Key|Api-Key)\s+([a-zA-Z0-9_\-\.+/=]+)",
                r"token\s*[:=]\s*([a-zA-Z0-9_\-\.+/=]+)",
                r"access_token\s*[:=]\s*([a-zA-Z0-9_\-\.+/=]+)",
                r"refresh_token\s*[:=]\s*([a-zA-Z0-9_\-\.+/=]+)",
                r"([a-zA-Z0-9_\-\.+/=]{20,})"  # 长字符串可能是token
            ]
            
            for pattern in token_patterns:
                matches = re.findall(pattern, body, re.IGNORECASE)
                for match in matches:
                    if match and match not in self.token_list:
                        self.token_list.append(match)
                        print(f"\033[92m[发现Token]\033[0m 来源: 文本匹配")
                        print(f"\033[93mToken值: {match}\033[0m")
    
    def done(self):
        """
        脚本结束时调用，打印总结信息
        """
        print(f"\n\033[94m[监控总结]\033[0m")
        print(f"总交互次数: {self.interaction_count}")
        print(f"发现的Token数量: {len(self.token_list)}")
        if self.token_list:
            print("\033[93m发现的Token列表:\033[0m")
            for i, token in enumerate(self.token_list, 1):
                print(f"{i}. {token}")
        print("\n\033[91m注意: 请妥善保管获取到的Token，避免泄露！\033[0m")

def run_monitor():
    """
    运行监控器
    """
    print("\033[94mTrae与外部系统交互监控工具\033[0m")
    print("=" * 50)
    print("使用说明:")
    print("1. 确保已安装mitmproxy: pip install mitmproxy")
    print("2. 运行Clash，确保代理已启动")
    print("3. 将Trae应用的代理设置为: http://localhost:8080")
    print("4. 观察终端输出，获取token信息")
    print("5. 按 Ctrl+C 停止监控")
    print("=" * 50)
    print("\033[92m监控已启动，正在监听 http://localhost:8080\033[0m")
    print("\033[91m注意: 首次使用需要安装mitmproxy证书到系统信任存储\033[0m")
    print("证书位置: ~/.mitmproxy/mitmproxy-ca-cert.pem")
    print("=" * 50)
    
    # 运行mitmdump，使用我们的监控类
    mitmdump(['-s', __file__, '--set', 'ssl_insecure=true'])

# 创建监控器实例，mitmproxy会自动查找addons变量
monitor = TraeTokenMonitor()

# 设置mitmproxy的事件处理函数
def request(flow):
    monitor.request(flow)

def response(flow):
    monitor.response(flow)

def done():
    monitor.done()

# 将监控器添加到addons列表，mitmproxy会自动加载
addons = [monitor]

if __name__ == "__main__":
    # 直接运行时，启动mitmdump
    run_monitor()

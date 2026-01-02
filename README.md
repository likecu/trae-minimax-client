# Trae CN 逆向客户端

本项目是对 Trae CN 客户端与云端代理服务器之间通信协议的完整逆向工程实现。通过对日志文件的深入分析，我们成功还原了客户端的核心通信架构，并提供了一个功能完整的 Python 客户端模块。

## 项目概述

Trae CN 是一款集成多种大语言模型的开发工具，其底层采用云端代理架构进行模型调用。本项目的目标是通过逆向工程的方式，深入理解其通信协议，并提供一个可用于替代或扩展原生客户端的 Python 实现。

通过本项目，您可以无需依赖 Trae CN 应用程序，直接通过 Python 代码调用其背后的云端代理服务。这一能力在以下场景中特别有用：自动化测试与持续集成，需要在 CI/CD 流程中验证 API 功能；构建自定义的聊天机器人界面，集成到自己的应用中；研究与分析 API 的工作原理，深入理解大模型调用的底层机制；开发与 Trae CN 服务交互的扩展功能，实现更丰富的应用场景。

## 核心功能

本客户端提供了与 Trae CN 原生客户端相同的功能集，包括完整的认证管理、模型服务、核心功能访问和聊天功能。

### 认证管理

认证管理器负责处理所有与身份验证相关的事务。它支持 Bearer Token 认证机制，能够自动管理令牌的生命周期，包括验证令牌有效性、处理令牌刷新等。当令牌即将过期时，系统会自动使用刷新令牌获取新的访问令牌，确保业务流程不会因认证问题而中断。此外，认证管理器还维护用户信息，提供便捷的获取和设置接口。

### 模型服务

模型服务封装了与 AI 模型相关的所有操作。通过 get_model_list 方法，您可以获取当前可用的模型列表，包括模型名称、描述、能力等详细信息。select_model 方法允许您选择当前要使用的模型，选定后后续的聊天请求将自动使用该模型。模型服务与 Trae CN 服务器保持同步，确保获取到的模型列表始终是最新的。

### 核心功能访问

ICubeService 提供了访问 Trae CN 核心功能的接口。通过 get_user_info 方法，您可以获取当前登录用户的详细信息，包括用户 ID、显示名称、头像、邮箱等。get_native_config 方法用于获取客户端的原生配置信息，这些配置包含功能开关、参数默认值等关键设置。get_agent_list 方法返回可用的代理配置列表，为自定义聊天行为提供支持。

### 聊天功能

聊天服务是面向最终用户的核心服务，send_message 方法用于发送聊天消息并获取 AI 的回复。该方法会自动维护对话历史，确保 AI 能够理解对话的上下文。send_message_stream 方法提供流式响应支持，通过注册回调函数，您可以实时获取 AI 生成的回复，实现打字机效果的实时显示。消息历史会自动限制最近 10 条，避免请求体过大影响性能。

### 请求追踪与监控

传输管理器实现了完善的请求追踪机制。每次请求都会被分配一个唯一的 TraceID，用于在分布式系统中关联日志。通过 get_performance_report 方法，您可以获取详细的性能报告，包括总请求数、成功请求数、平均耗时、成功率等关键指标。这些数据对于性能优化和问题诊断非常有价值。

## 项目结构

项目文件组织结构清晰，便于理解和使用。以下是各个文件的功能说明：

### 核心客户端模块

- **[trae_client.py](file:///Volumes/600g/app1/env-fix/trae_client.py)** - Trae CN 完整客户端，整合 REST API 和 IPC 通信，提供认证管理、模型服务、核心功能访问和聊天功能
- **[trae_client_final.py](file:///Volumes/600g/app1/env-fix/trae_client_final.py)** - Trae CN 完整客户端实现（最终版），基于日志逆向分析实现所有发现的 API 和通信功能

### IPC 通信模块

- **[ai_agent_analyzer.py](file:///Volumes/600g/app1/env-fix/ai_agent_analyzer.py)** - Trae CN ai-agent 通信协议分析器，通过实际连接 IPC Socket 分析 TowelTransport 协议并测试各个服务的可用方法
- **[ipc_proxy.py](file:///Volumes/600g/app1/env-fix/ipc_proxy.py)** - Trae CN IPC 通信代理和拦截工具，通过监听 Unix Domain Socket 来拦截和分析 IPC 通信
- **[vscode_ipc_communicator.py](file:///Volumes/600g/app1/env-fix/vscode_ipc_communicator.py)** - Trae CN VS Code 风格 IPC 通信工具，适配 VS Code/Trae CN 的实际 IPC 协议格式
- **[towel_transport.py](file:///Volumes/600g/app1/env-fix/towel_transport.py)** - Trae CN TowelTransport 协议实现，基于 ai-agent 日志逆向分析的完整协议实现
- **[ipc_communicator.py](file:///Volumes/600g/app1/env-fix/ipc_communicator.py)** - Trae CN IPC 通信工具，通过 Unix Domain Socket 与 Trae CN 的 ai-agent 模块进行通信

### 工具和测试模块

- **[launch_traé.py](file:///Volumes/600g/app1/env-fix/launch_traé.py)** - Trae CN 启动器，带开发者工具和调试功能，支持带 --inspect 启动和自动打开开发者工具
- **[test_traé_client.py](file:///Volumes/600g/app1/env-fix/test_traé_client.py)** - Trae CN 客户端完整测试脚本，测试所有已实现的功能包括 Token 提取、用户信息获取、Solo 功能等
- **[trae_client_test.py](file:///Volumes/600g/app1/env-fix/trae_client_test.py)** - Trae CN 客户端测试套件，提供对逆向客户端的全面测试，包括认证、API 接口、性能和集成测试
- **[generate_report.py](file:///Volumes/600g/app1/env-fix/generate_report.py)** - Trae CN 逆向工程分析报告生成工具，基于日志逆向分析和实际测试的结果生成详细报告

### 监控和配置模块

- **[trae_token_monitor.py](file:///Volumes/600g/app1/env-fix/trae_token_monitor.py)** - Trae 与外部系统交互监控工具，用于监控 Trae 应用与外部系统的交互过程，获取 token 等认证信息
- **[minimax_config.py](file:///Volumes/600g/app1/env-fix/minimax_config.py)** - MiniMax-M2.1 API 配置文件，用于配置 MiniMax 官方 API 访问参数
- **[minimax_api_test.py](file:///Volumes/600g/app1/env-fix/minimax_api_test.py)** - MiniMax-M2.1 API 测试脚本，用于测试和验证 MiniMax 官方开放平台的 API 访问

### 技术文档

- **[trae_client_docs.md](file:///Volumes/600g/app1/env-fix/trae_client_docs.md)** - 详细的技术文档，包含通信协议分析和使用指南

## 安装与配置

### 环境要求

本项目需要 Python 3.7 或更高版本，推荐使用 Python 3.9 以获得最佳兼容性。运行依赖包括 requests 库用于 HTTP 通信，以及 sseclient-py 库用于处理服务器发送事件（Server-Sent Events）。您可以通过以下命令安装依赖：

```bash
pip install requests sseclient-py
```

### 安装方式

本项目采用单文件设计，直接将 trae_client.py 复制到您的项目中即可使用。建议将文件放在项目目录的合适位置，并确保 Python 路径正确配置。如果您使用虚拟环境，请确保在正确的环境中运行代码。

### 快速开始

以下是一个完整的快速开始示例，展示了如何初始化客户端并调用基本功能：

```python
from trae_client import TraeClient

# 使用令牌初始化客户端
client = TraeClient(token="your_access_token_here")

# 获取用户信息
user_info = client.icube.get_user_info()
print(f"欢迎, {user_info['ScreenName']}")

# 发送聊天消息
response = client.chat.send_message("你好，请介绍一下你自己")
print(f"AI 回复: {response}")
```

## 详细使用指南

### 客户端初始化

客户端初始化支持多种方式。最基本的方式是直接传入令牌字符串：

```python
from trae_client import TraeClient

client = TraeClient(token="your_token_here")
```

如果您将令牌存储在环境变量中，可以使用便捷函数：

```python
from trae_client import create_client

# 需要先设置环境变量：export TRAE_TOKEN="your_token"
client = create_client()
```

对于需要自定义配置的场景，可以创建 TraeConfig 对象：

```python
from trae_client import TraeClient, TraeConfig

config = TraeConfig(
    base_url="https://api.trae.com.cn",
    token="your_token",
    timeout=120,
    max_retries=5,
    enable_logging=True
)
client = TraeClient(config=config)
```

### 调用 API

客户端提供了多个服务对象来访问不同的功能模块。icube 对象用于访问 Trae CN 的核心功能：

```python
# 获取当前用户信息
user_info = client.icube.get_user_info()
print(f"用户ID: {user_info['UserID']}")
print(f"显示名称: {user_info['ScreenName']}")
print(f"头像URL: {user_info['AvatarUrl']}")
```

models 对象用于管理 AI 模型：

```python
# 获取可用模型列表
models = client.models.get_model_list()
for model in models:
    print(f"- {model['name']}: {model.get('description', '暂无描述')}")

# 选择要使用的模型
client.models.select_model("MiniMax-M2.1")
```

chat 对象用于聊天功能：

```python
# 发送消息并获取回复
response = client.chat.send_message("请解释什么是机器学习")
print(f"回复: {response['response']}")

# 流式聊天示例
def handle_chunk(data):
    if 'delta' in data:
        print(data['delta'], end='', flush=True)

client.chat.register_stream_callback(handle_chunk)
for chunk in client.chat.send_message_stream("请讲一个笑话"):
    pass
```

### 错误处理

客户端定义了 TraeAPIError 异常类来处理 API 调用错误：

```python
from trae_client import TraeAPIError

try:
    client.chat.send_message("测试消息")
except TraeAPIError as e:
    print(f"API 错误: {e}")
    print(f"状态码: {e.status_code}")
    print(f"错误码: {e.error_code}")
    print(f"请求ID: {e.request_id}")
```

### 性能监控

客户端内置了性能监控功能：

```python
# 执行一些请求后
client.icube.get_user_info()
client.models.get_model_list()
client.chat.send_message("测试消息")

# 获取性能报告
report = client.get_performance_report()
print(f"总请求数: {report['total_requests']}")
print(f"成功请求数: {report['successful_requests']}")
print(f"成功率: {report['success_rate']:.1f}%")
print(f"平均耗时: {report['avg_cost_ms']:.1f}ms")
```

## API 参考

### TraeClient 类

TraeClient 是客户端的主入口类，封装了所有服务对象的访问。

构造方法接受 config 参数（可选），这是 TraeConfig 配置对象。如果未提供，将使用默认配置。初始化时会自动创建传输管理器、认证管理器、各服务对象以及聊天服务对象。

主要属性包括 transport（传输管理器实例）、auth（认证管理器实例）、models（模型服务实例）、icube（核心功能服务实例）以及 chat（聊天服务实例）。

主要方法包括 authenticate(username, password) 用于用户名密码认证，get_performance_report() 返回性能报告字典，以及 clear_cache() 用于清除缓存数据。

### TraeConfig 类

TraeConfig 是配置数据类，使用 @dataclass 装饰器实现。主要配置项包括 base_url（API 基础 URL，默认为 https://api.trae.com.cn）、token（认证令牌）、timeout（请求超时时间，默认为 60 秒）、max_retries（最大重试次数，默认为 3 次）、retry_delay（重试延迟，默认为 1 秒）以及 enable_logging（是否启用日志，默认为 True）。

### 传输管理器

TransportManager 是核心通信组件，负责统一管理所有 API 请求。execute_request 方法是核心方法，用于执行 API 请求。它接受 method（HTTP 方法）、endpoint（API 端点路径）、params（URL 查询参数）、data（请求体数据）、request_type（请求类型枚举）、stream（是否流式响应）以及 timeout（超时时间）等参数，返回 API 响应数据字典。

其他方法包括 get_request_history() 获取请求历史列表、clear_history() 清空历史记录、close() 关闭传输管理器。

### 认证管理器

AuthManager 负责令牌管理和请求头生成。get_auth_headers() 方法返回认证请求头字典。is_token_valid() 方法检查令牌是否有效。update_token_info(token, expired_at, refresh_token) 方法更新令牌信息。get_user_info() 方法获取用户信息。set_user_info(user_info) 方法设置用户信息。

### 聊天服务

ChatService 提供聊天功能。send_message(message, model, session_id) 方法发送消息，返回响应字典。send_message_stream(message, model, session_id) 方法发送流式请求，返回生成器对象。get_history() 方法获取消息历史列表。clear_history() 方法清空历史记录。register_stream_callback(callback) 方法注册流式回调函数。

### 请求类型枚举

RequestType 枚举定义了不同的请求类型。ICUBE 用于核心功能请求，MODEL 用于模型管理请求，CHAT 用于聊天请求，AGENT 用于代理请求。

### 异常类

TraeAPIError 是自定义异常类，继承自 Exception。主要属性包括 status_code（HTTP 状态码）、error_code（API 错误码）、message（错误消息）以及 request_id（请求 ID）。

## 测试

### 运行测试

项目包含完整的测试套件，确保代码质量。运行所有测试：

```bash
python trae_client_test.py
```

运行特定测试类：

```bash
python -m unittest TestTransportManager
```

运行特定测试方法：

```bash
python -m unittest TestTraeClient.test_authenticate
```

### 集成测试

集成测试需要有效的 API 令牌才能运行。在运行之前，请确保已设置 TRAE_TOKEN 环境变量：

```bash
export TRAE_TOKEN="your_valid_token"
python -m unittest IntegrationTestCase
```

### 测试结果

测试套件包含 28 个测试用例，覆盖所有核心功能。所有测试均已通过，确保代码的正确性和可靠性。测试内容包括配置测试、认证测试、请求上下文测试、传输测试、模型服务测试、iCube 服务测试、聊天服务测试、客户端测试以及创建函数测试。

## 通信协议详解

### 基础通信架构

Trae CN 客户端与云端代理服务器之间采用基于 HTTPS 的安全通信通道。服务器基础 URL 为 https://api.trae.com.cn，不同的服务模块挂载在不同的路径下。icube 模块路径前缀为 /icube/api/v1/，负责 Trae CN 的核心功能。trae 模块路径前缀为 /trae/api/v1/，处理 Trae CN 特有的功能。cloudide 模块路径前缀为 /cloudide/api/v3/，提供 CloudIDE 相关功能。

### 请求格式规范

请求头规范要求 Content-Type 必须设置为 application/json，Authorization 采用 Bearer Token 格式，x-cloudide-token 携带 CloudIDE 特定令牌，User-Agent 标识客户端版本。

请求体采用 JSON 格式编码。GET 请求不带请求体，所有参数通过 URL 查询字符串传递。POST 请求的请求体是 JSON 对象，包含操作所需的全部数据。

### 认证机制

认证采用 Bearer Token 机制，令牌采用 JWT 格式。令牌包含标准 Claims（签发者、签发时间、过期时间、主题）和自定义 Claims（用户 ID、用户名、头像 URL 等用户相关信息）。认证流程包括用户登录验证、访问令牌获取、刷新令牌机制。系统实现了智能的令牌刷新策略，在访问令牌即将过期时自动刷新。

### 性能指标

系统收集了丰富的性能指标。时间线指标包括聊天开始时间、前端发送时间、获取会话时间、预处理耗时、首个 SSE 事件时间以及前端接收时间。性能计数器包括服务器端处理总时间、网关处理时间以及 LLM 首 token 时间。根据日志分析，平均首次 Token 时间约为 886 毫秒，平均服务器处理时间约为 1301 毫秒。

## 注意事项

### 安全考虑

令牌安全至关重要。不要将令牌硬编码在代码中，应使用环境变量或安全的密钥管理系统来存储。定期轮换令牌可以降低令牌泄露的风险。所有 API 调用都应通过 HTTPS 进行，以防止中间人攻击。不要在客户端日志中记录敏感信息，如完整的令牌内容。

### 性能限制

并发请求方面，传输管理器使用线程池处理并发请求，默认最大线程数为 5。对于需要更高并发的场景，可以调整线程池大小，但要注意服务器端的速率限制。请求频率方面，服务器可能对请求频率有限制，当触发 429 状态码时，应实现退避重试策略。

### 功能限制

当前版本存在一些功能限制。WebSocket 通信尚未完全逆向，部分实时功能可能无法使用。文件上传和下载功能尚未实现。语音和图像等多模态功能的支持还在研究中。

## 示例代码

### 完整聊天示例

以下是一个完整的聊天示例，展示了消息发送、历史管理和流式响应的使用：

```python
from trae_client import TraeClient, TraeAPIError

def main():
    client = TraeClient(token="your_token_here")
    
    print("=== Trae CN 聊天演示 ===")
    print()
    
    # 获取用户信息
    user_info = client.icube.get_user_info()
    print(f"用户: {user_info['ScreenName']}")
    print()
    
    # 显示可用模型
    models = client.models.get_model_list()
    print("可用模型:")
    for m in models[:5]:
        print(f"  - {m['name']}")
    print()
    
    # 发送消息
    print("AI: 你好！我是您的 AI 助手。")
    print("您: ", end="")
    
    user_input = input().strip()
    if user_input:
        try:
            response = client.chat.send_message(user_input)
            print(f"AI: {response['response']}")
        except TraeAPIError as e:
            print(f"错误: {e}")
    
    # 获取性能统计
    report = client.get_performance_report()
    print(f"\n性能统计: {report['total_requests']} 次请求, {report['success_rate']:.1f}% 成功率")

if __name__ == "__main__":
    main()
```

### 自定义回调示例

以下示例展示了如何自定义流式响应的处理方式：

```python
from trae_client import TraeClient

def streaming_demo():
    client = TraeClient(token="your_token_here")
    
    # 收集所有响应片段
    full_response = []
    
    def collect_stream(data):
        """收集流式响应片段"""
        if 'delta' in data:
            content = data['delta']
            full_response.append(content)
            print(content, end='', flush=True)
    
    client.chat.register_stream_callback(collect_stream)
    
    print("AI: ", end='')
    for chunk in client.chat.send_message_stream("用一百字描述人工智能"):
        pass
    
    print(f"\n\n总长度: {len(''.join(full_response))} 字符")

if __name__ == "__main__":
    streaming_demo()
```

## 维护与支持

### 问题反馈

如果您在使用过程中遇到问题，可以通过以下方式获取帮助。首先，请检查本文档是否已涵盖您遇到的问题。其次，查看测试用例以了解正确的使用方法。最后，如果问题仍然存在，请检查日志输出以获取更多调试信息。

### 未来计划

本项目的后续优化方向包括功能扩展和性能优化。功能扩展方面，计划增加 WebSocket 支持以实现更好的实时通信，增加多模态支持包括图像和语音功能，实现文件上传和下载功能，以及增加本地缓存机制以减少网络请求。性能优化方面，计划实现更智能的连接池管理，增加请求批量处理能力，优化重试策略以提高成功率，以及实现本地响应缓存。

## 许可证

本项目仅供学习和研究使用。

## 致谢

感谢 Trae CN 团队提供了优秀的 AI 开发工具。本项目的逆向工程工作基于对公开日志和配置文件的分析，旨在促进对相关技术的理解和学习。

# Krita AI Copilot 插件第一阶段实现方案

本方案旨在跑通 Krita 的原生 UI 面板开发以及与 FastAPI 后端之间的异步文字通信。

## 用户审核项

> [!IMPORTANT]
> 1. **Krita 插件目录路径**：在 Windows 系统中，Krita 插件存放在 `%APPDATA%\krita\pykrita`。我们将在工作区中编写所有的代码，并提供一个自动化部署脚本 `deploy.py`，将插件文件一键复制到 Krita 的插件路径中，避免手动复制出错。
> 2. **异步网络请求**：我们将使用 PyQt5 的 `QNetworkAccessManager` 和 `QNetworkRequest` 来实现异步的网络请求。这种方式完全基于 Qt 的事件循环，不会阻塞 Krita 的主界面，相比 `QThread` 更加轻量且不容易出错。

## 待讨论问题

目前暂无未决的阻塞性问题，我们将直接实现一套稳定、美观的极简微信风格聊天面板。

---

## 拟议的修改和新增文件

我们将在工作区 `d:\workspace\Aura` 下创建以下结构：
- `ai_copilot.desktop`：Krita 插件配置文件。
- `ai_copilot/`：Krita 插件 Python 包文件夹。
  - `__init__.py`：包入口。
  - `ai_copilot.py`：插件核心扩展类。
  - `docker.py`：停靠面板 UI 及网络请求实现。
- `server.py`：FastAPI 后端。
- `deploy.py`：便捷的本地部署脚本，用于把工作区插件代码拷贝到 Krita 的 pykrita 目录中。

---

### [Krita Frontend Plugin]

#### [NEW] [ai_copilot.desktop](file:///d:/workspace/Aura/ai_copilot.desktop)
Krita 插件描述文件。告知 Krita 插件的名称、模块名和类型。

#### [NEW] [__init__.py](file:///d:/workspace/Aura/ai_copilot/__init__.py)
包初始化文件，导入核心 Extension。

#### [NEW] [ai_copilot.py](file:///d:/workspace/Aura/ai_copilot/ai_copilot.py)
继承自 `krita.Extension`，负责向 Krita 注册 DockWidget（停靠面板）。

#### [NEW] [docker.py](file:///d:/workspace/Aura/ai_copilot/docker.py)
继承自 `krita.DockWidget`。
- 构建 UI 面板：包含只读 `QTextBrowser`、单行输入框 `QLineEdit`、发送按钮 `QPushButton`。
- 网络逻辑：创建 `QNetworkAccessManager`，发起异步 POST 请求到 `http://127.0.0.1:8000/api/chat`。
- 处理返回结果并渲染 UI。

---

### [FastAPI Backend]

#### [NEW] [server.py](file:///d:/workspace/Aura/server.py)
- 使用 FastAPI 搭建。
- 开启 CORS 中间件，允许任意来源。
- 实现 `POST /api/chat` 接口，接收 `{"text": "..."}` 并打印，返回 `{"reply": "收到指令，准备执行..."}`。

---

### [Helper Scripts]

#### [NEW] [deploy.py](file:///d:/workspace/Aura/deploy.py)
- 自动定位到用户的 `%APPDATA%\krita\pykrita` 目录。
- 清理旧的 `ai_copilot` 文件夹和 `ai_copilot.desktop`。
- 将工作区中的最新插件代码拷贝过去。

---

## 验证计划

### 自动化与手动测试
1. **后端验证**：
   - 运行 `python server.py` 启动服务。
   - 使用 Powershell 或者 Python 脚本发送测试 POST 请求，验证返回 JSON 格式符合预期。
2. **部署插件**：
   - 运行 `python deploy.py` 将插件拷贝到 `%APPDATA%\krita\pykrita`。
3. **Krita 联调验证**：
   - 打开 Krita，在 `配置 Krita` -> `Python 插件管理器` 中启用 `AI Copilot`。
   - 重启 Krita，在 `设置` -> `面板` 勾选 `AI Copilot` 调出停靠窗。
   - 在输入框输入文本，点击发送，检查界面聊天内容变化，并观察 FastAPI 后端命令行输出以及 Krita 面板收到的回复。

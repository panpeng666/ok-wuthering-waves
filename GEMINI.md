# ok-ww 项目上下文

## 项目概览

**ok-ww** 是一个开源的、基于图像识别的 *鸣潮 (Wuthering Waves)* 自动化工具。它构建在 `ok-script` 框架之上，通过视觉信号识别游戏状态，并模拟用户交互（键盘/鼠标）来执行操作。它**不**注入代码或读取内存，严格在“表面”层级（UI 自动化）运行。

*   **语言:** Python 3.12
*   **核心框架:** `ok-script`
*   **关键技术:** OpenCV (图像处理), OpenVINO/ONNX (AI/OCR), PySide6 (GUI), PyWin32 (Windows 交互).
*   **平台:** Windows (由于游戏客户端和 `pywin32` 依赖，这是自动化的目标操作系统).

## 目录结构

*   `src/`: 主要源代码。
    *   `task/`: 具体自动化任务的实现 (例如 `DailyTask` (日常任务), `FarmEchoTask` (刷声骸), `AutoCombatTask` (自动战斗)).
    *   `char/`: 角色特定的逻辑和配置。
    *   `scene/`: 场景检测和管理 (例如 `WWScene`).
    *   `combat/`: 战斗逻辑。
    *   `echo/`: 声骸系统自动化逻辑。
    *   `globals.py`: 全局应用状态。
*   `assets/`: 资源文件，如用于模板匹配的图片 (`.png`)，ONNX 模型和配置文件。
*   `config.py`: 中心配置文件。定义了可用任务、窗口设置和全局选项。
*   `main.py`: 发布版本的入口点。
*   `main_debug.py`: 调试版本的入口点。
*   `tests/`: 单元和集成测试 (`Test*.py`).
*   `pyappify.yml`: `pyappify` 的配置 (可能用于构建独立可执行文件和处理更新)。

## 开发与使用

### 前置条件
*   Python 3.12
*   Windows 操作系统 (用于实际针对游戏的执行)。

### 安装设置
1.  **安装依赖:**
    ```bash
    pip install -r requirements.txt
    ```

### 运行应用
*   **发布模式:**
    ```bash
    python main.py
    ```
*   **调试模式:**
    ```bash
    python main_debug.py
    ```
*   **命令行参数:**
    *   `-t <N>` 或 `--task <N>`: 立即运行第 N 个任务。
    *   `-e` 或 `--exit`: 任务完成后退出。

### 测试
测试位于 `tests/` 目录下。
*   **运行所有测试:** (推测命令) 可能使用 `python -m unittest discover tests` 或运行单独的文件如 `python tests/TestEcho.py`。
*   **PowerShell 脚本:** 提供了 `run_tests.ps1` 用于在 Windows 上运行测试。

## 关键配置 (`config.py`)

*   **任务 (Tasks):** 定义在 `onetime_tasks` (一次性任务) 和 `trigger_tasks` (触发式任务) 列表中。
*   **窗口处理:** 配置在 `windows` 键下 (目标 exe: `Client-Win64-Shipping.exe`)。
*   **OCR/推理:** 配置在 `ocr` 和 `template_matching` 下。

## 架构说明

*   **基于任务 (Task-Based):** 应用程序围绕执行特定自动化序列的“任务 (Tasks)”构建。
*   **图像识别:** 严重依赖 `process_feature` 和模板匹配 (`assets/result.json`) 来理解游戏状态。
*   **安全自动化:** 强调非侵入式自动化（无内存读取），以便在宏工具的范围内尽可能遵守反作弊/服务条款。\n- Thu Dec 11 10:19:57 CST 2025: Optimized codebase documentation and configured git proxy.

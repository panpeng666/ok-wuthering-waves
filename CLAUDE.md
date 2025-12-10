```
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述
- 一个基于图像识别的鸣潮自动化程序，支持后台运行，基于 ok-script 框架开发
- 完全通过模拟常规用户界面与游戏交互，不修改游戏文件或数据

## 技术栈
- Python 3.12
- ok-script==1.0.15 (核心自动化框架)
- OpenVINO 2025.2.0 + YOLOv8 (目标检测)
- onnxocr-ppocrv4==0.0.5 (OCR)
- PySide6 (GUI)
- opencv-python==4.12.0.88 (图像处理)

## 项目结构
```
├── src/
│   ├── char/          # 各个角色的自动化逻辑
│   ├── combat/        # 战斗相关自动化
│   ├── scene/         # 场景检测和处理
│   ├── task/          # 各种自动化任务
│   ├── OpenVinoYolo8Detect.py  # YOLOv8 目标检测实现
│   └── globals.py     # 全局变量
├── main.py            # Release 版本入口
├── main_debug.py      # Debug 版本入口
├── config.py          # 配置文件
├── assets/            # 资源文件
└── requirements.txt   # 依赖
```

## 运行和开发命令
```bash
# 安装或更新依赖
pip install -r requirements.txt --upgrade

# 运行 Release 版本
python main.py

# 运行 Debug 版本
python main_debug.py
```

## 核心架构
- **主入口**: main.py 初始化 ok-script 的 OK 类并启动应用
- **配置**: config.py 包含所有游戏热键、目标检测和GUI等配置
- **自动化任务**: 定义在 src/task/ 目录，包括每日任务、自动战斗、自动拾取等
- **角色系统**: src/char/ 目录包含每个角色的技能序列和自动化逻辑
- **场景处理**: src.scene.WWScene 负责游戏场景的检测和切换

## 命令行参数
```bash
# 示例：启动后自动执行第一个任务（一条龙），并在任务完成后退出程序
ok-ww.exe -t 1 -e
```
- `-t` 或 `--task`: 启动后自动执行第 N 个任务。`1` 代表任务列表中的第一个
- `-e` 或 `--exit`: 任务执行完毕后自动退出程序

## 注意事项
- 项目仅支持 Python 3.12
- 所有自动化操作均通过模拟用户界面实现，不涉及内存读取或文件修改
- 需将游戏设置为默认按键配置或在工具中同步配置

## 常见任务
- 添加新角色: 在 src/char/ 目录下创建新的角色类，继承 BaseChar
- 添加新任务: 在 src/task/ 目录下创建新的任务类

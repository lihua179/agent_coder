# AI Agent Coder Framework

## 概述 (Overview)

这是一个基于大型语言模型 (LLM) 的 AI Agent 框架，旨在通过自然语言指令自动执行编码和系统管理任务。Agent 可以解析任务，与 LLM 交互生成操作计划（文件操作、程序执行），执行这些计划，并根据反馈进行调整。

该框架的核心设计思想是将配置、数据结构、API 交互、文件执行和程序执行等功能模块化，使其更易于维护和扩展。

## 主要特性 (Features)

*   **配置驱动**: 通过 `config.json` 文件集中管理 API 密钥、模型参数、工作路径、执行限制等，方便调整。
*   **任务管理**: 支持通过任务 ID (`--task_id`) 启动和管理不同的任务，每个任务拥有独立的工作目录和聊天记录。
*   **模块化设计**: 清晰分离了核心逻辑 (`agent.py`)、API 交互 (`chat_api.py`)、数据结构 (`data_struct.py`)、文件操作 (`file_exec.py`) 和程序执行 (`program_exec.py`)。
*   **文件操作**: 支持创建、删除、读取、替换文件内容以及创建/删除目录，包含路径安全检查和可配置的文件读取限制。
*   **程序执行**: 支持执行外部命令/程序，可并行执行多个命令，包含超时控制、输出/错误捕获和可选的周期性监控反馈机制。
*   **LLM 交互**: 封装了与 OpenAI 兼容 API 的交互逻辑，包括流式响应处理、上下文窗口管理和基本的错误重试。
*   **状态持久化**: 将每个任务的聊天记录保存到 JSON 文件中，方便调试和恢复。

## 模块说明 (Modules Description)

*   **`config.json`**: 配置文件，包含所有可调参数。
*   **`agent.py`**: Agent 的主控制流。加载配置，初始化组件，管理任务循环，解析 LLM 响应，调用执行器，处理反馈。
*   **`chat_api.py`**: 负责与 LLM API 通信。构建请求，发送请求，处理流式响应，管理对话历史上下文。
*   **`data_struct.py`**: 定义 Agent 内部及与 LLM 交互所使用的所有数据类 (Dataclasses) 和枚举 (Enums)，如操作请求、反馈结果等。
*   **`file_exec.py`**: `FileExecutor` 类，负责执行所有文件系统相关的操作。根据 `config.json` 中的设置进行操作。
*   **`program_exec.py`**: `CommandExecutor` 和 `ParallelExecutor` 类，负责执行外部命令。`CommandExecutor` 处理单个命令，`ParallelExecutor` 管理多个命令的并行执行和监控。`ProgramCheck` 类用于实现周期性反馈。

## 配置 (`config.json`)

配置文件 `config.json` 分为几个主要部分：

*   **`api`**: LLM API 相关设置 (密钥 `api_key`, `base_url`, `model`, `timeout`)。
*   **`paths`**: 工作目录 (`work_dir`)、任务目录 (`task_dir`)、Prompt 文件 (`prompt_file`) 的相对路径。
*   **`agent`**: Agent 行为设置 (聊天记录保存数量 `save_chat_count`, 初始上下文消息数 `initial_context_messages`)。
*   **`file_execution`**: 文件操作相关设置 (最大读取长度 `read_max_length`, 应用长度限制的文件类型 `read_limit_extensions`, 允许读取的文件类型 `allowed_read_extensions`, 默认编码 `default_encoding`)。
*   **`program_execution`**: 程序执行相关设置 (默认超时 `default_timeout`, 监控线程检查间隔 `monitor_interval`, 反馈给 AI 的检查间隔 `feedback_check_interval`, 输出缓存大小限制 `output_buffer_limit`)。

**注意**: 首次使用前，请务必在 `config.json` 中填入有效的 `api_key`。

## 使用方法 (Usage)

1.  **配置**: 确保 `config.json` 文件存在于 `agent.py` 同级目录下，并已填入正确的 API 密钥和所需配置。
2.  **安装依赖**: 确保已安装所需的 Python 库 (主要是 `openai`):
    ```bash
    pip install openai
    ```
   3.  **运行 Agent**: 在 `ai/` 目录下执行以下命令启动 Agent 并指定任务 ID：
```        
    # -*- coding: utf-8 -*-
 
    import json
    import re
    import os
    import argparse  # Import argparse for potential command-line overrides
    import logging  # Added logging
    from typing import Any, Dict, List, Optional  # Added Optional
    from agent_coder import AutoCoder
    logger = logging.getLogger(__name__)  # Module-level logger
    
    
    def setup_logging(config: Dict[str, Any]):
        """Configures logging based on the provided configuration."""
        log_config = config.get('logging', {})
        log_level_str = log_config.get('log_level', 'INFO').upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        log_format = log_config.get('log_format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        log_date_format = log_config.get('log_date_format', '%Y-%m-%d %H:%M:%S')
        log_file = log_config.get('log_file')  # Log file path is optional
    
        formatter = logging.Formatter(log_format, datefmt=log_date_format)
    
        # Clear existing handlers to avoid duplicate logs if re-configured
        if logger.hasHandlers():
            logger.handlers.clear()
    
        # Configure console handler
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    
        # Configure file handler if log_file is specified
        if log_file:
            try:
                # Ensure log directory exists if log_file path includes directories
                log_dir = os.path.dirname(log_file)
                if log_dir and not os.path.exists(log_dir):
                    os.makedirs(log_dir)
                fh = logging.FileHandler(log_file, encoding='utf-8')
                fh.setFormatter(formatter)
                logger.addHandler(fh)
                logger.info(f"Logging to file: {log_file}")
            except Exception as e:
                logger.error(f"Failed to configure file logging to {log_file}: {e}")
    
        logger.setLevel(log_level)
        logger.info(f"Logging initialized. Level: {log_level_str}")
    
    
    DEFAULT_CONFIG_PATH = 'config.json'
    
    
    def load_config(config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
        """Loads configuration from a JSON file."""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            # Basic validation (can be expanded)
            if 'api' not in config or 'paths' not in config or 'agent' not in config:
                raise ValueError("Config file missing required top-level keys: 'api', 'paths', 'agent'")
            return config
        except json.JSONDecodeError as e:
            raise ValueError(f"Error decoding JSON from config file {config_path}: {e}")
        except Exception as e:
            raise RuntimeError(f"Error loading config file {config_path}: {e}")
    
    
    # --- JSON Extraction (Improved) ---
    def extract_json_content(ai_response: str) -> Dict[str, Any]:
        """
        提取AI返回的结构化JSON内容。
    
        参数:
        ai_response (str): AI返回的内容，包含JSON格式的结构化文本。
    
        返回:
        Dict[str, Any]: 提取的结构化字段字典。
        """
        # 使用正则表达式提取JSON内容
        match = re.search(r'#####--\s*(.*?)\s*--#####', ai_response, re.DOTALL)
    
        if match:
            json_content = match.group(1)  # 提取匹配的内容
            try:
                # 尝试将字符串解析为JSON对象
                structured_data = json.loads(json_content)
                return structured_data
            except json.JSONDecodeError as e:
                raise ValueError(f"无法正确解析提取的JSON内容，确保其为有效的JSON格式（####--json内容--####）。{e}")
        else:
            # Keep original error message for consistency if needed, or improve it
            raise ValueError("未找到有效的JSON结构化内容（单个），确保其为有效的JSON格式（#####--json内容--#####）。")


    def main():
        """Main function to load config, setup logging, and run the AutoCoder."""
        # parser = argparse.ArgumentParser(description="AutoCoder Agent")
        # parser.add_argument('--config', type=str, default=DEFAULT_CONFIG_PATH, help=f"Path to configuration file (default: {DEFAULT_CONFIG_PATH})")
        # parser.add_argument('--task_id', type=str, required=True, help="Unique ID for the current task")
        # parser.add_argument('--request', type=str, default="", help="Initial user request/prompt for the task")
        # # Add other command-line arguments if.txt needed (e.g., overriding work_dir)
        #
        # args = parser.parse_args()
        config_path = fr'C:\Users\config.json'
        task_id = '001'
        try:
            config = load_config(config_path)
            # Setup logging right after loading config
            setup_logging(config)
            logger.info("Configuration loaded successfully.")
        except (FileNotFoundError, ValueError, RuntimeError) as e:
            # Logger might not be set up, so print is safer here
            print(f"CRITICAL: Error loading configuration: {e}")
            # Attempt to log as well, might fail if setup_logging failed
            try:
                logger.critical(f"Error loading configuration: {e}", exc_info=True)
            except Exception:
                pass
            return  # Exit if config fails
    
        logger.debug(
            f"Loaded config: {json.dumps(config, indent=2, ensure_ascii=False)}")  # Log loaded config at DEBUG level
    
        # You might want to allow overriding work_dir via command line too
        # config['paths']['work_dir'] = args.work_dir if.txt args.work_dir else config['paths']['work_dir']
    
        # Use initial request from command line if.txt provided
        initial_content = f"请你在{config['paths']['work_dir']}下实现贪吃蛇游戏"  # Default if no request given
        logger.info(f"Starting AutoCoder for task_id: {task_id}")
        logger.debug(f"Initial request content (first 100 chars): {initial_content[:100]}")
    
        try:
            # Pass the config file path to the AutoCoder constructor
            auto_coder = AutoCoder(config=config,
                                   config_path=config_path,  # Pass the actual config path
                                   task_id=task_id,
                                   initial_chat_content=initial_content)
            auto_coder.run()
            logger.info(f"AutoCoder run finished for task_id: {task_id}")
        except (FileNotFoundError, ValueError, RuntimeError) as e:
            # These are likely setup errors before the main loop
            logger.critical(f"Setup error during AutoCoder initialization: {e}", exc_info=True)
        except Exception as e:
            # Catch-all for unexpected errors during the run
            logger.critical(f"An unexpected error occurred during AutoCoder execution: {e}", exc_info=True)


    if __name__ == "__main__":
        main()
   ```



#####   Agent 将会：
    *   加载 `config.json`。
    *   在 `paths.task_dir` 下创建或使用 `<your_task_id>` 目录。
    *   加载该任务的聊天记录（如果存在）。
    *   加载 `paths.prompt_file` 中的系统 Prompt。
    *   开始与 LLM 交互以执行 `task.txt` (如果存在于任务目录中) 或等待用户输入初始任务。

## 依赖 (Dependencies)

*   Python 3.7+
*   `openai` library




# -*- coding: utf-8 -*-
"""
@author: Zed
@file: main.py
@time: 2025/4/7 22:54
@describe:自定义描述
"""
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

# -*- coding: utf-8 -*-
"""
@author: Zed
@file: tool.py
@time: 2025/4/8 16:13
@describe:自定义描述
"""
import logging
# --- Logging Setup ---
logger = logging.getLogger() # Module-level logger
def setup_logging(logger):
    """Configures logging based on the provided configuration."""
    log_config = {
        "log_file": "agent_run.log",
        "log_level": "INFO",
        "log_format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "log_date_format": "%Y-%m-%d %H:%M:%S"
    }

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
setup_logging(logger)



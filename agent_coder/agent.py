# -*- coding: utf-8 -*-
import json
import re
import os
import argparse # Import argparse for potential command-line overrides
import logging # Added logging
import uuid # For generating unique request IDs for feedback

from typing import Any, Dict, List, Optional # Added Optional
# Use relative imports for modules within the same package
from .chat_api import ChatAPI
from .file_exec import FileExecutor
from .program_exec import ParallelExecutor, ProgramCheck
from .data_struct import (
    Parser,
    OperationResponse,
    ProgramCheckFeedback, # Added
    ProgramCheckRequest,  # Added
    ProgramCheckInput,    # Added
    FileOperationFeedback,
    ProgramResult, # Added for type hinting in OperationResponse
    FeedbackStatus
)

# --- Logging Setup ---
logger = logging.getLogger(__name__) # Module-level logger

def setup_logging(config: Dict[str, Any]):
    """Configures logging based on the provided configuration."""
    log_config = config.get('logging', {})
    log_level_str = log_config.get('log_level', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    log_format = log_config.get('log_format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_date_format = log_config.get('log_date_format', '%Y-%m-%d %H:%M:%S')
    log_file = log_config.get('log_file') # Log file path is optional

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


# --- Configuration Loading ---
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


def extract_json_list(ai_response: str) -> List[Dict[str, Any]]:
    """
    提取AI返回的包含一个或多个JSON块的列表。

    参数:
    ai_response (str): AI返回的内容，包含JSON格式的结构化文本。

    返回:
    List[Dict[str, Any]]: 包含提取的结构化字段字典的列表。
    """
    pattern = r'#####--(.*?)--#####'
    matches = re.findall(pattern, ai_response, re.DOTALL)

    if not matches:
        raise ValueError("未找到有效的JSON结构化内容（列表），确保其为有效的JSON格式（#####--json内容--#####）。")

    result_list = []
    errors = []
    for i, json_content in enumerate(matches):
        try:
            # 使用 json.loads() 替换 eval()
            structured_data = json.loads(json_content.strip())
            result_list.append(structured_data)
        except json.JSONDecodeError as e:
            error_msg = f"无法解析第 {i+1} 个JSON块: {e}. 内容: '{json_content[:100]}...'"
            logger.error(error_msg) # Use logger
            errors.append(error_msg)
            # Decide if you want to continue or raise immediately
            # continue
        except Exception as e: # Catch other potential errors during parsing
            error_msg = f"解析第 {i+1} 个JSON块时发生意外错误: {e}. 内容: '{json_content[:100]}...'"
            logger.error(error_msg) # Use logger
            errors.append(error_msg)
            # continue

    # Optionally raise an error if.txt any parsing failed, or return partial results
    # if.txt errors:
    #     raise ValueError(f"解析JSON列表时出错:\n" + "\n".join(errors))

    return result_list


class AutoCoder:
    # Modify __init__ to accept config_path
    def __init__(self, config: Dict[str, Any], config_path: str, task_id: str, initial_chat_content: str = ''):
        self.config = config
        self.config_path = config_path # Store config path
        self.task_id = task_id
        logger.info(f"Initializing AutoCoder for task_id: {task_id} using config: {config_path}")
        self.work_dir = config['paths']['work_dir'] # Use work_dir from config
        self.task_dir = config['paths']['task_dir'] # Use task_dir from config
        self.chat_content = initial_chat_content  # Initial user request
        logger.debug(f"Work directory set to: {self.work_dir}")
        logger.debug(f"Task directory set to: {self.task_dir}")

        # Ensure task-specific directory exists
        self.current_task_path = os.path.join(self.task_dir, self.task_id)
        os.makedirs(self.current_task_path, exist_ok=True)
        logger.info(f"Ensured task directory exists: {self.current_task_path}")

        # --- Load prompt (resolve path relative to config file) ---
        config_dir = os.path.dirname(os.path.abspath(self.config_path))
        prompt_path_relative = config['paths']['prompt_file']
        prompt_path = os.path.abspath(os.path.join(config_dir, prompt_path_relative))

        logger.info(f"Attempting to load prompt from resolved path: {prompt_path}")
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_content = f.read()
        except FileNotFoundError:
             logger.error(f"Prompt file not found: {prompt_path}")
             raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        except Exception as e:
             logger.error(f"Error reading prompt file {prompt_path}: {e}")
             raise RuntimeError(f"Error reading prompt file {prompt_path}: {e}")

        # Initialize components using config
        logger.info("Initializing components (ChatAPI, FileExecutor, ParallelExecutor)...")
        self.chat_api = ChatAPI(
            api_key=config['api']['api_key'],
            base_url=config['api']['base_url'],
            model=config['api']['model'],
            timeout=config['api'].get('timeout', 1200.0), # Use get for optional timeout
            prompt=prompt_content,
            save_func=self.save_chat_his,
            save_chat_count=config['agent']['save_chat_count'],
            initial_context_messages=config['agent']['initial_context_messages'] # Pass this new config
        )
        self.file_exec = FileExecutor(self.work_dir,self.config) # Pass base work directory
        # Initialize ProgramCheck with the callback method
        self.cmd_check = ProgramCheck(config=self.config, send_feedback=self.send_program_feedback_to_ai)
        # Initialize ParallelExecutor with the ProgramCheck instance
        self.cmd_exec = ParallelExecutor(config=self.config, program_check=self.cmd_check)

        # Load history if it exists
        self.load_his_chat()

    def _get_chat_history_path(self) -> str:
        """Returns the path to the chat history file for the current task."""
        return os.path.join(self.current_task_path, 'chat_his_list.txt')

    def _get_summary_path(self) -> str:
        """Returns the path to the summary file for the current task."""
        return os.path.join(self.current_task_path, 'summary.txt')

    def load_his_chat(self):
        """Loads chat history from the task-specific file."""
        history_path = self._get_chat_history_path()
        if os.path.exists(history_path):
            try:
                with open(history_path, 'r', encoding='utf-8', errors='ignore') as f:
                    res = f.read()
                # Use json.loads for safety, assuming history is stored as JSON list
                loaded_req = json.loads(res)
                if isinstance(loaded_req, list):
                     self.chat_api.req = loaded_req
                     logger.info(f"Loaded {len(self.chat_api.req)} messages from history: {history_path}")
                else:
                     logger.warning(f"Chat history file {history_path} does not contain a valid list. Starting fresh.")
                     # Keep the initial prompt from __init__
            except json.JSONDecodeError:
                logger.warning(f"Could not decode JSON from chat history file {history_path}. Starting fresh.")
            except Exception as e:
                logger.warning(f"Error loading chat history from {history_path}: {e}. Starting fresh.")
        else:
            logger.info(f"No chat history found at {history_path}. Starting fresh.")


    def save_chat_his(self):
        """Saves the current chat history to the task-specific file."""
        chat_his_list = self.chat_api.req
        path = self._get_chat_history_path()
        try:
            # Save as JSON for easier and safer loading
            with open(path, 'w', encoding='utf-8', errors='ignore') as f:
                json.dump(chat_his_list, f, ensure_ascii=False, indent=2) # Use indent for readability
            logger.debug(f"Chat history saved to {path}")
        except Exception as e:
            logger.error(f"Error saving chat history to {path}: {e}")


    def save_tail(self, summary: str):
        """Saves the final chat history and summary."""
        logger.info('Task finished. Saving final state.')
        self.save_chat_his() # Save history first
        summary_path = self._get_summary_path()
        logger.info(f"Saving summary to: {summary_path}")
        try:
            with open(summary_path, 'w', encoding='utf-8', errors='ignore') as f:
                f.write(summary)
            logger.info(f"Summary saved successfully.")
        except Exception as e:
            logger.error(f"Error saving summary to {summary_path}: {e}")


    def send_program_feedback_to_ai(self, feedback_payload: Dict[str, Dict]) -> Optional[List[str]]:
        """
        Callback function for ProgramCheck. Sends program output to AI and handles interrupt commands.

        Args:
            feedback_payload (Dict[str, Dict]): Dictionary mapping program names to their
                                                ProgramCheckFeedback data (as dicts).

        Returns:
            Optional[List[str]]: List of program names AI requested to terminate.
        """
        if not feedback_payload:
            return None

        logger.info(f"Sending program feedback to AI for programs: {list(feedback_payload.keys())}")
        # Format the feedback for the AI. Wrap it to indicate it's program output.
        # Using a simple structure here, might need refinement based on prompt.
        feedback_message = {
            "type": "program_runtime_feedback",
            "programs": feedback_payload,
            "request_id": f"fb-{uuid.uuid4()}" # Add a unique ID for this feedback message
        }
        feedback_str = json.dumps(feedback_message, ensure_ascii=False, indent=2)
        logger.debug(f"Formatted feedback for AI:\n{feedback_str}")

        try:
            # Send feedback to AI and get response
            # Note: This call is synchronous within the monitor thread's callback.
            # Consider making chat_api.chat async or running this in a separate thread
            # if AI response time becomes a bottleneck for monitoring.
            ai_response_text = self.chat_api.chat(f"#####--\n{feedback_str}\n--#####") # Wrap in delimiters
            logger.debug(f"Received AI response to feedback: {ai_response_text}...")

            # Parse AI response to check for termination commands
            terminate_list = []
            try:
                # AI might respond with one or more JSON blocks
                structured_responses = extract_json_list(ai_response_text)
                for response_data in structured_responses:
                    # Check if it's a program check request (termination instruction)
                    if response_data.get('type') == 'check_program':
                        # Use the existing parser logic
                        parsed_request = Parser.parse_request(response_data)
                        if isinstance(parsed_request, ProgramCheckRequest):
                            logger.info(f"Received program check request from AI: {parsed_request}")
                            for op in parsed_request.program_operations:
                                if isinstance(op, ProgramCheckInput) and op.terminal: # Check type just in case parser changes
                                    logger.info(f"AI requested termination for program: {op.name} (Reason: {op.reason})")
                                    terminate_list.append(op.name)
                        else:
                             logger.warning(f"Parsed 'check_program' type but got unexpected object: {type(parsed_request)}")
                    # else: ignore other response types in this context
            except ValueError as e:
                pass
                # logger.info(f"ai connect: {ai_response_text}")
            except Exception as e:
                 logger.error(f"Error processing AI response to feedback: {e}", exc_info=True)


            return terminate_list if terminate_list else None

        except Exception as e:
            logger.error(f"Error sending feedback to AI or receiving response: {e}", exc_info=True)
            return None # Don't terminate anything if communication fails


    def run(self):
        """Main execution loop for the AutoCoder agent."""
        logger.info(f"Starting main execution loop for task: {self.task_id}")
        # Agent starts with the initial user request or loaded history
        # If history is loaded, self.chat_content might be ignored unless explicitly used
        current_input = self.chat_content # Start with the initial request if no history or if logic dictates
        logger.debug(f"Initial input for loop: {current_input[:200]}...")

        finish = False
        loop_count = 0
        while not finish:
            loop_count += 1
            logger.info(f"--- Agent Loop Iteration {loop_count} ---")
            logger.debug(f"Sending input to LLM: {current_input[:500]}...")
            # Send the current input (either initial request or feedback from previous step)
            response = self.chat_api.chat(current_input)
            logger.debug(f"Received response from LLM: {response[:500]}...")
            # History is saved automatically by chat_api via save_func

            structured_data_list = []
            next_input_parts = [] # Collect feedback for the next iteration

            try:
                # Use the improved function to extract potentially multiple JSON blocks
                structured_data_list = extract_json_list(response)
            except ValueError as e:
                # Handle case where no valid JSON blocks are found in the response
                error_message = f"ValueError: {e}\n[系统报错]：AI响应中未找到有效的结构化文本（#####--...--#####）。请确保AI按要求格式返回。原始响应: {response[:500]}..."
                logger.error(error_message)
                current_input = error_message # Send error back to AI
                continue # Skip processing this response and ask AI again

            logger.info(f'Received {len(structured_data_list)} command blocks from AI.')

            # Process each structured command block
            for i, structured_data in enumerate(structured_data_list):
                logger.info(f"--- Processing command block {i+1}/{len(structured_data_list)} ---")
                try:
                    # Log the raw command block at DEBUG level
                    logger.debug(f"Raw command block {i+1}: {json.dumps(structured_data, indent=2, ensure_ascii=False)}")
                except Exception: # Fallback for non-serializable data if any
                    logger.debug(f"Raw command block {i+1} (non-serializable): {structured_data}")

                try:
                    operation_req = Parser.parse_request(structured_data)
                    logger.info(f"Parsed command {i+1}: Type='{operation_req.type}', Reason='{getattr(operation_req, 'reason', 'N/A')}'")
                except (TypeError, ValueError, KeyError) as e:
                    error_message = f"[系统报错] Error parsing command block {i+1}: {e}. Content: {str(structured_data)[:200]}..."
                    logger.error(error_message)
                    next_input_parts.append(error_message)
                    continue # Skip this invalid command

                # Check for finish command
                if operation_req.type.lower() in ['finish', 'completed']:
                    summary = getattr(operation_req, 'summary', "任务完成，无详细摘要。") # Get summary safely
                    logger.info(f"Finish command received. Summary: {summary}")
                    self.save_tail(summary)
                    finish = True
                    break # Exit the inner loop over commands

                # --- Execute File Operations ---
                file_results = []
                if hasattr(operation_req, 'file_operations') and operation_req.file_operations:
                    logger.info(f"Executing {len(operation_req.file_operations)} file operations...")
                    for action in operation_req.file_operations:
                        try:
                            logger.debug(f"  Attempting file op: {action.action_type} on {action.path}")
                            file_op_feed: FileOperationFeedback = self.file_exec.execute_file_operation(action)
                            file_results.append(file_op_feed)
                            log_level = logging.INFO if file_op_feed.status else logging.WARNING
                            logger.log(log_level, f"    - File op {action.action_type} {action.path}: {'Success' if file_op_feed.action_type else 'Failed'}. Msg: {file_op_feed.content}")
                        except Exception as e:
                            logger.error(f"    - Unhandled exception during file op {action.action_type} {action.path}: {e}", exc_info=True)
                            file_results.append(FileOperationFeedback(path=action.path,  status=FeedbackStatus.FAILURE, error_detail=f"Unhandled exception: {e}"))
                else:
                     logger.info("No file operations requested.")


                # --- Execute Program Operations ---
                program_results = []
                if hasattr(operation_req, 'program_operations') and operation_req.program_operations:
                    logger.info(f"Executing {len(operation_req.program_operations)} program operations...")
                    try:
                        # Assuming execute_programs returns a dict {id: result}
                        # This call now runs with the background monitor thread handling
                        # real-time feedback via self.send_program_feedback_to_ai
                        exec_results_dict: Dict[str, ProgramResult] = self.cmd_exec.execute_programs(operation_req.program_operations)
                        program_results_list: List[ProgramResult] = list(exec_results_dict.values()) # Convert dict to list of ProgramResult objects
                        for res in program_results_list:
                             # Determine log level based on final status
                             log_level = logging.INFO
                             if res.status not in ['completed', 'terminated']: # Consider terminated by AI as non-error
                                 log_level = logging.WARNING
                             logger.log(log_level, f"    - Program '{res.name}' final status: {res.status} (Code: {res.return_code}, Time: {res.exec_time}s). Output snippet: {res.stdout[:100]}...")
                    except Exception as e:
                         logger.error(f"Unhandled exception during program execution block: {e}", exc_info=True)
                         # Create error feedback for each requested program op if needed
                         program_results_list = [ProgramResult(name=op.name, stdout="", stderr=f"Unhandled exception: {e}", exec_time=0.0, return_code=-1, status="failed") for op in operation_req.program_operations]

                else:
                     logger.info("No program operations requested.")
                     program_results_list=[]


                # --- Construct Feedback for AI (using final results) ---
                operation_res = OperationResponse(
                    request_id=getattr(operation_req, 'request_id', f'op-{uuid.uuid4()}'), # Generate ID if missing
                    reason=getattr(operation_req, 'reason', ''), # Include AI's reason
                    file_actions_result=[f.to_dict() for f in file_results], # Convert feedback objects to dicts
                    program_execs_result=[p.to_json() for p in program_results_list] # Convert result objects to dicts
                )
                # Wrap the final operation response in delimiters for the AI
                feedback_text = f"#####--\n{operation_res.to_structured_text()}\n--#####"
                next_input_parts.append(feedback_text)

                logger.info(f"--- Command block {i+1} processing complete ---")
                logger.debug(f"Feedback for AI (block {i+1}):\n{feedback_text}")


            if finish: # If finish command was received in the loop
                logger.info("Finish command processed, exiting main loop.")
                break

            # Combine all feedback for the next turn
            current_input = "\n".join(next_input_parts)
            if not current_input: # Handle case where all commands failed parsing
                 logger.warning("All command blocks failed parsing. Sending system prompt.")
                 current_input = "[系统提示] 所有收到的指令都无法解析，请重新发送指令。"

            logger.info('Finished processing all command blocks for this iteration.')


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
        return # Exit if config fails

    logger.debug(f"Loaded config: {json.dumps(config, indent=2, ensure_ascii=False)}") # Log loaded config at DEBUG level

    # You might want to allow overriding work_dir via command line too
    # config['paths']['work_dir'] = args.work_dir if.txt args.work_dir else config['paths']['work_dir']


    # Use initial request from command line if.txt provided
    initial_content = f"请你在{config['paths']['work_dir']}下实现贪吃蛇游戏" # Default if no request given
    logger.info(f"Starting AutoCoder for task_id: {task_id}")
    logger.debug(f"Initial request content (first 100 chars): {initial_content[:100]}")

    try:
        # Pass the config file path to the AutoCoder constructor
        auto_coder = AutoCoder(config=config,
                               config_path=config_path, # Pass the actual config path
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

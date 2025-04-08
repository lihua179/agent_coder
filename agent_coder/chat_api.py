# -*- coding: utf-8 -*-
"""
@author: Zed
@file: chat_api.txt
@time: 2024/11/13 0:46
@describe: 提供与外部对话的回调函数接口
"""

import sys
# import logging # Added logging
from openai import OpenAI
import time # Added missing time import (used later)
import json # Added missing json import (used later)
from typing import List, Dict # Added missing typing import
from .tool import logger
import openai
# AProject/A/aaa世界规律/期货认知/程序/ai/code_agent/main_pro/CodeAgent/api/chat_api.py

__all__ = [
    "ChatAPI",
    "CharPrinter"
]




# 其他代码...
class CharPrinter:
    def __init__(self, max_width=40):
        self.max_width = max_width
        self.buffer = []  # 缓存当前行的字符列表
        self.visible_length = 0  # 当前行可见字符长度

    def _is_ansi(self, char):
        """判断是否是ANSI控制符"""
        return '\x1b' <= char <= '\x1f' or (char == '\\' and len(self.buffer) > 0 and self.buffer[-1] == '\\')

    def add_char(self, char):
        """添加单个字符到输出缓冲区"""
        try:
            if char in ('\n', '\r'):
                self.flush()
                self.buffer.append(char)
                return
        except UnicodeEncodeError as e:
            print(e)
            return

        # 计算新增字符的可见长度
        add_len = 1 if not self._is_ansi(char) else 0
        new_visible = self.visible_length + add_len

        # 处理自动换行
        if new_visible > self.max_width:
            self.flush()

        self.buffer.append(char)
        self.visible_length = new_visible

    def flush(self):
        """强制刷新当前行"""
        if self.buffer:
            try:
                # Note: CharPrinter still writes directly to stdout for streaming effect.
                # Logging individual characters might be too verbose.
                # We will log errors and key events in ChatAPI instead.
                sys.stdout.write(''.join(self.buffer))
                sys.stdout.flush()
            except UnicodeEncodeError as e:
                # Log the error instead of just printing
                logger.warning(f"UnicodeEncodeError in CharPrinter.flush: {e}. Skipping problematic characters.")
                pass # Continue execution
            self.buffer = []
            self.visible_length = 0

    def dynamic_single_callback(self, c):
        self.add_char(c)
        self.flush()


class ChatAPI:
    def __init__(self, api_key: str, model: str, base_url: str, prompt: str,
                 timeout: float = 1200.0, # Added timeout
                 save_chat_count: int = 20,
                 initial_context_messages: int = 5, # Added initial context config
                 callback_content=None, callback_reason_content=None, save_func=None):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout # Store timeout
        self.prompt_message = {"role": 'system', "content": prompt}
        self.req = [self.prompt_message] # Start with only the system prompt
        self.printer = CharPrinter(max_width=40)  # Increased default width slightly
        self.callback_content = callback_content
        self.callback_reason_content = callback_reason_content
        self.save_func = save_func
        self.save_chat_count = save_chat_count
        self.initial_context_messages = initial_context_messages # Store initial context count
        logger.info(f"ChatAPI initialized with model: {self.model}, base_url: {self.base_url}")
        logger.debug(f"Timeout: {self.timeout}, Save Count: {self.save_chat_count}, Initial Context: {self.initial_context_messages}")

    def add_assistant_message(self, assistant_response: str):
        """Adds an assistant message to the request history."""
        logger.debug(f"Adding assistant message (len: {len(assistant_response)}): {assistant_response[:100]}...")
        if assistant_response is not None: # Ensure content is not None
            self.req.append({'role': 'assistant', 'content': assistant_response})

    def add_user_message(self, message: str):
        """Adds a user message to the request history."""
        logger.debug(f"Adding user message (len: {len(message)}): {message[:100]}...")
        if message is not None: # Ensure content is not None
            self.req.append({'role': 'user', 'content': message})

    def _prepare_messages_for_api(self) -> List[Dict[str, str]]:
        """Prepares the list of messages for the API call, applying context window logic."""
        # Always include the system prompt
        if not self.req or self.req[0]['role'] != 'system':
             # Should not happen if initialized correctly, but as a safeguard
             messages_to_send = [self.prompt_message] + self.req
        else:
             messages_to_send = list(self.req) # Create a copy

        # Apply context window logic if history exceeds the limit
        # Limit is system_prompt + (save_chat_count * 2) for user/assistant pairs
        max_messages = 1 + (self.save_chat_count * 2)
        if len(messages_to_send) > max_messages:
            # Keep system prompt, initial context messages (if any), and the latest messages
            initial_context_count = min(self.initial_context_messages, len(messages_to_send) - 1) # Number of messages after system prompt
            latest_count = max_messages - 1 - initial_context_count # Number of latest messages to keep

            if latest_count < 0: # Ensure latest_count is not negative
                 latest_count = 0

            # Construct the message list
            preserved_initial = messages_to_send[1 : 1 + initial_context_count]
            preserved_latest = messages_to_send[-latest_count:] if latest_count > 0 else []

            messages_to_send = [messages_to_send[0]] + preserved_initial + preserved_latest
            logger.info(f"Context limited: Sending {len(messages_to_send)} messages (System + {len(preserved_initial)} initial + {len(preserved_latest)} latest).")

        logger.debug(f"Prepared {len(messages_to_send)} messages for API call.")
        return messages_to_send


    def get_response(self):
        """Gets response from the OpenAI compatible API."""
        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout
        )
        logger.info(f"Sending request to LLM: model={self.model}")

        messages_to_send = self._prepare_messages_for_api()
        logger.debug(f"Messages being sent to API: {json.dumps(messages_to_send, indent=2, ensure_ascii=False)}")

        try:
            responses = client.chat.completions.create(
                model=self.model,
                messages=messages_to_send,
                stream=True
                # max_tokens can be added here if needed
            )
            logger.info("API request successful, streaming response...")
        except openai.InternalServerError as e:
            time.sleep(5)
            logger.error(f"API call failed: {e}", exc_info=True)
            raise  # Re-raise the exception to be handled by the caller (.chat method)
        except openai.RateLimitError as e:
            time.sleep(5)
            logger.error(f"API call failed: {e}", exc_info=True)
            raise  # Re-raise the exception to be handled by the caller (.chat method)
        except Exception as api_error:
            logger.error(f"API call failed: {api_error}", exc_info=True)
            raise # Re-raise the exception to be handled by the caller (.chat method)

        res_total = ''
        # Keep the print for visual feedback during streaming
        print("\nAI Response: ", end="")
        stream_start_time = time.time()
        first_token_received = False
        # The loop starts here
        for response in responses:
            # Handle potential reasoning content (specific to some models)
            # Use getattr for safer access in case delta structure varies
            reason = getattr(response.choices[0].delta, 'reasoning_content', None)
            if reason:
                self.reason_callback(reason)

            # Handle main content
            res = getattr(response.choices[0].delta, 'content', None)
            if res:
                res_total += res
                self.callback_stream_single(res)

                if not first_token_received:
                    first_token_time = time.time() - stream_start_time
                    logger.info(f"First token received in {first_token_time:.2f} seconds.")
                    first_token_received = True

        stream_duration = time.time() - stream_start_time
        logger.info(f"Finished streaming response. Total length: {len(res_total)}, Duration: {stream_duration:.2f} seconds.")
        print() # Newline after streaming finishes
        return res_total

    def chat(self, user_message: str) -> str:
        """Handles a user message, gets the AI response, and updates history."""
        self.add_user_message(user_message)
        assistant_response = "" # Initialize response
        try:
            assistant_response = self.get_response()
        except Exception as e:
            logger.error(f"Error getting response from API: {e}", exc_info=True)
            # Attempt to truncate user message for retry if it's very long
            if len(self.req) > 1: # Ensure there's a user message to modify
                 last_user_msg_index = -1
                 # Find the last user message index (might not be -1 if assistant failed before adding)
                 for i in range(len(self.req) - 1, 0, -1):
                      if self.req[i]['role'] == 'user':
                           last_user_msg_index = i
                           break

                 if last_user_msg_index != -1:
                      original_user_message = self.req[last_user_msg_index]['content']
                      if len(original_user_message) > 2000: # Arbitrary length threshold for truncation
                           truncated_message = (
                               original_user_message[:1000] +
                               f'\n\n\n...[系统截断，省略 {len(original_user_message)-2000} 字符]...\n\n\n' +
                               original_user_message[-1000:] +
                               f'\n[系统备注]: 上次调用失败 - {e}'
                           )
                           self.req[last_user_msg_index]['content'] = truncated_message
                           logger.warning(f"API call failed. Retrying with truncated user message (original len: {len(original_user_message)}). Error: {e}")
                           try:
                               assistant_response = self.get_response()
                               logger.info("Retry with truncated message successful.")
                           except Exception as e_retry:
                                logger.error(f"Retry with truncated message failed: {e_retry}", exc_info=True)
                                assistant_response = f"[系统错误] API 调用重试失败: {e_retry}"
                      else:
                           # If message wasn't long, just add error info
                           self.req[last_user_msg_index]['content'] += f'\n[系统备注]: 上次调用失败 - {e}'
                           logger.warning(f"API call failed. Retrying with error appended to user message. Error: {e}")
                           try:
                               assistant_response = self.get_response()
                               logger.info("Retry with appended error successful.")
                           except Exception as e_retry:
                                logger.error(f"Retry with appended error failed: {e_retry}", exc_info=True)
                                assistant_response = f"[系统错误] API 调用重试失败: {e_retry}"

                 else: # Should not happen often
                      logger.error("Could not find last user message to modify for retry.")
                      assistant_response = f"[系统错误] API 调用失败且无法重试: {e}"

            else: # Only system prompt exists?
                 logger.error("API call failed with only system prompt in history.")
                 assistant_response = f"[系统错误] API 调用失败: {e}"


        self.add_assistant_message(assistant_response)
        if self.save_func:
            try:
                logger.debug("Calling save function callback...")
                self.save_func() # Call the save function provided by AutoCoder
                logger.debug("Save function callback completed.")
            except Exception as e_save:
                 logger.error(f"Error during chat history save callback: {e_save}", exc_info=True)
        return assistant_response

    def callback_stream_single(self, res: str):
        """Callback for handling a single chunk of the response stream."""
        self.printer.dynamic_single_callback(res)
        if self.callback_content:
            try:
                self.callback_content(res)
            except Exception as e:
                 logger.error(f"Error in content callback: {e}", exc_info=True)

    def reason_callback(self, reason: str):
        """Callback for handling reasoning content stream."""
        logger.debug(f"Received reasoning chunk: {reason[:100]}...")
        # Optionally print reasoning differently or log it
        # print(f"\n[Reasoning]: {reason}", end="")
        # Keep printing for visual feedback if desired
        self.printer.dynamic_single_callback(f"\n[Reasoning]: {reason}")
        if self.callback_reason_content:
             try:
                 self.callback_reason_content(reason)
             except Exception as e:
                  logger.error(f"Error in reason callback: {e}", exc_info=True)


# Example usage (optional, consider removing or guarding better)
# if __name__ == '__main__':
#     # Setup basic logging for standalone testing
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#     # This example requires manual API key input or environment variables
#     # It's better run via agent.py which loads config
#     logger.info("ChatAPI Module - Standalone Example Usage (requires valid API key)")
#     try:
#         # Replace with your actual key for direct testing if needed
#         import os # Ensure os is imported for environ access
#         test_api_key = os.environ.get("OPENAI_API_KEY", "YOUR_API_KEY_HERE")
#         if test_api_key == "YOUR_API_KEY_HERE":
#              logger.warning("Please set OPENAI_API_KEY environment variable or replace placeholder.")
#         else:
#              chat_api = ChatAPI(api_key=test_api_key,
#                                 base_url='https://api.openai.com/v1', # Example: Use OpenAI directly
#                                 model='gpt-3.5-turbo',
#                                 prompt='You are a helpful assistant.'
#                                 )
#              response1 = chat_api.chat("Hello, can you help me?")
#              # logger.info(f"\nResponse 1: {response1}") # Already streamed
#              response2 = chat_api.chat("Is 1+1=9?")
#              # logger.info(f"\nResponse 2: {response2}") # Already streamed
#     except Exception as e:
#          logger.critical(f"An error occurred in example usage: {e}", exc_info=True)

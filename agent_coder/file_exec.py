# -*- coding: utf-8 -*-
"""
@author: Zed
@file: file_exec.txt
@time: 2025/2/21 12:34
@describe:文件操作执行器
"""

import os
import shutil
import locale

from typing import List, Optional, Dict, Any  # Added Any for config type hint
from .tool import logger
# Import data structures from data_struct.py
from .data_struct import (
    FileActionType,
    FileOperationInput,
    FileOperationFeedback,
    FeedbackStatus,
    ReplaceResult,
    CodeBlock  # Keep CodeBlock if needed internally, though it's also in data_struct
)



# Helper functions using config
def _is_extension_in_list(filename: str, extensions: List[str]) -> bool:
    """Checks if the file extension is in the provided list."""
    return any(filename.lower().endswith(ext.lower()) for ext in extensions)


def _read_file_content(full_path: str, encoding: str, max_length: Optional[int] = None,
                       limit_extensions: Optional[List[str]] = None) -> str:
    """Reads file content with optional length limiting for specific extensions."""
    apply_limit = False
    if max_length and limit_extensions and _is_extension_in_list(full_path, limit_extensions):
        apply_limit = True

    try:
        with open(full_path, 'r', encoding=encoding, errors='ignore') as f:
            content = f.read()
            if apply_limit and len(content) > max_length:
                n_chars = max_length // 2
                return content[:n_chars] + f'\n... [内容过长，已截断，总长 {len(content)}] ...\n' + content[-n_chars:]
            return content
    except FileNotFoundError:
        raise  # Re-raise FileNotFoundError to be caught by the main handler
    except Exception as e:
        raise IOError(f"读取文件时出错 {full_path}: {e}")


class FileExecutor:

    def __init__(self, workspace: str, config: Dict[str, Any]):
        """
        Initializes the FileExecutor.

        Args:
            workspace (str): The base directory for all file operations.
            config (Dict[str, Any]): Configuration dictionary, expected to contain 'file_execution' settings.
        """
        self.workspace = os.path.abspath(workspace)
        os.makedirs(self.workspace, exist_ok=True)

        # Load config settings
        file_config = config.get('file_execution', {})
        self.default_encoding = file_config.get('default_encoding', 'utf-8')
        self.read_max_length = file_config.get('read_max_length', 10000)
        self.read_limit_extensions = file_config.get('read_limit_extensions', [])
        self.allowed_read_extensions = file_config.get('allowed_read_extensions', [])
        logger.info(f"FileExecutor initialized. Workspace: {self.workspace}, Encoding: {self.default_encoding}")
        logger.debug(
            f"Read Max Length: {self.read_max_length}, Limit Exts: {self.read_limit_extensions}, Allowed Exts: {self.allowed_read_extensions}")

    def _resolve_path(self, relative_path: str) -> str:
        """Resolves a relative path against the workspace, ensuring it stays within."""
        # Normalize path to prevent '..' traversal issues
        normalized_path = os.path.normpath(relative_path)
        # Prevent path components like '..', '.', or leading '/'
        if '..' in normalized_path.split(os.path.sep) or normalized_path.startswith(('.', '/', '\\')):
            raise ValueError(f"无效或禁止的路径: {relative_path}")

        full_path = os.path.join(self.workspace, normalized_path)
        # Double check it's still within workspace (might be redundant with normpath checks but safer)
        if not os.path.abspath(full_path).startswith(self.workspace):
            logger.error(
                f"Path traversal attempt detected: '{relative_path}' resolved to '{full_path}' which is outside workspace '{self.workspace}'")
            raise ValueError(f"路径超出工作区限制: {relative_path}")
        logger.debug(f"Resolved path '{relative_path}' to '{full_path}'")
        return full_path

    def execute_file_operation(self, op: FileOperationInput) -> FileOperationFeedback:
        """Executes a single file operation based on the input."""
        full_path = ""  # Initialize to handle potential errors early
        logger.info(f"Executing file operation: {op.action_type.value} on path: '{op.path}'")
        try:
            # Resolve and validate path first
            full_path = self._resolve_path(op.path)
            action_type = op.action_type  # Use the enum member directly
            logger.debug(f"Operation details: {op}")  # Log the full operation details at debug level

            if action_type == FileActionType.CREATE_FILE:
                return self._create_file(full_path, op)
            elif action_type == FileActionType.DELETE_FILE:
                return self._delete_file(full_path, op)
            elif action_type == FileActionType.REPLACE_FILE:
                return self._replace_blocks(full_path, op)
            elif action_type == FileActionType.READ_FILE:
                return self._read_file(full_path, op)
            elif action_type == FileActionType.CREATE_DIR:
                return self._create_directory(full_path, op)
            elif action_type == FileActionType.DELETE_DIR:
                return self._delete_directory(full_path, op)
            elif action_type == FileActionType.LIST_DIR_TREE:
                # LIST_DIR_TREE might operate on workspace root if path is empty or '.'
                list_path = self._resolve_path(op.path if op.path else '.')
                return self._list_dir_tree(list_path, op)
            else:
                # This case should ideally not be reached if parsing in agent.py is correct
                logger.error(f"Unknown file action type received: {action_type}")
                raise ValueError(f"未知文件操作类型: {action_type}")

        except (ValueError, FileNotFoundError, IOError, OSError) as e:
            # Catch specific file-related errors
            logger.error(f"Error executing {op.action_type.value} on '{op.path}': {e}", exc_info=True)
            return FileOperationFeedback(
                status=FeedbackStatus.FAILURE,
                action_type=op.action_type,
                path=op.path,  # Use the original relative path in feedback
                error_detail=str(e)
            )
        except Exception as e:
            # Catch any other unexpected exceptions
            logger.critical(f"Unexpected error during {op.action_type.value} on '{op.path}': {e}", exc_info=True)
            return FileOperationFeedback(
                status=FeedbackStatus.FAILURE,
                action_type=op.action_type,
                path=op.path,  # Use the original relative path in feedback
                error_detail=str(e)
            )

    # Renamed methods to have leading underscore, indicating internal use
    def _create_file(self, full_path: str, op: FileOperationInput) -> FileOperationFeedback:
        """Creates a file, overwriting if it exists."""
        logger.debug(f"Creating/overwriting file: {full_path}")
        try:
            dir_path = os.path.dirname(full_path)
            if dir_path:  # Ensure directory exists only if there is one
                os.makedirs(dir_path, exist_ok=True)
                logger.debug(f"Ensured directory exists: {dir_path}")
            with open(full_path, 'w', encoding=self.default_encoding) as f:
                content_to_write = op.content if op.content else ""  # Ensure content is not None
                f.write(content_to_write)
                logger.info(f"Successfully created/overwritten file: {op.path} ({len(content_to_write)} chars written)")
            # Read back content to confirm write and potentially apply limits for feedback
            # confirmed_content = _read_file_content(full_path, self.default_encoding, self.read_max_length, self.read_limit_extensions)
            return FileOperationFeedback(
                status=FeedbackStatus.SUCCESS,
                action_type=op.action_type,
                path=op.path,
                # content=confirmed_content # Optionally return limited content
            )
        except Exception as e:
            logger.error(f"Failed to create file {op.path}: {e}", exc_info=True)
            raise IOError(f"创建文件时出错 {op.path}: {e}")

    def _delete_file(self, full_path: str, op: FileOperationInput) -> FileOperationFeedback:
        """Deletes a file."""
        logger.debug(f"Deleting file: {full_path}")
        if not os.path.isfile(full_path):
            logger.error(f"File not found for deletion: {op.path}")
            raise FileNotFoundError(f"文件未找到: {op.path}")
        try:
            os.remove(full_path)
            logger.info(f"Successfully deleted file: {op.path}")
            return FileOperationFeedback(
                status=FeedbackStatus.SUCCESS,
                action_type=op.action_type,
                path=op.path
            )
        except Exception as e:
            logger.error(f"Failed to delete file {op.path}: {e}", exc_info=True)
            raise OSError(f"删除文件时出错 {op.path}: {e}")

    def _read_file(self, full_path: str, op: FileOperationInput) -> FileOperationFeedback:
        """Reads a file, applying extension and length checks."""
        logger.debug(f"Reading file: {full_path}")
        if not os.path.isfile(full_path):
            logger.error(f"File not found for reading: {op.path}")
            raise FileNotFoundError(f"文件未找到: {op.path}")

        # Check allowed extensions
        if not _is_extension_in_list(full_path, self.allowed_read_extensions):
            logger.error(f"Attempted to read disallowed file type: {op.path}")
            raise ValueError(f"不允许读取的文件类型: {op.path}")

        # Read content using helper function (handles limits)
        try:
            content = _read_file_content(full_path, self.default_encoding, self.read_max_length,
                                         self.read_limit_extensions)
            logger.info(f"Successfully read file: {op.path} (Length: {len(content)})")
        except Exception as e:
            logger.error(f"Failed to read file {op.path}: {e}", exc_info=True)
            raise  # Re-raise the exception caught by the helper or IO errors

        return FileOperationFeedback(
            status=FeedbackStatus.SUCCESS,
            action_type=op.action_type,
            path=op.path,
            content=content
        )

    def _replace_blocks(self, full_path: str, op: FileOperationInput) -> FileOperationFeedback:
        """Replaces the first occurrence of specified blocks in a file."""
        logger.debug(f"Replacing blocks in file: {full_path}")
        if not os.path.isfile(full_path):
            logger.error(f"File not found for replacing blocks: {op.path}")
            return FileOperationFeedback(
                status=FeedbackStatus.FAILURE,
                action_type=op.action_type,
                path=op.path,
                error_detail=f"文件未找到: {op.path}"
            )
            # raise FileNotFoundError(f"文件未找到: {op.path}")
        if not op.blocks:
            logger.error(f"No blocks provided for replace operation on {op.path}")
            return FileOperationFeedback(
                status=FeedbackStatus.FAILURE,
                action_type=op.action_type,
                path=op.path,
                error_detail="未提供替换块 (blocks)"
            )

        try:
            # Read original content
            logger.debug(f"Reading original content from {full_path} for replacement.")
            with open(full_path, 'r', encoding=self.default_encoding, errors='ignore') as f:
                content = f.read()
            logger.debug(f"Original content length: {len(content)}")
        except Exception as e:
            logger.error(f"Failed to read file {op.path} before replacement: {e}", exc_info=True)
            raise IOError(f"替换前读取文件时出错 {op.path}: {e}")

        results = []
        modified = False
        current_content = content  # Work on a copy
        blocks_replaced_count = 0

        for i, block in enumerate(op.blocks):
            logger.debug(f"Processing replacement block {i + 1}/{len(op.blocks)} (ID: {block.identifier})")
            # Use replace with count=1 for first occurrence only
            old_content_snippet = block.old_content[:50].replace('\n', '\\n') + (
                '...' if len(block.old_content) > 50 else '')
            new_content_snippet = block.new_content[:50].replace('\n', '\\n') + (
                '...' if len(block.new_content) > 50 else '')
            logger.debug(f"  Replacing '{old_content_snippet}' with '{new_content_snippet}'")

            new_content_after_replace = current_content.replace(block.old_content, block.new_content, 1)

            if new_content_after_replace == current_content:  # No replacement happened
                match_count = current_content.count(block.old_content)  # Check if it exists at all
                logger.warning(
                    f"  Block {i + 1} (ID: {block.identifier}) replacement failed. Matches found: {match_count}.")
                results.append(ReplaceResult(
                    identifier=block.identifier,
                    replaced=False,
                    matches_found=match_count,
                    # Report if found, even if not replaced (e.g., due to previous block change)
                    verification_passed=False,
                    # file_content=content, # Removed file_content from result
                    error_detail="未找到匹配内容或内容已被先前操作更改" if match_count == 0 else "未替换 (可能已被先前操作更改)"
                ))
            else:
                modified = True
                blocks_replaced_count += 1
                current_content = new_content_after_replace
                logger.info(f"  Block {i + 1} (ID: {block.identifier}) replaced successfully.")
                # Basic verification: check if the new content is now present
                # More robust verification might involve parsing or specific checks
                verification = block.new_content in current_content
                logger.debug(f"  Verification passed: {verification}")
                results.append(ReplaceResult(
                    identifier=block.identifier,
                    replaced=True,
                    matches_found=1,  # Replaced one occurrence
                    verification_passed=verification,
                    # file_content=None # Removed file_content
                ))

        # Write back only if modifications occurred
        if modified:
            logger.info(
                f"Writing {blocks_replaced_count} modifications back to {op.path}. New length: {len(current_content)}")
            try:
                with open(full_path, 'w', encoding=self.default_encoding) as f:
                    f.write(current_content)
                logger.info(f"Successfully wrote modifications to {op.path}")
            except Exception as e:
                logger.error(f"Failed to write modifications to {op.path}: {e}", exc_info=True)
                # If write fails, report error but results might reflect intended changes
                return FileOperationFeedback(
                    status=FeedbackStatus.FAILURE,
                    action_type=op.action_type,
                    path=op.path,
                    replace_results=results,
                    error_detail=f"替换后写入文件时出错: {e}"
                )

        logger.info(
            f"Replace operation on {op.path} completed. {blocks_replaced_count}/{len(op.blocks)} blocks replaced.")
        return FileOperationFeedback(
            status=FeedbackStatus.SUCCESS,
            action_type=op.action_type,
            path=op.path,
            replace_results=results
        )

    def _build_tree(self, directory: str) -> dict:
        """Recursively builds a directory tree structure.
        Example return format:
        {
            'name': 'dir_name',
            'files': ['file1.txt', 'file2.py'],
            'dirs': {
                'subdir1': {
                    'name': 'subdir1',
                    'files': ['subfile.txt'],
                    'dirs': {}
                },
                'subdir2': { ... }
            }
        }
        """
        node_name = os.path.basename(directory)
        if not node_name:  # Handle case for root like '.'
            node_name = '.'
        result = {
            'name': node_name,
            'files': [],
            'dirs': {}
        }

        try:
            # Use scandir for potentially better performance
            for entry in sorted(os.scandir(directory), key=lambda e: e.name):
                if entry.is_file():
                    result['files'].append(entry.name)
                elif entry.is_dir():
                    # Recursive call
                    result['dirs'][entry.name] = self._build_tree(entry.path)
            return result
        except PermissionError as pe:
            logger.warning(f"Permission denied accessing directory: {directory}. Error: {pe}")
            # Don't raise, just mark as inaccessible in the tree
            result['error'] = 'Permission Denied'
            return result
        except FileNotFoundError as fnfe:
            logger.warning(f"Directory not found during scan: {directory}. Error: {fnfe}")
            # If the directory disappears during listing
            result['error'] = 'Not Found During Scan'
            return result
        except Exception as e:
            logger.error(f"Error scanning directory {directory}: {e}", exc_info=True)
            result['error'] = f"Scan Error: {e}"
            return result

    def _list_dir_tree(self, full_path: str, op: FileOperationInput) -> FileOperationFeedback:
        """Lists the directory tree structure."""
        logger.debug(f"Listing directory tree for: {full_path}")
        if not os.path.isdir(full_path):
            logger.error(f"Directory not found for listing: {op.path}")
            raise FileNotFoundError(f"目录未找到: {op.path}")

        tree = self._build_tree(full_path)
        logger.info(f"Successfully listed directory tree for: {op.path}")
        logger.debug(
            f"Directory tree structure (root): {tree.get('name')}, Files: {len(tree.get('files', []))}, Dirs: {len(tree.get('dirs', {}))}")

        return FileOperationFeedback(
            status=FeedbackStatus.SUCCESS,
            action_type=op.action_type,
            path=op.path,
            dir_tree=tree
        )

    def _create_directory(self, full_path: str, op: FileOperationInput) -> FileOperationFeedback:
        """Creates a directory."""
        logger.debug(f"Creating directory: {full_path}")
        try:
            # exist_ok=True prevents error if directory already exists
            os.makedirs(full_path, exist_ok=True)
            logger.info(f"Successfully created or ensured directory exists: {op.path}")
            return FileOperationFeedback(
                status=FeedbackStatus.SUCCESS,
                action_type=op.action_type,
                path=op.path
            )
        except Exception as e:
            logger.error(f"Failed to create directory {op.path}: {e}", exc_info=True)
            raise OSError(f"创建目录时出错 {op.path}: {e}")

    def _delete_directory(self, full_path: str, op: FileOperationInput) -> FileOperationFeedback:
        """Deletes a directory, recursively if specified."""
        logger.debug(f"Deleting directory: {full_path} (Recursive: {op.recursive})")
        if not os.path.isdir(full_path):
            logger.error(f"Directory not found for deletion: {op.path}")
            raise FileNotFoundError(f"目录未找到: {op.path}")
        action_desc = ''
        try:

            if op.recursive:
                shutil.rmtree(full_path)
                action_desc = "递归删除目录"
                logger.info(f"Successfully recursively deleted directory: {op.path}")
            else:
                # os.rmdir only works on empty directories
                os.rmdir(full_path)
                action_desc = "删除空目录"
                logger.info(f"Successfully deleted empty directory: {op.path}")

            return FileOperationFeedback(
                status=FeedbackStatus.SUCCESS,
                action_type=op.action_type,
                path=op.path
            )
        except OSError as e:
            # Provide more specific feedback for non-empty directory deletion attempt
            if not op.recursive and (
                    "Directory not empty" in str(e) or "目录不是空的" in str(e)):  # Check common error messages
                logger.error(f"{action_desc} failed: Directory not empty and recursive not specified ({op.path}): {e}")
                raise OSError(f"{action_desc} 失败: 目录非空且未指定递归删除 ({op.path}): {e}")
            else:
                logger.error(f"Error during {action_desc} on {op.path}: {e}", exc_info=True)
                raise OSError(f"{action_desc} 时出错 {op.path}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during {action_desc} on {op.path}: {e}", exc_info=True)
            raise OSError(f"{action_desc} 时发生意外错误 {op.path}: {e}")

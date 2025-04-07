from enum import Enum
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Union
import json
from datetime import datetime

__all__ = [
    "OperationRequest",
    "OperationResponse",
    "FeedbackStatus",
    "FileOperationInput",
    "FileOperationFeedback",
    "CodeBlock",
    "ReplaceResult",
    "FileActionType",
    "Parser",
    "WorkFinishNote",
    "ProgramCheckRequest"
]


@dataclass
class OperationResponse:
    request_id: str
    reason: str
    file_actions_result: list
    program_execs_result: list
    program_role: str = "system"

    def to_structured_text(self) -> str:
        """转换为符合API要求的结构化文本"""

        def convert_enum(data):
            if isinstance(data, dict):
                return {k: convert_enum(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [convert_enum(item) for item in data]
            elif isinstance(data, Enum):
                return data.value
            else:
                return data

        response_dict = asdict(self)
        cleaned_dict = convert_enum(response_dict)
        return json.dumps(cleaned_dict, ensure_ascii=False, indent=2)


@dataclass
class ReplaceResult:
    """单个区块替换结果"""
    identifier: str
    replaced: bool  # 是否成功替换
    matches_found: int  # 找到的匹配数量
    verification_passed: bool  # 替换后校验是否通过
    error_detail: Optional[str] = None

    def to_dict(self):
        return {
            "id": self.identifier,
            "replaced": self.replaced,
            "matches": self.matches_found,
            "verified": self.verification_passed,
            "error": self.error_detail
        }

    def __str__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class FileActionType(Enum):
    CREATE_FILE = "create_file"
    DELETE_FILE = "delete_file"
    READ_FILE = "read_file"
    REPLACE_FILE = "replace_file"  # 区块替换操作
    CREATE_DIR = "create_directory"
    DELETE_DIR = "delete_directory"
    LIST_DIR_TREE = "list_tree"


@dataclass
class CodeBlock:
    """代码区块标识（通过函数名/唯一标识定位）"""
    identifier: str  # 如函数名：def my_function()
    old_content: str  # 需要匹配的原始代码
    new_content: str  # 替换后的新代码

    def to_dict(self):
        return {
            "id": self.identifier,
            "old": self.old_content,
            "new": self.new_content
        }

    def __str__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class FeedbackStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass
class FileOperationFeedback:
    """文件操作的反馈结果"""
    status: FeedbackStatus
    action_type: FileActionType
    path: str
    content: Optional[str] = None
    dir_tree: Optional[Dict] = None
    replace_results: Optional[List[ReplaceResult]] = None
    error_detail: Optional[str] = None

    def to_dict(self):
        return {
            "status": self.status.value,
            "action": self.action_type.value,
            "path": self.path,
            "content": self.content,
            "dir_tree": self.dir_tree,
            "replaces": [r.to_dict() for r in self.replace_results] if self.replace_results else None,
            "error": self.error_detail
        }

    def __str__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class FileOperationInput:
    action_type: FileActionType
    path: str
    blocks: Optional[List[CodeBlock]] = None  # 仅REPLACE_BLOCK时使用
    content: Optional[str] = None
    recursive: bool = False
    request_reason: Optional[str] = None

    def to_dict(self):
        return {
            "action": self.action_type.value,
            "path": self.path,
            "blocks": [b.to_dict() for b in self.blocks] if self.blocks else None,
            "content": self.content,
            "recursive": self.recursive,
            "reason": self.request_reason
        }

    def __str__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ========================
# 核心枚举类型
# ========================


class ProgramActionType(Enum):
    EXECUTE_COMMAND = "execute"
    TERMINATE_COMMAND = "terminate"


class RequestStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


# ========================
# 操作指令数据结构
# Note: Redundant definitions of CodeBlock and ReplaceResult were removed from here.
# The definitions near the top of the file are kept.
# ========================
@dataclass
class FileOperationInput:
    action_type: FileActionType
    path: str
    blocks: Optional[List[CodeBlock]] = None  # 仅REPLACE_BLOCK时使用
    content: Optional[str] = None
    recursive: bool = False
    request_reason: Optional[str] = None

    def to_dict(self):
        return {
            "action": self.action_type.value,
            "path": self.path,
            "blocks": [b.to_dict() for b in self.blocks] if self.blocks else None,
            "content": self.content,
            "recursive": self.recursive,
            "reason": self.request_reason
        }


@dataclass
class ProgramExecutionInput:
    name: str
    command: str
    timeout: Optional[int] = None
    request_reason: Optional[str] = None

    def to_dict(self):
        return {
            "name": self.name,
            "command": self.command,
            "timeout": self.timeout,
            "reason": self.request_reason
        }

    def __str__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class ProgramCheckInput:
    name: str
    terminal: bool  # true表示终止程序
    reason: Optional[str] = None  # 理由

    def to_dict(self):
        return {
            "name": self.name,
            "terminal": self.terminal,
            "reason": self.reason
        }

    def __str__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ========================
# 反馈数据结构
# ========================
@dataclass
class FileOperationFeedback:
    status: FeedbackStatus
    action_type: FileActionType
    path: str
    content: Optional[str] = None
    dir_tree: Optional[Dict] = None
    replace_results: Optional[List[ReplaceResult]] = None
    error_detail: Optional[str] = None

    def to_dict(self):
        return {
            "status": self.status.value,
            "action": self.action_type.value,
            "path": self.path,
            "content": self.content,
            "dir_tree": self.dir_tree,
            "replaces": [r.to_dict() for r in self.replace_results] if self.replace_results else None,
            "error": self.error_detail
        }

    def __str__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class ProgramExecutionFeedback:
    status: FeedbackStatus
    action_type: ProgramActionType
    execution_time: float
    stdout: str
    stderr: str
    returncode: str
    killed_by_timeout: bool = False

    #     print(f"输出内容: {result['output']}")
    #     print(f"错误信息: {result['error']}")
    #     print(f"返回码: {result['returncode']}")
    #     print(f"是否超时: {result['timeout']}")
    #     print(f"进程ID: {result['pid']}")
    #     print(f"执行时间: {result['execution_time']}秒")
    #     print(f"是否完成: {result['finished']}")
    def to_dict(self):
        return {
            "status": self.status.value,
            "action": self.action_type.value,
            "exec_time": self.execution_time,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.stderr,
            "timeout": self.killed_by_timeout
        }

    def __str__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class ProgramCheckFeedback:
    name: str
    runtime: float
    stdout: str
    stderr: str

    def to_dict(self):
        return {
            "name": self.name,
            "runtime": self.runtime,
            "stdout": self.stdout,
            "stderr": self.stderr,

        }

    def __str__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class ProgramCheckRequest:
    # 程序过程检查请求：终止/或者继续
    request_id: str
    program_operations: List[ProgramCheckInput] = None
    created_at: str = datetime.now().isoformat()
    type = 'program_check'

    def to_dict(self):
        return {
            "request_id": self.request_id,
            "program_operations": self.program_operations,
            "created_at": self.created_at,
            "type": 'program_check'
        }

    def __str__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class WorkFinishNote:
    # 工作流结束通知：对该工作内容的总结：主要包括架构，核心功能，注意事项，优点，缺点，建议等细节
    # 后续可考虑更细致的结构化
    # request_id: str
    summary: str
    created_at: str = datetime.now().isoformat()
    type = 'finish'

    def to_dict(self):
        return {
            # "request_id": self.request_id,
            "summary": self.summary,
            "created_at": self.created_at,
            'type': self.type,
        }

    def __str__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ========================
# 顶层通信协议
# ========================
@dataclass
class OperationRequest:
    request_id: str
    reason: str
    file_operations: List[FileOperationInput] = None
    program_operations: List[ProgramExecutionInput] = None
    created_at: str = datetime.now().isoformat()
    type = 'operate'

    def to_json(self):
        return json.dumps({
            "step_id": self.request_id,
            'reason': self.reason,
            "file_operations": [op.to_dict() for op in self.file_operations] if self.file_operations else [],
            "programs_operations": [op.to_dict() for op in self.program_operations] if self.program_operations else [],
            "created": self.created_at,
            "type": self.type
        }, ensure_ascii=False, indent=2)

    def __str__(self):
        return self.to_json()


@dataclass
class ProgramResult:
    name: str
    stdout: str
    stderr: str
    exec_time: float
    return_code: int
    status: str  # completed, timeout, aborted

    def to_json(self):
        return json.dumps({
            "name": self.name,
            'stdout': self.stdout,
            "stderr": self.stderr,
            "exec_time": self.exec_time,
            "return_code": self.return_code,
            "status": self.status
        }, ensure_ascii=False, indent=2)

    def __str__(self):
        return self.to_json()


#
# 在已有代码基础上新增以下内容
class Parser:
    # 结构化文本转类实例
    @classmethod
    def parse_request(cls, json_data: Dict) -> Union[OperationRequest, ProgramCheckRequest, WorkFinishNote]:
        """解析操作请求"""
        if json_data['type'] == 'finish':
            # 程序执行结束，通知用户，可以给出文档，建议，总结之类的内容作为收尾
            return WorkFinishNote(summary=json_data["metadata"]["summary"])
        elif json_data['type'] == 'operate':
            return OperationRequest(
                request_id=json_data["metadata"]["step_id"],
                reason=json_data["metadata"]["reason"],
                file_operations=cls._parse_file_actions(json_data.get("file_operations", [])),
                program_operations=cls._parse_program_execs(json_data.get("program_operations", [])),
                created_at=json_data["metadata"].get("timestamp")
            )
        elif json_data['type'] == 'check_program':
            # 程序检查，用于在程序过程中实时的通讯，获取反馈以及指导，正常预期继续进行，否则可以考虑中止
            return ProgramCheckRequest(
                request_id=json_data["metadata"]["step_id"],
                program_operations=json_data["program_operations"],
            )

    @classmethod
    def _parse_file_actions(cls, actions: List[Dict]) -> List[FileOperationInput]:
        result = []
        for action in actions:
            action_type = FileActionType(action["action_type"])
            blocks = None
            if action_type == FileActionType.REPLACE_FILE:
                blocks = []
                # Assuming the AI provides 'identifier', 'old_content', 'new_content' in each dict within 'modify_content'
                for mod in action.get("modify_content", []):
                    identifier = mod.get("identifier") # Get identifier safely
                    if not identifier:
                         # Handle missing identifier, maybe log a warning or raise error
                         print(f"Warning: Missing 'identifier' in modify_content block for {action['path']}. Using placeholder.")
                         identifier = "MISSING_IDENTIFIER" # Or skip this block
                    blocks.append(CodeBlock(
                        identifier=identifier, # Use extracted identifier
                        old_content=mod.get("old_content", ""), # Use get for safety
                        new_content=mod.get("new_content", "")  # Use get for safety
                    ))

            result.append(FileOperationInput(
                action_type=action_type,
                path=action["path"],
                blocks=blocks,
                content=action.get("file_content"),
                request_reason=action.get("reason")
            ))
        return result

    @classmethod
    def _parse_program_execs(cls, exec_program_list: List) -> List[ProgramExecutionInput]:
        total_list = []
        for exec_program in exec_program_list:
            total_list.append(ProgramExecutionInput(
                name=exec_program["name"],
                command=exec_program["command"],
                timeout=exec_program.get("set_timeout"),
                request_reason=exec_program.get("expected_output")
            ))
        return total_list

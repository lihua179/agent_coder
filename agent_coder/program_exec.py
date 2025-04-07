# -*- coding: utf-8 -*-
"""
@author: Zed
@file: program_exec.py
@time: 2025/2/19 20:09
@describe:程序执行器，支持并行和监控 (v0.3 - 支持实时输出反馈和中断)
"""
import subprocess
import threading
import time
import os
import signal
import queue  # Use queue for thread-safe communication of output lines
from typing import List, Callable, Optional, Dict, Any, Tuple

# Import data structures from data_struct.py
from .data_struct import (
    FeedbackStatus,
    ProgramActionType,
    ProgramExecutionFeedback,
    ProgramCheckFeedback,
    ProgramExecutionInput,
    ProgramResult,
    ProgramCheckInput  # Needed for ProgramCheck callback return type hint
)

__all__ = [
    "ParallelExecutor",
    "ProgramCheck",
]


class CommandExecutor:
    def __init__(self, config: Dict[str, Any]):
        """
        Initializes the CommandExecutor.

        Args:
            config (Dict[str, Any]): Configuration dictionary, expected to contain 'program_execution' settings.
        """
        program_config = config.get('program_execution', {})
        self.output_buffer_limit = program_config.get('output_buffer_limit', 2000)
        self.default_timeout = program_config.get('default_timeout', 60)

        self.active_process: Optional[subprocess.Popen] = None
        self.output_queue: queue.Queue[Tuple[str, str]] = queue.Queue()  # Queue for ('stdout'/'stderr', line)
        self.running: bool = False
        self.lock = threading.Lock()  # Protects access to self.running and self.active_process
        self.stdout_thread: Optional[threading.Thread] = None
        self.stderr_thread: Optional[threading.Thread] = None
        self.process_terminated_event = threading.Event()  # Signal when process ends or is stopped

    def _read_stream_to_queue(self, stream_name: str, stream):
        """Reads lines from a stream and puts them into the output queue."""
        try:
            for line in iter(stream.readline, ''):
                if not line:
                    break
                self.output_queue.put((stream_name, line.strip()))
            stream.close()
        except ValueError:  # Handle potential ValueError if stream is closed prematurely
            # print(f"Stream {stream_name} closed prematurely.")
            pass
        except Exception as e:
            print(f"Error reading stream {stream_name}: {e}")
        finally:
            # Signal that this stream is done (might help determine process end)
            # print(f"Stream reader thread for {stream_name} finished.")
            pass  # Let the main execute loop handle process termination logic

    def get_new_output(self) -> List[Tuple[str, str]]:
        """Retrieves all currently available output lines from the queue."""
        lines = []
        while not self.output_queue.empty():
            try:
                lines.append(self.output_queue.get_nowait())
            except queue.Empty:
                break
        return lines

    def execute(self, name: str, command: str, timeout: Optional[int] = None) -> Dict:
        """
        Executes a command, captures output in real-time, handles timeout.

        Args:
            name (str): A name for this execution instance.
            command (str): The command string to execute.
            timeout (Optional[int]): Timeout in seconds. Uses default from config if None.

        Returns:
            Dict: A dictionary containing final execution results.
        """
        exec_timeout = timeout if timeout is not None else self.default_timeout
        result = {
            "output": "", "error": "", "returncode": -1,
            "timeout": False, "pid": None, "execution_time": 0.0, "finished": False
        }
        # Clear queue and reset state for new execution
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break
        self.process_terminated_event.clear()

        output_lines = []
        error_lines = []

        try:
            start_time = time.time()
            with self.lock:
                self.running = True

            # Using Popen for non-blocking execution
            # Use os.setsid on Unix to create a process group for easier termination
            preexec_fn = os.setsid if os.name != 'nt' else None
            self.active_process = subprocess.Popen(
                command, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='ignore',
                bufsize=1, universal_newlines=True,
                preexec_fn=preexec_fn
            )
            result["pid"] = self.active_process.pid

            # Start threads to read stdout and stderr
            self.stdout_thread = threading.Thread(
                target=self._read_stream_to_queue,
                args=('stdout', self.active_process.stdout),
                daemon=True
            )
            self.stderr_thread = threading.Thread(
                target=self._read_stream_to_queue,
                args=('stderr', self.active_process.stderr),
                daemon=True
            )
            self.stdout_thread.start()
            self.stderr_thread.start()

            # Wait for process completion or timeout
            process_finished = False
            try:
                # Wait for the process to finish or timeout occurs
                self.active_process.wait(timeout=exec_timeout)
                process_finished = True  # Process finished naturally
            except subprocess.TimeoutExpired:
                print(f"Process '{name}' (PID: {result['pid']}) timed out after {exec_timeout}s.")
                result["timeout"] = True
                self.stop(name)  # Use stop method to terminate and signal
            except Exception as wait_err:
                print(f"Error waiting for process '{name}': {wait_err}")
                self.stop(name)  # Attempt to stop if wait fails

            # Ensure reader threads finish after process termination/completion
            if self.stdout_thread and self.stdout_thread.is_alive():
                self.stdout_thread.join(timeout=1.0)  # Short timeout for thread join
            if self.stderr_thread and self.stderr_thread.is_alive():
                self.stderr_thread.join(timeout=1.0)

            # Process finished or was terminated, collect final results
            result[
                "returncode"] = self.active_process.returncode if self.active_process else -1  # Get return code if process object exists
            result["finished"] = process_finished and not result["timeout"]  # Mark finished only if completed naturally

            # Collect all output from the queue
            final_lines = self.get_new_output()  # Get any remaining lines
            for stream_name, line in final_lines:
                if stream_name == 'stdout':
                    output_lines.append(line)
                else:
                    error_lines.append(line)

            # Apply buffer limit to final result
            final_output = "\n".join(output_lines)
            final_error = "\n".join(error_lines)

            if len(final_output) > self.output_buffer_limit:
                n_chars = self.output_buffer_limit // 2
                result["output"] = final_output[
                                   :n_chars] + f'\n... [截断, 总长 {len(final_output)}] ...\n' + final_output[-n_chars:]
            else:
                result["output"] = final_output

            if len(final_error) > self.output_buffer_limit:
                n_chars = self.output_buffer_limit // 2
                result["error"] = final_error[:n_chars] + f'\n... [截断, 总长 {len(final_error)}] ...\n' + final_error[
                                                                                                           -n_chars:]
            else:
                result["error"] = final_error

            result["execution_time"] = round(time.time() - start_time, 2)

        except FileNotFoundError:
            result["error"] = f"命令或程序未找到: {command.split()[0]}"
            result["returncode"] = -1
        except Exception as e:
            print(f"执行命令时发生错误 '{name}': {e}")
            result["error"] = str(e)
        finally:
            with self.lock:
                self.running = False
            # Ensure process is cleaned up if it wasn't terminated explicitly or wait failed
            if self.active_process and self.active_process.poll() is None:
                print(
                    f"Warning: Process '{name}' (PID: {result.get('pid')}) might still be running after execution block.")
                self._terminate_process(name)  # Force terminate if still running
            self._cleanup()

        return result

    def _terminate_process(self, name: str):
        """Terminates the active process and its group if possible."""
        with self.lock:  # Protect access to active_process
            if not self.active_process or self.active_process.poll() is not None:
                return  # Process already terminated or doesn't exist

            pid = self.active_process.pid
            print(f"正在终止程序 '{name}' (PID: {pid})...")
            try:
                if os.name == 'nt':
                    # Windows: Using taskkill /T /F to forcefully terminate process tree
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], check=False, capture_output=True,
                                   timeout=5)
                else:
                    # Unix: Send SIGTERM to the process group, then SIGKILL if needed
                    pgid = os.getpgid(pid)
                    try:
                        os.killpg(pgid, signal.SIGTERM)
                        time.sleep(0.5)  # Give time for graceful shutdown
                        # Check if still alive
                        if self.active_process.poll() is None:
                            print(f"Process group {pgid} did not terminate with SIGTERM, sending SIGKILL...")
                            os.killpg(pgid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass  # Process or group already gone
                    except Exception as e_unix:
                        print(f"Error sending SIGTERM/SIGKILL to group {pgid}: {e_unix}. Trying direct kill.")
                        # Fallback to killing just the main process if group kill fails
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except Exception as e_kill:
                            print(f"Error sending direct SIGKILL to {pid}: {e_kill}")

                # Wait briefly for termination confirmation
                try:
                    self.active_process.wait(timeout=1.0)
                    print(f"程序 '{name}' 已终止.")
                except subprocess.TimeoutExpired:
                    print(f"Warning: 程序 '{name}' (PID: {pid}) 未能在超时内确认终止.")

            except Exception as e:
                print(f"终止程序时发生错误 '{name}' (PID: {pid}): {e}")
            finally:
                # Ensure process object is cleared even if termination had issues
                self.active_process = None
                self.process_terminated_event.set()  # Signal that termination was attempted/completed

    def stop(self, name: str):
        """Public method to stop the execution."""
        print(f"Stop requested for '{name}'")
        with self.lock:
            if not self.running:
                print(f"Stop ignored: '{name}' is not running.")
                return
            self.running = False  # Signal intent to stop
        self._terminate_process(name)  # Initiate termination

    def _cleanup(self):
        """Cleans up resources."""
        self.active_process = None
        # self.running is set in finally block of execute or in stop()
        self.stdout_thread = None
        self.stderr_thread = None
        # Queue is cleared at the start of execute


class ProgramCheck:
    """
    Handles periodic checking of running programs and sending feedback.
    """

    def __init__(self, config: Dict[str, Any], send_feedback: Callable[[Dict[str, Dict]], Optional[List[str]]]):
        """
        Initializes the ProgramCheck instance.

        Args:
            config (Dict[str, Any]): Configuration dictionary.
            send_feedback (Callable): Function to call with program status updates.
                                      Expected input: {program_name: {'stdout': [lines], 'stderr': [lines], 'runtime': float}}
                                      Expected return: List of program names to terminate, or None/empty list.
        """
        program_config = config.get('program_execution', {})
        self.check_interval = program_config.get('feedback_check_interval', 5)  # Default 5 seconds
        self.send_feedback = send_feedback
        self.start_times: Dict[str, float] = {}  # Store start time per program
        self.last_check_time = time.time()
        print(f"ProgramCheck initialized. Interval: {self.check_interval}s")

    def set_start_time(self, name: str):
        """Records the start time for a program."""
        self.start_times[name] = time.time()

    def remove_program(self, name: str):
        """Removes a program when it finishes or is stopped."""
        self.start_times.pop(name, None)

    def __call__(self, current_output_dict: Dict[str, Dict[str, List[str]]]) -> Optional[List[str]]:
        """
        Checks if the interval has passed and sends feedback if needed.

        Args:
            current_output_dict (Dict[str, Dict[str, List[str]]]):
                Dictionary mapping program names to their *new* {'stdout': [lines], 'stderr': [lines]} since last check.

        Returns:
            Optional[List[str]]: List of program names to terminate, or None.
        """
        now = time.time()
        if now - self.last_check_time >= self.check_interval:
            self.last_check_time = now
            feedback_payload = {}

            for name, outputs in current_output_dict.items():
                if name not in self.start_times: continue  # Skip if program already removed

                runtime = round(now - self.start_times[name], 2)
                # Create feedback object using ProgramCheckFeedback structure
                # Send only the *new* output lines
                program_feedback = ProgramCheckFeedback(
                    name=name,
                    runtime=runtime,
                    stdout="\n".join(outputs.get('stdout', [])),  # Join new lines
                    stderr="\n".join(outputs.get('stderr', []))  # Join new lines
                )
                feedback_payload[name] = program_feedback.to_dict()

            if feedback_payload:
                print(
                    f"ProgramCheck: Sending feedback for {list(feedback_payload.keys())}:{list(feedback_payload.values())}")
                try:
                    # Call the provided feedback function (likely sends to AI)
                    terminate_list = self.send_feedback(feedback_payload)
                    return terminate_list  # Return list of names to terminate
                except Exception as e:
                    print(f"Error during send_feedback callback: {e}")
        return None  # No termination requested


class ParallelExecutor:
    def __init__(self, config: Dict[str, Any], program_check: Optional[ProgramCheck] = None):
        """
        Initializes the ParallelExecutor.

        Args:
            config (Dict[str, Any]): Configuration dictionary.
            program_check (Optional[ProgramCheck]): Instance for monitoring and feedback.
        """
        self.config = config
        program_config = config.get('program_execution', {})
        self.monitor_interval = program_config.get('monitor_interval', 0.5)  # How often monitor checks status

        self.executors: Dict[str, CommandExecutor] = {}
        self.results: Dict[str, ProgramResult] = {}
        self.lock = threading.Lock()  # Protects executors and results
        self.program_check = program_check
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_monitor = threading.Event()
        print(f"ParallelExecutor initialized. Monitor Interval: {self.monitor_interval}s")

    def execute_programs(self, configs: List[ProgramExecutionInput]) -> Dict[str, ProgramResult]:
        """
        Executes multiple programs in parallel, collects results, allows real-time feedback/interruption.

        Args:
            configs (List[ProgramExecutionInput]): List of program configurations.

        Returns:
            Dict[str, ProgramResult]: Dictionary mapping program names to their final results.
        """
        self.results = {}
        self.executors = {}
        self.stop_monitor.clear()

        # Initialize executors and result placeholders
        for cfg in configs:
            executor = CommandExecutor(self.config)
            self.executors[cfg.name] = executor
            self.results[cfg.name] = ProgramResult(
                name=cfg.name, stdout="", stderr="",
                exec_time=0.0, return_code=-1, status="pending"
            )
            if self.program_check:
                self.program_check.set_start_time(cfg.name)  # Record start time for check

        # Start execution threads
        threads = []
        for cfg in configs:
            thread = threading.Thread(target=self._run_single_program, args=(cfg,), daemon=True)
            threads.append(thread)
            thread.start()

        # Start monitoring thread if ProgramCheck is enabled
        if self.program_check:
            self.monitor_thread = threading.Thread(target=self._monitor_programs, daemon=True)
            self.monitor_thread.start()

        # Wait for all execution threads to complete
        for thread in threads:
            thread.join()  # Wait for the _run_single_program threads

        # Signal monitor thread to stop and wait for it
        self.stop_monitor.set()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=self.monitor_interval * 2)  # Wait for monitor to finish

        print("Parallel execution finished.")
        # Final results are populated by _run_single_program
        return self.results

    def _run_single_program(self, cfg: ProgramExecutionInput):
        """Target function for each program execution thread."""
        executor = self.executors[cfg.name]
        print(f"Starting program '{cfg.name}'...")
        exec_timeout = cfg.timeout  # Use timeout from input config
        result_dict = {}
        try:
            result_dict = executor.execute(name=cfg.name, command=cfg.command, timeout=exec_timeout)
            status = "unknown"  # Start with unknown status

            # --- Revised Status Logic ---
            # 1. Check if explicitly terminated by stop() first
            if executor.process_terminated_event.is_set():
                status = 'terminated'
            # 2. Check if it timed out
            elif result_dict.get("timeout"):
                status = 'timeout'
            # 3. Check if it finished naturally (wait() returned without timeout/termination)
            elif result_dict.get("finished"):
                status = 'completed'
            # 4. Otherwise, consider it aborted or failed based on return code?
            else:
                # If return code is available and non-zero, maybe 'failed'?
                # For now, stick to 'aborted' as a general non-completed state.
                status = 'aborted'
                # You could add more specific logic here based on return_code if needed
                # if result_dict.get("returncode", -1) != 0:
                #     status = 'failed'


        except Exception as e:
            print(f"Unhandled exception in _run_single_program for '{cfg.name}': {e}")
            status = 'failed'
            result_dict = {"output": "", "error": str(e), "execution_time": 0.0,
                           "returncode": -1}  # Populate basic error info

        # Update the shared results dictionary safely
        with self.lock:
            self.results[cfg.name] = ProgramResult(
                name=cfg.name,
                stdout=result_dict.get("output", ""),
                stderr=result_dict.get("error", ""),
                exec_time=result_dict.get("execution_time", 0.0),
                return_code=result_dict.get("returncode", -1),
                status=status
            )
            # Remove from program check tracking once finished/stopped
            if self.program_check:
                self.program_check.remove_program(cfg.name)

        print(f"Program '{cfg.name}' finished with status: {status}")

    def _monitor_programs(self):
        """Monitoring thread function."""
        print("Monitor thread started.")
        while not self.stop_monitor.is_set():
            new_outputs_for_check: Dict[str, Dict[str, List[str]]] = {}
            active_executors_exist = False

            with self.lock:  # Lock when accessing shared executors dict
                # Create a copy of keys to avoid issues if dict changes during iteration (e.g., program finishes)
                executor_names = list(self.executors.keys())
                for name in executor_names:
                    if name not in self.executors: continue  # Skip if removed between getting keys and access
                    executor = self.executors[name]
                    if executor.running:
                        active_executors_exist = True
                        # Get *new* output since last check
                        new_lines = executor.get_new_output()
                        if new_lines:
                            if name not in new_outputs_for_check:
                                new_outputs_for_check[name] = {'stdout': [], 'stderr': []}
                            for stream_name, line in new_lines:
                                new_outputs_for_check[name][stream_name].append(line)

            if not active_executors_exist and not self.stop_monitor.is_set():
                # print("Monitor: No active executors found. Exiting loop.") # Debug
                break  # Exit loop if no programs are running

            # Perform check using ProgramCheck instance if there's new output
            if self.program_check and new_outputs_for_check:
                try:
                    # Pass the dictionary of *new* outputs
                    terminate_names = self.program_check(new_outputs_for_check)
                    if terminate_names:
                        print(f"Monitor: Requesting termination for {terminate_names}")
                        with self.lock:  # Lock for modifying executors via stop()
                            for name_to_term in terminate_names:
                                if name_to_term in self.executors and self.executors[name_to_term].running:
                                    print(f"Monitor: Stopping '{name_to_term}'...")
                                    # Call stop on the executor instance
                                    self.executors[name_to_term].stop(name_to_term)
                                else:
                                    print(f"Monitor: Cannot stop '{name_to_term}', not found or not running.")
                except Exception as check_err:
                    print(f"Error during program check callback execution: {check_err}")

            # Wait for the configured interval or until stop event is set
            self.stop_monitor.wait(self.monitor_interval)

        print("Monitor thread finished.")

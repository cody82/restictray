import subprocess
import asyncio
import json
from datetime import datetime
from typing import Callable, Optional
from restictray.storage import Repository, Job, History, Storage
from restictray import globals


class BackupExecutor:
    def __init__(self, repository: Repository, job: Job, state_update_callback: Optional[Callable[[str],None]]=None):
        self.running = False
        self._state_update_callback = state_update_callback
        self.repository = repository
        self.job = job

    def _count(self, obj: list|None) -> int:
        if obj is None:
            return 0
        return len(obj)
    
    async def run(self) -> dict|None:
        async with globals.get_repo_lock(self.repository.name):
            return await self._run()
    
    async def _run(self) -> dict|None:
        self.running = True
        
        repo_url = self.repository.url
        password = self.repository.password
        if self.job.type == "backup":
            tags = ["--tag", "created-by:ResticTray"]
        else:
            tags = []
        args = ["-r", repo_url, *tags, "--password-command", f"echo '{password}'", "--json", self.job.type, *self.job.additional_args.split(), self.job.directory]
        
        # filter empty args
        args = [arg for arg in args if arg]

        print(f"Running restic with args: {args}")
        start = asyncio.get_event_loop().time()
        """Perform a restic backup asynchronously, reading JSON output line by line."""
        process = await asyncio.create_subprocess_exec(
            'restic', *args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Read stdout line by line in real time
        summary = None
        async for line in process.stdout:
            line_str = line.decode().strip()
            if not line_str:
                continue
                
            try:
                data = json.loads(line_str)
                if self.job.type == "forget":
                    summary = data
                    continue
                
                message_type = data.get("message_type", "")

                if message_type == "status":
                    # Progress update
                    files_done = data.get("files_done", 0)
                    bytes_done = data.get("bytes_done", 0)
                    total_files = data.get("total_files", 0)
                    total_bytes = data.get("total_bytes", 0)
                    percent_done = data.get("percent_done", 0)
                    
                    # Format bytes to human readable
                    bytes_done_mb = bytes_done / (1024 * 1024)
                    total_bytes_mb = total_bytes / (1024 * 1024)
                    
                    progress = f"Progress: {percent_done:.0%} - {files_done}/{total_files} files, {bytes_done_mb:.0f}/{total_bytes_mb:.0f} MB"
                    #print(progress)
                    globals.set_tooltip(progress)
                    #if self._state_update_callback:
                    #    self._state_update_callback(progress)
                    
                elif message_type == "summary":
                    # Final summary
                    summary = data
                    files_new = data.get("files_new", 0)
                    files_changed = data.get("files_changed", 0)
                    files_unmodified = data.get("files_unmodified", 0)
                    total_files = data.get("total_files_processed", 0)
                    total_bytes = data.get("total_bytes_processed", 0)
                    data_added = data.get("data_added", 0)
                    total_duration = data.get("total_duration", 0)
                    
                    # Format bytes to human readable
                    total_bytes_gb = total_bytes / (1024 * 1024 * 1024)
                    data_added_mb = data_added / (1024 * 1024)
                    
                    print(f"\nBackup completed successfully!")
                    print(f"Files: {files_new} new, {files_changed} changed, {files_unmodified} unmodified")
                    print(f"Total: {total_files} files ({total_bytes_gb:.2f} GB)")
                    print(f"Data added: {data_added_mb:.2f} MB")
                    print(f"Duration: {total_duration:.1f} seconds")
                    print(f"Snapshot ID: {data.get('snapshot_id', 'N/A')}")
                    

                elif message_type == "error":
                    # Error message
                    print(f"Error: {data.get('error', 'Unknown error')}")
                    
            except json.JSONDecodeError as e:
                print(f"Failed to parse JSON: {line_str}")
                print(f"Error: {e}")

        async for line in process.stderr:
            line_str = line.decode().strip()
            if not line_str:
                continue
                
            try:
                data = json.loads(line_str)
                message_type = data.get("message_type", "")
                if message_type == "exit_error":
                    summary = data
            except json.JSONDecodeError as e:
                print(f"Failed to parse stderr JSON: {line_str}")
                print(f"Error: {e}")
        
        
        # Wait for process to complete
        exit_code = await process.wait()
        
        # Read any stderr output
        #stderr = await process.stderr.read()
        #if stderr:
        #    print("Stderr:", stderr.decode())
        
        # Calculate duration
        end = asyncio.get_event_loop().time()
        duration = int(end - start)
        
        # Determine success
        success = exit_code == 0
        
        # Store history entry
        storage = Storage()
        #if summary:
            #print(f"Summary: {summary}")
        if self.job.type == "forget":
            if success:
                summary = summary[0]
            history_entry = History(
                job_name=self.job.name,
                repo_name=self.repository.name,
                timestamp=datetime.now().isoformat(),
                success=success,
                files=0,
                bytes=0,
                duration=duration,
                snapshot_id="",
                bytes_added=0,
                exit_code = exit_code
            )
            if success:
                history_entry.summary_text = f"remove: {self._count(summary.get('remove', None))}, keep: {self._count(summary.get('keep', None))}"
            else:
                history_entry.summary_text = summary.get("message", "Unknown error")
        elif self.job.type == "backup":
            history_entry = History(
                job_name=self.job.name,
                repo_name=self.repository.name,
                timestamp=datetime.now().isoformat(),
                success=success,
                files=summary.get("total_files_processed", 0) if summary else 0,
                bytes=summary.get("total_bytes_processed", 0) if summary else 0,
                duration=duration,
                snapshot_id=summary.get("snapshot_id", "") if summary else "",
                bytes_added=data_added,
                exit_code = exit_code
            )
            if exit_code == 0:
                history_entry.summary_text = f"Files: {history_entry.files}, Bytes: {history_entry.bytes}, Duration: {history_entry.duration}s"
            else:
                history_entry.summary_text = summary.get("message", "Unknown error")

        storage.add_history(history_entry)
        print(f"History entry saved for job: {self.job.name}")
        
        if process.returncode != 0:
            print(f"Backup failed with exit code {process.returncode}")
            return None
        
        self.running = False

        return summary




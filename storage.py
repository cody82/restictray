import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class Repository:
    """Represents a restic repository configuration"""
    name: str
    url: str
    password: str


@dataclass
class Job:
    """Represents a scheduled backup job"""
    name: str
    target_repo: str
    type: str  # e.g., 'backup', 'forget', 'prune'
    schedule: str
    additional_args: str
    directory: str
    enabled: bool = True

@dataclass
class History:
    """Represents a backup history entry"""
    job_name: str
    repo_name: str
    timestamp: str # ISO format
    success: bool
    files: int
    bytes: int
    duration: int # in seconds
    snapshot_id: str
    exit_code: int = 0
    summary_text: str = ""

class Storage:
    """Handles saving and loading application data to disk"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize storage with a config directory"""
        if config_dir is None:
            # Use XDG config directory or fallback to home
            config_home = Path.home() / ".config" / "restictray"
        else:
            config_home = Path(config_dir)
        
        self.config_dir = config_home
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.repositories_file = self.config_dir / "repositories.json"
        self.jobs_file = self.config_dir / "jobs.json"
        self.settings_file = self.config_dir / "settings.json"
        self.history_file = self.config_dir / "history.json"
    
    def _load_json(self, file_path: Path) -> Any:
        """Load JSON from a file"""
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading {file_path}: {e}")
            return None
    
    def _save_json(self, file_path: Path, data: Any) -> bool:
        """Save data to a JSON file"""
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except IOError as e:
            print(f"Error saving {file_path}: {e}")
            return False
    
    # Repository methods
    def load_repositories(self) -> List[Repository]:
        """Load all repositories from disk"""
        data = self._load_json(self.repositories_file)
        if not data:
            return []
        
        return [Repository(**repo) for repo in data]
    
    def save_repositories(self, repositories: List[Repository]) -> bool:
        """Save repositories to disk"""
        data = [asdict(repo) for repo in repositories]
        return self._save_json(self.repositories_file, data)
    
    def add_repository(self, repository: Repository) -> bool:
        """Add a new repository"""
        repos = self.load_repositories()
        
        # Check if repository with same name exists
        if any(r.name == repository.name for r in repos):
            print(f"Repository '{repository.name}' already exists")
            return False
        
        repos.append(repository)
        return self.save_repositories(repos)
    
    def get_repository(self, name: str) -> Optional[Repository]:
        """Get a repository by name"""
        repos = self.load_repositories()
        for repo in repos:
            if repo.name == name:
                return repo
        return None
    
    def update_repository(self, name: str, updated_repo: Repository) -> bool:
        """Update an existing repository"""
        repos = self.load_repositories()
        
        for i, repo in enumerate(repos):
            if repo.name == name:
                repos[i] = updated_repo
                return self.save_repositories(repos)
        
        print(f"Repository '{name}' not found")
        return False
    
    def delete_repository(self, name: str) -> bool:
        """Delete a repository by name"""
        repos = self.load_repositories()
        original_len = len(repos)
        repos = [r for r in repos if r.name != name]
        
        if len(repos) == original_len:
            print(f"Repository '{name}' not found")
            return False
        
        return self.save_repositories(repos)
    
    # Job methods
    def load_jobs(self) -> List[Job]:
        """Load all jobs from disk"""
        data = self._load_json(self.jobs_file)
        if not data:
            return []
        
        return [Job(**job) for job in data]
    
    def save_jobs(self, jobs: List[Job]) -> bool:
        """Save jobs to disk"""
        data = [asdict(job) for job in jobs]
        return self._save_json(self.jobs_file, data)
    
    def add_job(self, job: Job) -> bool:
        """Add a new job"""
        jobs = self.load_jobs()
        
        # Check if job with same name exists
        if any(j.name == job.name for j in jobs):
            print(f"Job '{job.name}' already exists")
            return False
        
        jobs.append(job)
        return self.save_jobs(jobs)
    
    def get_job(self, name: str) -> Optional[Job]:
        """Get a job by name"""
        jobs = self.load_jobs()
        for job in jobs:
            if job.name == name:
                return job
        return None
    
    def update_job(self, name: str, updated_job: Job) -> bool:
        """Update an existing job"""
        jobs = self.load_jobs()
        
        for i, job in enumerate(jobs):
            if job.name == name:
                jobs[i] = updated_job
                return self.save_jobs(jobs)
        
        print(f"Job '{name}' not found")
        return False
    
    def delete_job(self, name: str) -> bool:
        """Delete a job by name"""
        jobs = self.load_jobs()
        original_len = len(jobs)
        jobs = [j for j in jobs if j.name != name]
        
        if len(jobs) == original_len:
            print(f"Job '{name}' not found")
            return False
        
        return self.save_jobs(jobs)
    
    # Settings methods
    def load_settings(self) -> Dict[str, Any]:
        """Load application settings from disk"""
        data = self._load_json(self.settings_file)
        if not data:
            return {}
        return data
    
    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """Save application settings to disk"""
        return self._save_json(self.settings_file, settings)
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a specific setting value"""
        settings = self.load_settings()
        return settings.get(key, default)
    
    def set_setting(self, key: str, value: Any) -> bool:
        """Set a specific setting value"""
        settings = self.load_settings()
        settings[key] = value
        return self.save_settings(settings)
    
    # History methods
    def load_history(self) -> List[History]:
        """Load all history entries from disk"""
        data = self._load_json(self.history_file)
        if not data:
            return []
        
        return [History(**entry) for entry in data]
    
    def save_history(self, history: List[History]) -> bool:
        """Save history entries to disk"""
        data = [asdict(entry) for entry in history]
        return self._save_json(self.history_file, data)
    
    def add_history(self, entry: History) -> bool:
        """Add a new history entry"""
        history = self.load_history()
        history.append(entry)
        return self.save_history(history)
    
    def get_history_for_job(self, job_name: str) -> List[History]:
        """Get all history entries for a specific job"""
        history = self.load_history()
        return [entry for entry in history if entry.job_name == job_name]
    
    def get_history_for_repo(self, repo_name: str) -> List[History]:
        """Get all history entries for a specific repository"""
        history = self.load_history()
        return [entry for entry in history if entry.repo_name == repo_name]
    
    def get_latest_history(self, limit: int = 10) -> List[History]:
        """Get the most recent history entries"""
        history = self.load_history()
        # Sort by timestamp in descending order
        sorted_history = sorted(history, key=lambda x: x.timestamp, reverse=True)
        return sorted_history[:limit]
    
    def clear_history(self) -> bool:
        """Clear all history entries"""
        return self.save_history([])
    
    def delete_history_before(self, timestamp: str) -> bool:
        """Delete history entries older than the specified timestamp"""
        history = self.load_history()
        filtered_history = [entry for entry in history if entry.timestamp >= timestamp]
        return self.save_history(filtered_history)

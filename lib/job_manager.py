"""
Job Manager - Track multiple parallel generation jobs and persistent history.
"""

import uuid
import json
import os
import time
from datetime import datetime
from threading import Lock
from pathlib import Path

class JobManager:
    """Manages multiple concurrent generation jobs and persists history."""

    def __init__(self, data_dir="data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

        self.history_file = self.data_dir / "history.json"
        self.jobs_file = self.data_dir / "active_jobs.json"

        self.active_jobs = {}  # job_id -> job info
        self.lock = Lock()

        # Load history on startup
        self.history = self._load_history()

    def _load_history(self):
        """Load generation history from disk. Auto-backs up corrupted files."""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                # Validate expected structure
                if not isinstance(data, dict) or "sessions" not in data or "thumbnails" not in data:
                    raise ValueError("Invalid history structure - missing required keys")
                return data
            except Exception as e:
                print(f"[JOB MANAGER] Error loading history: {e}")
                # Auto-backup corrupted file before resetting
                bak_path = self.history_file.with_suffix('.json.bak')
                try:
                    import shutil
                    shutil.copy2(str(self.history_file), str(bak_path))
                    print(f"[JOB MANAGER] Corrupted history backed up to {bak_path}")
                except Exception:
                    pass
                return {"sessions": [], "thumbnails": []}
        return {"sessions": [], "thumbnails": []}

    def _save_history(self):
        """Save history to disk atomically (write to temp, fsync, then rename)."""
        import tempfile
        fd = None
        tmp_path = None
        try:
            fd, tmp_path_str = tempfile.mkstemp(
                dir=str(self.data_dir), suffix='.tmp', prefix='history_'
            )
            tmp_path = Path(tmp_path_str)
            with os.fdopen(fd, 'w') as f:
                fd = None  # os.fdopen takes ownership of fd
                json.dump(self.history, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(self.history_file)
        except Exception as e:
            print(f"[JOB MANAGER] Error saving history: {e}")
            if fd is not None:
                os.close(fd)
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()

    def create_job(self, job_type, params):
        """Create a new generation job."""
        job_id = str(uuid.uuid4())[:8]

        job = {
            "id": job_id,
            "type": job_type,  # 'generate', 'variations', 'quick', 'full-parallel'
            "params": params,
            "status": "starting",
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "progress": {
                "phase": "initializing",
                "current": 0,
                "total": 0,
                "models": {},  # model -> {status, current, total, complete}
                "llms": {},    # llm -> {status, count, complete}
            },
            "results": [],  # thumbnails generated
            "error": None
        }

        with self.lock:
            self.active_jobs[job_id] = job

        return job_id

    def start_job(self, job_id):
        """Mark job as started."""
        with self.lock:
            if job_id in self.active_jobs:
                self.active_jobs[job_id]["status"] = "running"
                self.active_jobs[job_id]["started_at"] = datetime.now().isoformat()

    def update_job_phase(self, job_id, phase, message=None):
        """Update the current phase of a job."""
        with self.lock:
            if job_id in self.active_jobs:
                self.active_jobs[job_id]["progress"]["phase"] = phase
                if message:
                    self.active_jobs[job_id]["progress"]["message"] = message

    def update_job_progress(self, job_id, current, total):
        """Update overall progress."""
        with self.lock:
            if job_id in self.active_jobs:
                self.active_jobs[job_id]["progress"]["current"] = current
                self.active_jobs[job_id]["progress"]["total"] = total

    def update_model_status(self, job_id, model, status, current=0, total=0, complete=False):
        """Update a specific model's progress within a job."""
        with self.lock:
            if job_id in self.active_jobs:
                self.active_jobs[job_id]["progress"]["models"][model] = {
                    "status": status,
                    "current": current,
                    "total": total,
                    "complete": complete
                }

    def update_llm_status(self, job_id, llm, status, count=0, complete=False):
        """Update LLM ideation progress."""
        with self.lock:
            if job_id in self.active_jobs:
                self.active_jobs[job_id]["progress"]["llms"][llm] = {
                    "status": status,
                    "count": count,
                    "complete": complete
                }

    def add_result(self, job_id, thumbnail_data):
        """Add a generated thumbnail to job results and history."""
        with self.lock:
            if job_id in self.active_jobs:
                self.active_jobs[job_id]["results"].append(thumbnail_data)
                self.active_jobs[job_id]["progress"]["current"] = len(self.active_jobs[job_id]["results"])

            # Also add to persistent history
            thumbnail_record = {
                **thumbnail_data,
                "job_id": job_id,
                "generated_at": datetime.now().isoformat()
            }
            self.history["thumbnails"].append(thumbnail_record)

            # Keep history manageable (last 1000 thumbnails)
            if len(self.history["thumbnails"]) > 1000:
                self.history["thumbnails"] = self.history["thumbnails"][-1000:]

            self._save_history()

    def update_result(self, job_id, file_path, updates):
        """Update an existing result with new data (e.g., evaluation scores)."""
        with self.lock:
            # Update in history
            for thumb in self.history["thumbnails"]:
                if thumb["job_id"] == job_id and thumb["file_path"] == file_path:
                    thumb.update(updates)
                    break

            # Update in active job if still running
            if job_id in self.active_jobs:
                for result in self.active_jobs[job_id]["results"]:
                    if result["file_path"] == file_path:
                        result.update(updates)
                        break

            self._save_history()

    def complete_job(self, job_id, success=True, error=None):
        """Mark job as complete and archive to history."""
        with self.lock:
            if job_id in self.active_jobs:
                job = self.active_jobs[job_id]
                job["status"] = "completed" if success else "failed"
                job["completed_at"] = datetime.now().isoformat()
                job["error"] = error

                # Archive to session history
                session_record = {
                    "id": job_id,
                    "type": job["type"],
                    "params": job["params"],
                    "created_at": job["created_at"],
                    "completed_at": job["completed_at"],
                    "thumbnail_count": len(job["results"]),
                    "status": job["status"]
                }
                self.history["sessions"].append(session_record)

                # Keep last 100 sessions
                if len(self.history["sessions"]) > 100:
                    self.history["sessions"] = self.history["sessions"][-100:]

                self._save_history()

                # Clean up completed job from active_jobs after saving
                del self.active_jobs[job_id]

                # Also clean up any stale jobs while we're at it
                stale = [jid for jid, j in self.active_jobs.items()
                         if j["status"] in ("completed", "failed")]
                for jid in stale:
                    del self.active_jobs[jid]

    def get_job(self, job_id):
        """Get job status."""
        with self.lock:
            return self.active_jobs.get(job_id)

    def get_all_jobs(self):
        """Get all active jobs."""
        with self.lock:
            return dict(self.active_jobs)

    def get_history(self, limit=50, offset=0):
        """Get thumbnail history."""
        thumbnails = list(reversed(self.history["thumbnails"]))
        return {
            "thumbnails": thumbnails[offset:offset+limit],
            "total": len(self.history["thumbnails"]),
            "sessions": list(reversed(self.history["sessions"]))[:20]
        }

    def cleanup_old_jobs(self, max_age_seconds=3600):
        """Remove completed jobs older than max_age."""
        now = time.time()
        with self.lock:
            to_remove = []
            for job_id, job in self.active_jobs.items():
                if job["status"] in ("completed", "failed"):
                    if job["completed_at"]:
                        completed = datetime.fromisoformat(job["completed_at"])
                        age = now - completed.timestamp()
                        if age > max_age_seconds:
                            to_remove.append(job_id)

            for job_id in to_remove:
                del self.active_jobs[job_id]


# Global instance - use persistent volume on Railway
_persistent = Path('/app/persistent/data')
_default_dir = _persistent if _persistent.parent.exists() else Path('data')
job_manager = JobManager(str(_default_dir))

"""
Thread-safe event store for generation jobs.

Decouples generation (background threads) from SSE delivery (browser connections).
Generation pushes events to the store. SSE endpoints subscribe and get replay + live stream.
This means page refresh doesn't kill generation — the browser just reconnects.
"""

import threading
import queue
import time
from datetime import datetime


class JobRecord:
    """Tracks a single generation job's events and subscribers."""

    def __init__(self, job_id, params):
        self.id = job_id
        self.status = 'running'  # running, complete, error
        self.params = params
        self.events = []  # all SSE event dicts, in order
        self.subscribers = []  # list of queue.Queue for live subscribers
        self.created_at = time.time()
        self.completed_at = None
        self.image_count = 0
        self.total_concepts = 0
        self.current_concept = 0


class JobEventStore:
    """
    Thread-safe event store with replay + live subscription.

    Usage:
        # Producer (generation thread):
        store.create_job(job_id, params)
        store.push_event(job_id, {'type': 'image_generated', ...})
        store.complete_job(job_id)

        # Consumer (SSE endpoint):
        past_events, live_queue = store.subscribe(job_id)
        for event in past_events:
            yield sse_message(event)
        while True:
            event = live_queue.get()
            if event is None: break  # job done
            yield sse_message(event)
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.jobs = {}  # job_id -> JobRecord

    def create_job(self, job_id, params):
        """Initialize a new job record."""
        with self.lock:
            self.jobs[job_id] = JobRecord(job_id, params)

    def push_event(self, job_id, event_dict):
        """Append event to history AND push to all subscriber queues."""
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            job.events.append(event_dict)

            # Track progress
            etype = event_dict.get('type', '')
            if etype == 'image_generated':
                job.image_count += 1
            elif etype == 'concept_start':
                job.current_concept = event_dict.get('concept_num', 0)
                job.total_concepts = event_dict.get('total_concepts', 0)

            # Push to all live subscribers
            dead = []
            for q in job.subscribers:
                try:
                    q.put_nowait(event_dict)
                except Exception:
                    dead.append(q)
            for q in dead:
                job.subscribers.remove(q)

    def complete_job(self, job_id, status='complete'):
        """Mark job as done and notify all subscribers with sentinel."""
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            job.status = status
            job.completed_at = time.time()
            # Send None sentinel to all subscribers
            for q in job.subscribers:
                try:
                    q.put_nowait(None)
                except Exception:
                    pass
            job.subscribers.clear()

    def subscribe(self, job_id):
        """
        Subscribe to a job's events.

        Returns (past_events, live_queue) under a single lock acquisition
        so no events are missed between snapshot and registration.

        If job is already complete, returns (all_events, None).
        If job not found, returns (None, None).
        """
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return None, None

            past_events = list(job.events)  # snapshot

            if job.status != 'running':
                return past_events, None  # job already done, no live queue needed

            live_queue = queue.Queue(maxsize=1000)
            job.subscribers.append(live_queue)
            return past_events, live_queue

    def unsubscribe(self, job_id, q):
        """Remove a subscriber queue (called when SSE client disconnects)."""
        with self.lock:
            job = self.jobs.get(job_id)
            if job and q in job.subscribers:
                job.subscribers.remove(q)

    def get_active_jobs(self):
        """Return summary of all running and recently-completed jobs."""
        with self.lock:
            now = time.time()
            result = []
            for job in self.jobs.values():
                # Include running jobs and jobs completed within last 5 minutes
                if job.status == 'running' or (job.completed_at and now - job.completed_at < 300):
                    result.append({
                        'id': job.id,
                        'status': job.status,
                        'params': job.params,
                        'image_count': job.image_count,
                        'current_concept': job.current_concept,
                        'total_concepts': job.total_concepts,
                        'created_at': job.created_at,
                        'completed_at': job.completed_at,
                    })
            return result

    def get_job_results(self, job_id):
        """Return all image_generated events for a job."""
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return None
            return [e for e in job.events if e.get('type') == 'image_generated']

    def get_job_status(self, job_id):
        """Return job status or None if not found."""
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return None
            return {
                'id': job.id,
                'status': job.status,
                'image_count': job.image_count,
                'current_concept': job.current_concept,
                'total_concepts': job.total_concepts,
            }

    def cleanup(self):
        """Remove jobs completed more than 1 hour ago."""
        with self.lock:
            now = time.time()
            expired = [
                jid for jid, job in self.jobs.items()
                if job.status != 'running' and job.completed_at and now - job.completed_at > 3600
            ]
            for jid in expired:
                del self.jobs[jid]


# Global singleton
job_event_store = JobEventStore()

import threading
import time
from collections import deque

from fastapi import HTTPException


class RateLimiter:
    def __init__(self, limit):
        self.limit = limit
        self.events = {}
        self.lock = threading.Lock()

    def check(self, key):
        now = time.monotonic()
        with self.lock:
            self.events = {k: v for k, v in self.events.items() if v and v[-1] > now - 60}
            if key not in self.events and len(self.events) >= 10000:
                raise HTTPException(429, "Máy chủ đang bận.")
            queue = self.events.setdefault(key, deque())
            while queue and queue[0] <= now - 60:
                queue.popleft()
            if len(queue) >= self.limit:
                raise HTTPException(
                    429,
                    "Quá nhiều yêu cầu. Hãy thử lại sau.",
                    headers={"Retry-After": "60"},
                )
            queue.append(now)

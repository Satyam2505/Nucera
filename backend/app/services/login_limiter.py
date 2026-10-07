"""A small in-memory limit on failed sign-in attempts.

Passwords can be guessed by trying them one after another, so repeated failures are
slowed down: after LOGIN_MAX_FAILURES wrong passwords for one email from one address
within LOGIN_WINDOW_SECONDS, further attempts are refused (even with the right
password) until the oldest failure ages out of the window. A second, looser cap per
address stops one machine from spraying many different emails.

The key includes the caller's address, so a stranger cannot lock the real owner out
by failing on their email from elsewhere. Successful sign-ins are not counted, and
one clears that email's failures from that address.

It lives in this process's memory: right for a single-user app run by one server, and
it resets on restart. Behind a reverse proxy every request would look like it comes
from the proxy's address; the app is meant to be run directly (see README).
"""

import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional, Tuple

from app.config import LOGIN_IP_MAX_FAILURES, LOGIN_MAX_FAILURES, LOGIN_WINDOW_SECONDS

# Bound on how many (address, email) pairs are remembered, so a flood of made-up
# emails can't grow the table without limit.
MAX_TRACKED_KEYS = 10_000


class LoginRateLimiter:
    def __init__(
        self,
        max_failures: int = LOGIN_MAX_FAILURES,
        window_seconds: float = LOGIN_WINDOW_SECONDS,
        ip_max_failures: int = LOGIN_IP_MAX_FAILURES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self.ip_max_failures = ip_max_failures
        self._clock = clock
        self._lock = threading.Lock()
        self._by_pair: Dict[Tuple[str, str], Deque[float]] = {}
        self._by_ip: Dict[str, Deque[float]] = {}

    def _prune(self, failures: Deque[float], now: float) -> None:
        while failures and now - failures[0] >= self.window:
            failures.popleft()

    def _retry_after(self, failures: Optional[Deque[float]], limit: int, now: float) -> int:
        if not failures:
            return 0
        self._prune(failures, now)
        if len(failures) < limit:
            return 0
        # The next attempt is allowed once enough old failures have expired to get under the limit.
        release_at = failures[len(failures) - limit] + self.window
        return max(1, int(release_at - now + 0.999))

    def check(self, ip: str, email: str) -> int:
        """Seconds until this address may try this email again; 0 if it may try now."""
        now = self._clock()
        with self._lock:
            return max(
                self._retry_after(self._by_pair.get((ip, email)), self.max_failures, now),
                self._retry_after(self._by_ip.get(ip), self.ip_max_failures, now),
            )

    def record_failure(self, ip: str, email: str) -> None:
        now = self._clock()
        with self._lock:
            if len(self._by_pair) >= MAX_TRACKED_KEYS and (ip, email) not in self._by_pair:
                self._evict(now)
            self._by_pair.setdefault((ip, email), deque()).append(now)
            self._by_ip.setdefault(ip, deque()).append(now)

    def record_success(self, ip: str, email: str) -> None:
        with self._lock:
            self._by_pair.pop((ip, email), None)

    def _evict(self, now: float) -> None:
        """Drop expired entries; if the table is still full, drop the oldest."""
        for key in [k for k, v in self._by_pair.items() if not v or now - v[-1] >= self.window]:
            del self._by_pair[key]
        while len(self._by_pair) >= MAX_TRACKED_KEYS:
            del self._by_pair[next(iter(self._by_pair))]
        for ip in [k for k, v in self._by_ip.items() if not v or now - v[-1] >= self.window]:
            del self._by_ip[ip]

    def reset(self) -> None:
        with self._lock:
            self._by_pair.clear()
            self._by_ip.clear()


# The one shared instance the login route uses.
limiter = LoginRateLimiter()

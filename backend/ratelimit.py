import math
import os
import threading
import time
from collections import defaultdict, deque

from common import ApiError


# True unless the limits were switched off in .env.
def enabled():
    return os.environ.get("RATE_LIMIT_ENABLED", "1") != "0"


# Allows `max_failures` failures per `window_seconds` for each key (an address, an email, a user).
class FailureLimiter:

    def __init__(self, name, max_failures, window_seconds, message):
        self.name, self.max_failures, self.window, self.message = name, max_failures, window_seconds, message
        self._failures = defaultdict(deque)
        self._lock = threading.Lock()

    # Drops the failures that are older than the window.
    def _trim(self, key, now):
        recent = self._failures[key]
        while recent and now - recent[0] > self.window:
            recent.popleft()
        if not recent:
            self._failures.pop(key, None)
        return recent

    # Raises a 429 when this key has used up its failures; the answer says how long to wait.
    def check(self, *keys):
        if not enabled():
            return
        now = time.monotonic()
        with self._lock:
            waits = []
            for key in keys:
                recent = self._trim(key, now)
                if len(recent) >= self.max_failures:
                    waits.append(self.window - (now - recent[0]))
        if waits:
            seconds = max(1, math.ceil(max(waits)))
            minutes = math.ceil(seconds / 60)
            raise ApiError(f"{self.message} Please wait {minutes} minute{'s' if minutes != 1 else ''} and try again.",
                           429, "RATE_LIMITED", retry_after=seconds)

    # Counts one failed try against each key.
    def fail(self, *keys):
        now = time.monotonic()
        with self._lock:
            for key in keys:
                self._trim(key, now)
                self._failures[key].append(now)

    # Forgets a key's failures (after a correct password).
    def clear(self, *keys):
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)

    # Forgets everything (used between tests).
    def reset(self):
        with self._lock:
            self._failures.clear()


def _number(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


WINDOW = _number("RATE_LIMIT_WINDOW_SECONDS", 600)
SIGN_IN = FailureLimiter("sign-in", _number("RATE_LIMIT_SIGN_IN", 8), WINDOW,
                         "Too many failed sign-in attempts for this account.")
SIGN_IN_ANY = FailureLimiter("sign-in-address", _number("RATE_LIMIT_SIGN_IN_PER_ADDRESS", 30), WINDOW,
                             "Too many failed sign-in attempts from this connection.")
ORDER_LOOKUP = FailureLimiter("order-lookup", _number("RATE_LIMIT_ORDER_LOOKUP", 10), WINDOW,
                              "Too many order look-ups that found nothing.")
PASSWORD_CHECK = FailureLimiter("password-check", _number("RATE_LIMIT_PASSWORD_CHECK", 5), WINDOW,
                                "Too many wrong passwords.")

ALL = (SIGN_IN, SIGN_IN_ANY, ORDER_LOOKUP, PASSWORD_CHECK)


# Clears every limiter (tests start each test from a clean slate).
def reset_all():
    for limiter in ALL:
        limiter.reset()

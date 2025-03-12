import time


class ApiRateLimiter:
    """Handles rate limiting for API calls with exponential backoff."""

    def __init__(self):
        self.failures = {}
        self.backoff_times = {}

    def should_retry(self, key):
        """Determine if we should retry a failed API call based on exponential backoff."""
        if key not in self.failures:
            return True

        if key not in self.backoff_times:
            return True

        current_time = time.time()
        if current_time > self.backoff_times[key]:
            return True

        return False

    def record_failure(self, key):
        """Record an API failure and set the backoff time."""
        if key not in self.failures:
            self.failures[key] = 1
        else:
            self.failures[key] += 1

        # Calculate backoff time: 2^failures seconds, max 10 minutes
        backoff_seconds = min(2 ** self.failures[key], 600)
        self.backoff_times[key] = time.time() + backoff_seconds

        return backoff_seconds

    def record_success(self, key):
        """Reset failure count after a successful API call."""
        if key in self.failures:
            del self.failures[key]

        if key in self.backoff_times:
            del self.backoff_times[key]
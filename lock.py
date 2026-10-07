import threading
import time
from collections import deque

class ReaderPreferredLock:
    def __init__(self):
        self._mutex = threading.Lock()
        self._write_lock = threading.Lock()
        self._read_count = 0

    def acquire_read(self):
        with self._mutex:
            self._read_count += 1
            if self._read_count == 1:
                self._write_lock.acquire()

    def release_read(self):
        with self._mutex:
            self._read_count -= 1
            if self._read_count == 0:
                self._write_lock.release()

    def acquire_write(self):
        self._write_lock.acquire()

    def release_write(self):
        self._write_lock.release()


class WriterPreferredLock:
    def __init__(self):
        self._cond = threading.Condition()
        self._active_readers = 0
        self._active_writers = 0
        self._waiting_writers = 0
        self._waiting_readers = 0

    def acquire_read(self):
        with self._cond:
            self._waiting_readers += 1
            while self._active_writers > 0 or self._waiting_writers > 0:
                self._cond.wait()
            self._waiting_readers -= 1
            self._active_readers += 1

    def release_read(self):
        with self._cond:
            self._active_readers -= 1
            if self._active_readers == 0:
                self._cond.notify_all()

    def acquire_write(self):
        with self._cond:
            self._waiting_writers += 1
            while self._active_readers > 0 or self._active_writers > 0:
                self._cond.wait()
            self._waiting_writers -= 1
            self._active_writers += 1

    def release_write(self):
        with self._cond:
            self._active_writers -= 1
            self._cond.notify_all()


class FairLock:
    def __init__(self):
        self._service_queue = threading.Lock()
        self._mutex = threading.Lock()
        self._write_lock = threading.Lock()
        self._read_count = 0

    def acquire_read(self):
        self._service_queue.acquire()
        self._mutex.acquire()
        self._read_count += 1
        if self._read_count == 1:
            self._write_lock.acquire()
        self._mutex.release()
        self._service_queue.release()

    def release_read(self):
        with self._mutex:
            self._read_count -= 1
            if self._read_count == 0:
                self._write_lock.release()

    def acquire_write(self):
        self._service_queue.acquire()
        self._write_lock.acquire()
        self._service_queue.release()

    def release_write(self):
        self._write_lock.release()


class FIFOLock:
    def __init__(self):
        self._cond = threading.Condition()
        self._queue = deque()
        self._active_readers = 0
        self._active_writer = False

    def acquire_read(self):
        current_thread = threading.current_thread()
        with self._cond:
            self._queue.append((current_thread, 'R'))
            while not self._can_read(current_thread):
                self._cond.wait()
            self._queue.remove((current_thread, 'R'))
            self._active_readers += 1
            self._cond.notify_all()

    def _can_read(self, thread):
        if self._active_writer:
            return False
        for q_thread, q_type in self._queue:
            if q_thread == thread:
                return True
            if q_type == 'W':
                return False
        return False

    def release_read(self):
        with self._cond:
            self._active_readers -= 1
            if self._active_readers == 0:
                self._cond.notify_all()

    def acquire_write(self):
        current_thread = threading.current_thread()
        with self._cond:
            self._queue.append((current_thread, 'W'))
            while self._active_readers > 0 or self._active_writer or self._queue[0][0] != current_thread:
                self._cond.wait()
            self._queue.popleft()
            self._active_writer = True

    def release_write(self):
        with self._cond:
            self._active_writer = False
            self._cond.notify_all()


class AgingLock:
    """Dual Aging Lock — dynamic starvation mitigation for both sides.

    Behaviour
    ---------
    The lock operates with a configurable *base preference* (``'reader'`` or
    ``'writer'``).  This intentionally creates starvation pressure on the
    non-preferred side — exactly the condition the aging mechanism is designed
    to detect and mitigate.

    * **Writer-starvation mitigation** (base_preference='reader'):
      When any waiting writer's age exceeds ``starvation_threshold``:

      1. **Detects** — logs a ``STARVATION_DETECTED`` event.
      2. **Responds** — closes the reader gate and logs ``MITIGATION_TRIGGERED``.
      3. **Drains** — waits for currently-active readers to finish.
      4. **Admits** — lets the starved writer proceed.
      5. **Recovers** — reopens reader gate, logs ``MITIGATION_RESOLVED``.

    * **Reader-starvation mitigation** (base_preference='writer'):
      When any waiting reader's age exceeds ``starvation_threshold``:

      1. **Detects** — logs a ``STARVATION_DETECTED`` event.
      2. **Responds** — closes the writer gate and logs ``MITIGATION_TRIGGERED``.
      3. **Drains** — waits for the active writer to finish.
      4. **Admits** — lets all starved readers proceed (batch boost).
      5. **Recovers** — reopens writer gate, logs ``MITIGATION_RESOLVED``.

    Parameters
    ----------
    starvation_threshold : float
        Seconds a thread may wait before the aging mechanism activates.
    metrics_collector : MetricsCollector or None
        If provided, mitigation events are recorded for reporting.
    base_preference : str
        ``'reader'`` (default) or ``'writer'``.  Determines the lock's
        normal-mode behaviour and which side naturally faces starvation.
    """

    def __init__(self, starvation_threshold=0.8, metrics_collector=None,
                 base_preference='reader'):
        self._cond = threading.Condition()

        # Active state
        self._active_readers = 0
        self._active_writer = False

        # Waiting queues: thread-name → arrival timestamp
        self._waiting_writers = {}
        self._waiting_readers = {}

        # Gates — when False, new threads of that type must block
        self._reader_gate_open = True
        self._writer_gate_open = True

        # Mitigation state
        self._mitigation_active = False
        self._mitigation_side = None      # 'writer' or 'reader'
        self._boosted_writer = None       # name of the boosted writer
        self._boosted_readers = set()     # names of boosted readers

        # Configuration
        self._threshold = starvation_threshold
        self._metrics = metrics_collector
        self._base_preference = base_preference

    # ------------------------------------------------------------------
    # Reader path
    # ------------------------------------------------------------------

    def acquire_read(self):
        current = threading.current_thread().name
        with self._cond:
            arrival = time.time()
            self._waiting_readers[current] = arrival

            while True:
                # --- Can this reader enter? ---
                can_enter = False

                if not self._active_writer:
                    if current in self._boosted_readers:
                        # Boosted by aging → bypass all preference checks
                        can_enter = True
                    elif self._reader_gate_open:
                        if self._base_preference == 'reader':
                            # Reader-preferred: enter freely
                            can_enter = True
                        else:
                            # Writer-preferred: also check no writers waiting
                            if not self._waiting_writers:
                                can_enter = True

                if can_enter:
                    break

                # --- Reader-side aging check ---
                now = time.time()
                for r_name, r_arrival in list(self._waiting_readers.items()):
                    age = now - r_arrival
                    if age >= self._threshold and not self._mitigation_active:
                        # >>> READER STARVATION DETECTED <<<
                        self._mitigation_active = True
                        self._mitigation_side = 'reader'
                        self._writer_gate_open = False
                        # Boost ALL currently waiting readers as a batch
                        self._boosted_readers = set(self._waiting_readers.keys())
                        if self._metrics:
                            self._metrics.record_starvation_detected(
                                r_name, age, self._threshold)
                            self._metrics.record_mitigation_triggered(
                                r_name, "WRITER_GATE_CLOSED")
                        self._cond.notify_all()
                        break  # trigger once

                self._cond.wait(timeout=0.05)

            # Reader is now admitted
            del self._waiting_readers[current]
            # Note: do NOT discard from _boosted_readers here — that happens
            # in release_read so we can track when all boosted reads complete.
            self._active_readers += 1

    def release_read(self):
        with self._cond:
            current = threading.current_thread().name
            self._active_readers -= 1
            self._boosted_readers.discard(current)

            # If all boosted readers have completed → resolve reader-side
            # mitigation and reopen the writer gate.
            if (self._mitigation_active
                    and self._mitigation_side == 'reader'
                    and not self._boosted_readers):
                if self._metrics:
                    self._metrics.record_mitigation_resolved(
                        current, action="WRITER_GATE_REOPENED")
                self._mitigation_active = False
                self._mitigation_side = None
                self._writer_gate_open = True
                self._cond.notify_all()

            if self._active_readers == 0:
                self._cond.notify_all()

    # ------------------------------------------------------------------
    # Writer path — with aging detection
    # ------------------------------------------------------------------

    def acquire_write(self):
        current = threading.current_thread().name
        with self._cond:
            arrival = time.time()
            self._waiting_writers[current] = arrival

            while True:
                # --- Can this writer enter? ---
                can_enter = False

                if not self._active_writer and self._active_readers == 0:
                    if self._boosted_writer == current:
                        # Boosted by aging → enter immediately
                        can_enter = True
                    elif self._writer_gate_open and self._boosted_writer is None:
                        # No mitigation blocking writers, no other writer boosted
                        can_enter = True

                if can_enter:
                    break

                # --- Writer-side aging check ---
                now = time.time()
                for w_name, w_arrival in list(self._waiting_writers.items()):
                    age = now - w_arrival
                    if age >= self._threshold and not self._mitigation_active:
                        # >>> WRITER STARVATION DETECTED <<<
                        self._mitigation_active = True
                        self._mitigation_side = 'writer'
                        self._reader_gate_open = False
                        self._boosted_writer = w_name
                        if self._metrics:
                            self._metrics.record_starvation_detected(
                                w_name, age, self._threshold)
                            self._metrics.record_mitigation_triggered(
                                w_name, "READER_GATE_CLOSED")
                        # Wake everyone so readers see the closed gate and
                        # stop entering; also so the boosted writer re-checks.
                        self._cond.notify_all()
                        break  # only boost one writer at a time

                # Wait with a short timeout so we can re-check ages
                self._cond.wait(timeout=0.05)

            # Writer is now admitted
            del self._waiting_writers[current]
            self._active_writer = True

    def release_write(self):
        with self._cond:
            current = threading.current_thread().name
            self._active_writer = False

            # If this was the boosted writer, end writer-side mitigation
            if (self._boosted_writer == current
                    and self._mitigation_active
                    and self._mitigation_side == 'writer'):
                if self._metrics:
                    self._metrics.record_mitigation_resolved(
                        current, action="READER_GATE_REOPENED")
                self._boosted_writer = None
                self._mitigation_active = False
                self._mitigation_side = None
                self._reader_gate_open = True

            self._cond.notify_all()

    # ------------------------------------------------------------------
    # Introspection helpers (used by the dashboard)
    # ------------------------------------------------------------------

    def is_mitigation_active(self):
        """Return True if the aging mechanism is currently intervening."""
        with self._cond:
            return self._mitigation_active

    def get_mitigation_side(self):
        """Return 'writer', 'reader', or None."""
        with self._cond:
            return self._mitigation_side

    def get_boosted_writer(self):
        """Return the name of the currently-boosted writer, or None."""
        with self._cond:
            return self._boosted_writer

    def get_boosted_readers(self):
        """Return the set of currently-boosted reader names."""
        with self._cond:
            return set(self._boosted_readers)

    def get_waiting_writer_ages(self):
        """Return a dict of writer-name → seconds-waited for queued writers."""
        with self._cond:
            now = time.time()
            return {name: now - arrival
                    for name, arrival in self._waiting_writers.items()}

    def get_waiting_reader_ages(self):
        """Return a dict of reader-name → seconds-waited for queued readers."""
        with self._cond:
            now = time.time()
            return {name: now - arrival
                    for name, arrival in self._waiting_readers.items()}

    def get_threshold(self):
        return self._threshold

    def get_base_preference(self):
        return self._base_preference

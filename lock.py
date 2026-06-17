import threading
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

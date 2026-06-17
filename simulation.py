import threading
import time
import random
from metrics import MetricsCollector

class SharedResource:
    def __init__(self):
        self.value = 0
        self.last_writer = None

    def read(self):
        return self.value

    def write(self, writer_name):
        self.value += 1
        self.last_writer = writer_name
        return self.value


class ReaderThread(threading.Thread):
    def __init__(self, thread_id, lock, resource, metrics, config, stop_event):
        super().__init__(name=f"Reader-{thread_id}")
        self.lock = lock
        self.resource = resource
        self.metrics = metrics
        self.config = config
        self.stop_event = stop_event

    def run(self):
        self.metrics.set_thread_state(self.name, 'IDLE')
        
        time.sleep(random.uniform(0.0, 0.5))

        while not self.stop_event.is_set():
            self.metrics.set_thread_state(self.name, 'IDLE')
            idle_time = random.uniform(
                self.config['reader_idle_min'], 
                self.config['reader_idle_max']
            )
            
            t_slept = 0.0
            while t_slept < idle_time:
                if self.stop_event.is_set():
                    return
                time.sleep(min(0.05, idle_time - t_slept))
                t_slept += 0.05

            arrival_time = time.time()
            self.metrics.set_thread_state(self.name, 'WAITING')
            
            self.lock.acquire_read()
            
            start_time = time.time()
            self.metrics.set_thread_state(self.name, 'RUNNING')
            
            read_value = self.resource.read()
            
            read_duration = random.uniform(
                self.config['reader_work_min'],
                self.config['reader_work_max']
            )
            time.sleep(read_duration)
            
            self.lock.release_read()
            end_time = time.time()
            
            self.metrics.record_operation(self.name, 'READ', arrival_time, start_time, end_time)


class WriterThread(threading.Thread):
    def __init__(self, thread_id, lock, resource, metrics, config, stop_event):
        super().__init__(name=f"Writer-{thread_id}")
        self.lock = lock
        self.resource = resource
        self.metrics = metrics
        self.config = config
        self.stop_event = stop_event

    def run(self):
        self.metrics.set_thread_state(self.name, 'IDLE')
        
        time.sleep(random.uniform(0.0, 0.5))

        while not self.stop_event.is_set():
            self.metrics.set_thread_state(self.name, 'IDLE')
            idle_time = random.uniform(
                self.config['writer_idle_min'], 
                self.config['writer_idle_max']
            )
            
            t_slept = 0.0
            while t_slept < idle_time:
                if self.stop_event.is_set():
                    return
                time.sleep(min(0.05, idle_time - t_slept))
                t_slept += 0.05

            arrival_time = time.time()
            self.metrics.set_thread_state(self.name, 'WAITING')
            
            self.lock.acquire_write()
            
            start_time = time.time()
            self.metrics.set_thread_state(self.name, 'RUNNING')
            
            write_result = self.resource.write(self.name)
            
           
            write_duration = random.uniform(
                self.config['writer_work_min'],
                self.config['writer_work_max']
            )
            time.sleep(write_duration)
            
            
            self.lock.release_write()
            end_time = time.time()
            
            self.metrics.record_operation(self.name, 'WRITE', arrival_time, start_time, end_time)


class SimulationManager:
    """Orchestrates spawning, running, and tearing down reader and writer threads."""
    def __init__(self, lock, num_readers, num_writers, config):
        self.lock = lock
        self.num_readers = num_readers
        self.num_writers = num_writers
        self.config = config
        
        self.resource = SharedResource()
        self.metrics = MetricsCollector()
        self.stop_event = threading.Event()
        self.threads = []

    def start(self):
        self.stop_event.clear()
        self.threads = []

        for i in range(1, self.num_readers + 1):
            t = ReaderThread(
                thread_id=i,
                lock=self.lock,
                resource=self.resource,
                metrics=self.metrics,
                config=self.config,
                stop_event=self.stop_event
            )
            self.threads.append(t)

        for i in range(1, self.num_writers + 1):
            t = WriterThread(
                thread_id=i,
                lock=self.lock,
                resource=self.resource,
                metrics=self.metrics,
                config=self.config,
                stop_event=self.stop_event
            )
            self.threads.append(t)

        for t in self.threads:
            t.start()

    def stop(self):
        self.stop_event.set()
        
        for t in self.threads:
            t.join(timeout=1.0)

import threading
import time
import math

class MetricsCollector:

    def __init__(self):
        self._lock = threading.RLock()
        
        self.thread_states = {}

        self.total_reads = 0
        self.total_writes = 0
        self.read_wait_times = []
        self.write_wait_times = []
        self.read_active_times = []
        self.write_active_times = []
        self.history = []
        
        
        self.start_time = time.time()

    def set_thread_state(self, thread_name, state):
        with self._lock:
            self.thread_states[thread_name] = (state, time.time())

    def record_operation(self, thread_name, op_type, arrival, start, end):
        wait_time = start - arrival
        active_time = end - start
        
        with self._lock:
            self.history.append({
                'thread': thread_name,
                'type': op_type,
                'arrival': arrival,
                'start': start,
                'end': end,
                'wait_time': wait_time,
                'active_time': active_time
            })
            
            if op_type == 'READ':
                self.total_reads += 1
                self.read_wait_times.append(wait_time)
                self.read_active_times.append(active_time)
            elif op_type == 'WRITE':
                self.total_writes += 1
                self.write_wait_times.append(wait_time)
                self.write_active_times.append(active_time)

    def get_summary(self):
        with self._lock:
            elapsed = time.time() - self.start_time
            
            avg_read_wait = sum(self.read_wait_times) / len(self.read_wait_times) if self.read_wait_times else 0.0
            avg_write_wait = sum(self.write_wait_times) / len(self.write_wait_times) if self.write_wait_times else 0.0
            
            max_read_wait = max(self.read_wait_times) if self.read_wait_times else 0.0
            max_write_wait = max(self.write_wait_times) if self.write_wait_times else 0.0
            
            std_read_wait = self._calc_stddev(self.read_wait_times, avg_read_wait)
            std_write_wait = self._calc_stddev(self.write_wait_times, avg_write_wait)
            
            total_ops = self.total_reads + self.total_writes
            throughput = total_ops / elapsed if elapsed > 0 else 0.0
            
            
            starvation_ratio = 0.0
            if avg_read_wait > 0 and avg_write_wait > 0:
                starvation_ratio = avg_write_wait / avg_read_wait if avg_write_wait > avg_read_wait else avg_read_wait / avg_write_wait
            elif avg_write_wait > 0:
                starvation_ratio = float('inf') 
            elif avg_read_wait > 0:
                starvation_ratio = float('inf') 
                
            return {
                'elapsed_time': elapsed,
                'total_reads': self.total_reads,
                'total_writes': self.total_writes,
                'avg_read_wait': avg_read_wait,
                'avg_write_wait': avg_write_wait,
                'max_read_wait': max_read_wait,
                'max_write_wait': max_write_wait,
                'std_read_wait': std_read_wait,
                'std_write_wait': std_write_wait,
                'throughput': throughput,
                'starvation_ratio': starvation_ratio
            }

    def _calc_stddev(self, data, mean):
        if len(data) <= 1:
            return 0.0
        variance = sum((x - mean) ** 2 for x in data) / (len(data) - 1)
        return math.sqrt(variance)

    def get_snapshot(self):
        """Returns a snapshot of thread counts and current states for visual rendering."""
        with self._lock:
            states_counts = {'IDLE': 0, 'WAITING': 0, 'RUNNING': 0}
            reader_states = {'IDLE': 0, 'WAITING': 0, 'RUNNING': 0}
            writer_states = {'IDLE': 0, 'WAITING': 0, 'RUNNING': 0}
            
            for t_name, (state, _) in self.thread_states.items():
                states_counts[state] += 1
                if t_name.startswith('Reader'):
                    reader_states[state] += 1
                elif t_name.startswith('Writer'):
                    writer_states[state] += 1
            
            return {
                'states': states_counts,
                'readers': reader_states,
                'writers': writer_states,
                'history_tail': self.history[-5:] if self.history else []
            }

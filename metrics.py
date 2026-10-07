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

        # --- Mitigation event tracking ---
        self.starvation_alerts = []    # Detection events
        self.mitigation_events = []    # Trigger + resolution events
        
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

    # ------------------------------------------------------------------
    # Mitigation event recording (called by AgingLock / Dual Aging Lock)
    # ------------------------------------------------------------------

    def record_starvation_detected(self, thread_name, wait_duration, threshold):
        """Log that a thread (reader or writer) has exceeded the starvation threshold."""
        with self._lock:
            self.starvation_alerts.append({
                'timestamp': time.time(),
                'thread': thread_name,
                'wait_duration': wait_duration,
                'threshold': threshold,
                'event': 'STARVATION_DETECTED'
            })

    def record_mitigation_triggered(self, thread_name, action):
        """Log that the aging mechanism has activated (gate closed on one side)."""
        with self._lock:
            self.mitigation_events.append({
                'timestamp': time.time(),
                'thread': thread_name,
                'action': action,
                'event': 'MITIGATION_TRIGGERED'
            })

    def record_mitigation_resolved(self, thread_name, action):
        """Log that the boosted thread(s) finished and normal mode resumed."""
        with self._lock:
            self.mitigation_events.append({
                'timestamp': time.time(),
                'thread': thread_name,
                'action': action,
                'event': 'MITIGATION_RESOLVED'
            })

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
            
            
            EPSILON = 1e-4  # seconds — below this, a wait time is effectively zero
            starvation_ratio = 0.0
            if avg_read_wait > EPSILON and avg_write_wait > EPSILON:
                starvation_ratio = max(avg_read_wait, avg_write_wait) / min(avg_read_wait, avg_write_wait)
            elif avg_write_wait > EPSILON or avg_read_wait > EPSILON:
                starvation_ratio = float('inf') 
                
            # Mitigation statistics
            starvation_events_count = len(self.starvation_alerts)
            mitigation_triggers = [e for e in self.mitigation_events
                                   if e['event'] == 'MITIGATION_TRIGGERED']
            mitigation_resolutions = [e for e in self.mitigation_events
                                      if e['event'] == 'MITIGATION_RESOLVED']
            mitigation_triggers_count = len(mitigation_triggers)

            # Compute average response time: time from trigger to resolution
            response_times = []
            for i, trig in enumerate(mitigation_triggers):
                if i < len(mitigation_resolutions):
                    dt = mitigation_resolutions[i]['timestamp'] - trig['timestamp']
                    response_times.append(dt)
            avg_mitigation_response = (sum(response_times) / len(response_times)
                                       if response_times else 0.0)

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
                'starvation_ratio': starvation_ratio,
                # Mitigation metrics
                'starvation_events_count': starvation_events_count,
                'mitigation_triggers_count': mitigation_triggers_count,
                'avg_mitigation_response': avg_mitigation_response,
                'starvation_alerts': list(self.starvation_alerts),
                'mitigation_events': list(self.mitigation_events)
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
            
            # Last 3 mitigation events for live feed
            recent_mitigation = (self.mitigation_events[-3:]
                                 if self.mitigation_events else [])

            return {
                'states': states_counts,
                'readers': reader_states,
                'writers': writer_states,
                'history_tail': self.history[-5:] if self.history else [],
                'mitigation_tail': recent_mitigation,
                'starvation_alerts_count': len(self.starvation_alerts),
                'mitigation_events_count': len(self.mitigation_events)
            }

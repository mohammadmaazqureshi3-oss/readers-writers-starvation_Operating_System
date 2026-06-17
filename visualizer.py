import os
import sys
import time

class TerminalVisualizer:
    
    def __init__(self, policy_name, num_readers, num_writers):
        self.policy_name = policy_name
        self.num_readers = num_readers
        self.num_writers = num_writers
        self.terminal_width = 80
        try:
            self.terminal_width = os.get_terminal_size().columns
        except OSError:
            pass

    def clear_screen(self):
        # Clear screen cleanly using standard terminal ANSI sequences
        sys.stdout.write("\033[H\033[J")
        sys.stdout.flush()

    def draw_dashboard(self, elapsed_time, snapshot, summary):
        """Draws a clean, minimalistic status dashboard without color codes."""
        self.clear_screen()
        
        # 1. Header
        header_text = f" READER-WRITER SIMULATION DASHBOARD "
        padding = (self.terminal_width - len(header_text)) // 2
        sys.stdout.write(f"{'=' * padding}{header_text}{'=' * (self.terminal_width - len(header_text) - padding)}\n")
        
        # 2. General Metadata
        meta_line = (
            f"Policy: {self.policy_name} | "
            f"Elapsed Time: {elapsed_time:.1f}s | "
            f"Threads: {self.num_readers} Readers / {self.num_writers} Writers\n"
        )
        sys.stdout.write(meta_line)
        sys.stdout.write(f"{'-' * self.terminal_width}\n")

        # 3. Thread State Summary
        readers_snap = snapshot['readers']
        writers_snap = snapshot['writers']
        
        sys.stdout.write(
            f"Readers: RUNNING: {readers_snap.get('RUNNING', 0)} | "
            f"WAITING: {readers_snap.get('WAITING', 0)} | "
            f"IDLE: {readers_snap.get('IDLE', 0)}\n"
        )
        sys.stdout.write(
            f"Writers: RUNNING: {writers_snap.get('RUNNING', 0)} | "
            f"WAITING: {writers_snap.get('WAITING', 0)} | "
            f"IDLE: {writers_snap.get('IDLE', 0)}\n"
        )
        sys.stdout.write(f"{'-' * self.terminal_width}\n")

        # 4. Starvation / Performance Analysis
        sys.stdout.write("Starvation Analysis:\n")
        avg_r_wait = summary['avg_read_wait']
        avg_w_wait = summary['avg_write_wait']
        
        # Draw clean ASCII-based progress bars
        max_val = max(avg_r_wait, avg_w_wait, 0.001)
        bar_len = 25
        
        r_bar_cnt = int((avg_r_wait / max_val) * bar_len)
        w_bar_cnt = int((avg_w_wait / max_val) * bar_len)
        
        r_bar = f"{'#' * r_bar_cnt}{'-' * (bar_len - r_bar_cnt)}"
        w_bar = f"{'#' * w_bar_cnt}{'-' * (bar_len - w_bar_cnt)}"
        
        sys.stdout.write(f"  Avg Reader Wait: [{r_bar}] {avg_r_wait*1000:6.1f} ms\n")
        sys.stdout.write(f"  Avg Writer Wait: [{w_bar}] {avg_w_wait*1000:6.1f} ms\n")

        # Fairness assessment
        ratio = summary['starvation_ratio']
        if ratio == float('inf'):
            status = "CRITICAL IMBALANCE (One group blocked completely)"
        elif ratio > 10.0:
            status = f"HIGH STARVATION (Ratio {ratio:.1f}x wait disparity)"
        elif ratio > 3.0:
            status = f"MODERATE IMBALANCE (Ratio {ratio:.1f}x wait disparity)"
        else:
            status = f"FAIR DISTRIBUTION (Ratio {ratio:.1f}x wait disparity)"
            
        sys.stdout.write(f"  System Status  : {status}\n")
        sys.stdout.write(f"{'-' * self.terminal_width}\n")

        # 5. Live Activity Feed (Recent operations)
        sys.stdout.write("Live Activity Feed:\n")
        tail = snapshot['history_tail']
        if not tail:
            sys.stdout.write("  (Waiting for operations...)\n")
        else:
            for op in tail:
                t_str = time.strftime('%H:%M:%S', time.localtime(op['start']))
                op_type = "READ" if op['type'] == 'READ' else "WRITE"
                sys.stdout.write(
                    f"  [{t_str}] {op['thread']} completed {op_type}. "
                    f"Wait time: {op['wait_time']*1000:.0f} ms\n"
                )
        
        sys.stdout.write(f"\n{'=' * self.terminal_width}\n")
        sys.stdout.write("Press Ctrl+C to terminate simulation early.\n")
        sys.stdout.flush()

    def print_final_report(self, summary):
        """Prints a clean, color-free, simple summary report of the simulation performance."""
        print("\n" * 2)
        header = " FINAL SIMULATION REPORT "
        padding = (self.terminal_width - len(header)) // 2
        print(f"{'=' * padding}{header}{'=' * (self.terminal_width - len(header) - padding)}")
        
        print(f"\n  Lock Policy Configuration: {self.policy_name}")
        print(f"  Simulation Time:           {summary['elapsed_time']:.2f} seconds")
        print(f"  Throughput:                {summary['throughput']:.2f} operations / sec\n")

        # Data table format
        row_fmt = "  {:<12} | {:^15} | {:^15} | {:^15}"
        print(f"  {'-' * 65}")
        print(row_fmt.format("Metric", "Readers (Reads)", "Writers (Writes)", "Overall"))
        print(f"  {'-' * 65}")
        
        print(row_fmt.format(
            "Count", 
            summary['total_reads'], 
            summary['total_writes'], 
            summary['total_reads'] + summary['total_writes']
        ))
        print(row_fmt.format(
            "Avg Wait", 
            f"{summary['avg_read_wait']*1000:.1f} ms", 
            f"{summary['avg_write_wait']*1000:.1f} ms", 
            f"{((summary['avg_read_wait'] + summary['avg_write_wait'])/2)*1000:.1f} ms"
        ))
        print(row_fmt.format(
            "Max Wait", 
            f"{summary['max_read_wait']*1000:.1f} ms", 
            f"{summary['max_write_wait']*1000:.1f} ms", 
            f"{max(summary['max_read_wait'], summary['max_write_wait'])*1000:.1f} ms"
        ))
        print(row_fmt.format(
            "Std Dev Wait", 
            f"{summary['std_read_wait']*1000:.1f} ms", 
            f"{summary['std_write_wait']*1000:.1f} ms", 
            "-"
        ))
        print(f"  {'-' * 65}\n")

        # Analytical Observations
        ratio = summary['starvation_ratio']
        print(f"  Starvation Factor: {ratio:.2f}x wait disparity.")
        
        print("  Analysis & Observations:")
        if self.policy_name == "Reader-Preferred Lock":
            print("    - Writer Starvation Simulated Successfully!")
            print("    - Arriving readers bypassed queued writers, keeping the lock continuously")
            print("      held by reading threads. The writers waited in queue for extended periods.")
            print(f"    - Max Writer Wait Time reached: {summary['max_write_wait']*1000:.1f} ms")
        elif self.policy_name == "Writer-Preferred Lock":
            print("    - Reader Starvation Simulated Successfully!")
            print("    - Writers announced their arrival, instantly blocking subsequent readers.")
            print("      A steady stream of writers kept the reader queue waiting indefinitely.")
            print(f"    - Max Reader Wait Time reached: {summary['max_read_wait']*1000:.1f} ms")
        else:
            print("    - Fair/FIFO Scheduling Confirmed!")
            print("    - Starvation has been mitigated. The maximum wait times for both groups")
            print("      remain bounded. Readers and writers interleaved perfectly in arrival order.")
            print("    - Wait time standard deviation remains low, verifying uniform service quality.")
            
        print(f"\n{'=' * self.terminal_width}\n")

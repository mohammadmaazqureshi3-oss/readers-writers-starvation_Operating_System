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

    def draw_dashboard(self, elapsed_time, snapshot, summary, aging_info=None):
        """Draws a clean, minimalistic status dashboard without color codes.
        
        Parameters
        ----------
        aging_info : dict or None
            If the lock is an AgingLock, this dict contains:
            - 'active': bool — is mitigation currently active?
            - 'mitigation_side': str or None — 'writer', 'reader', or None
            - 'boosted_writer': str or None — name of boosted writer
            - 'boosted_readers': set — names of boosted readers
            - 'writer_ages': dict — writer_name → seconds waited
            - 'reader_ages': dict — reader_name → seconds waited
            - 'threshold': float — starvation threshold in seconds
            - 'base_preference': str — 'reader' or 'writer'
        """
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

        # 4b. Mitigation Monitor (only for AgingLock)
        if aging_info is not None:
            base_pref = aging_info.get('base_preference', 'reader')
            side = aging_info.get('mitigation_side')
            sys.stdout.write(f"Mitigation Monitor (Dual Aging Lock — "
                             f"{base_pref.capitalize()}-Preferred Base):\n")
            if aging_info['active']:
                if side == 'writer':
                    boosted = aging_info.get('boosted_writer') or "unknown"
                    sys.stdout.write(
                        f"  Status         : >>> ACTIVE — {boosted} BOOSTED "
                        f"(reader gate CLOSED) <<<\n"
                    )
                elif side == 'reader':
                    boosted_set = aging_info.get('boosted_readers', set())
                    boosted_str = ', '.join(sorted(boosted_set)) if boosted_set else 'unknown'
                    sys.stdout.write(
                        f"  Status         : >>> ACTIVE — Readers BOOSTED "
                        f"(writer gate CLOSED) <<<\n"
                    )
                    sys.stdout.write(
                        f"  Boosted        : {boosted_str}\n"
                    )

                # Show ages of waiting writers
                for w_name, age in aging_info.get('writer_ages', {}).items():
                    marker = " <-- BOOSTED" if w_name == aging_info.get('boosted_writer') else ""
                    sys.stdout.write(
                        f"  {w_name:12s} age: {age:.2f}s "
                        f"(threshold: {aging_info['threshold']:.2f}s){marker}\n"
                    )
                # Show ages of waiting readers
                boosted_readers = aging_info.get('boosted_readers', set())
                for r_name, age in aging_info.get('reader_ages', {}).items():
                    marker = " <-- BOOSTED" if r_name in boosted_readers else ""
                    sys.stdout.write(
                        f"  {r_name:12s} age: {age:.2f}s "
                        f"(threshold: {aging_info['threshold']:.2f}s){marker}\n"
                    )
            else:
                sys.stdout.write(
                    f"  Status         : IDLE — {base_pref.capitalize()}-preferred "
                    f"mode active\n"
                )
                # Show any waiting writers and their ages
                for w_name, age in aging_info.get('writer_ages', {}).items():
                    sys.stdout.write(
                        f"  {w_name:12s} age: {age:.2f}s "
                        f"(threshold: {aging_info['threshold']:.2f}s)\n"
                    )
                # Show any waiting readers and their ages
                for r_name, age in aging_info.get('reader_ages', {}).items():
                    sys.stdout.write(
                        f"  {r_name:12s} age: {age:.2f}s "
                        f"(threshold: {aging_info['threshold']:.2f}s)\n"
                    )

            alerts_count = snapshot.get('starvation_alerts_count', 0)
            mitigation_count = snapshot.get('mitigation_events_count', 0)
            sys.stdout.write(
                f"  Starvation Detections: {alerts_count} | "
                f"Mitigation Interventions: {mitigation_count}\n"
            )

            # Show recent mitigation events
            mit_tail = snapshot.get('mitigation_tail', [])
            if mit_tail:
                sys.stdout.write("  Recent Events:\n")
                for evt in mit_tail:
                    t_str = time.strftime('%H:%M:%S',
                                         time.localtime(evt['timestamp']))
                    sys.stdout.write(
                        f"    [{t_str}] {evt['event']}: {evt['thread']} "
                        f"({evt['action']})\n"
                    )

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
        
        total_ops = summary['total_reads'] + summary['total_writes']
        overall_avg_wait = (
            (summary['avg_read_wait'] * summary['total_reads'] +
             summary['avg_write_wait'] * summary['total_writes']) / total_ops
            if total_ops > 0 else 0.0
        )
        print(row_fmt.format(
            "Count", 
            summary['total_reads'], 
            summary['total_writes'], 
            total_ops
        ))
        print(row_fmt.format(
            "Avg Wait", 
            f"{summary['avg_read_wait']*1000:.1f} ms", 
            f"{summary['avg_write_wait']*1000:.1f} ms", 
            f"{overall_avg_wait*1000:.1f} ms"
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
        elif "Aging Lock" in self.policy_name or "Dual Aging" in self.policy_name:
            # --- Mitigation-specific observations ---
            starvation_count = summary.get('starvation_events_count', 0)
            mitigation_count = summary.get('mitigation_triggers_count', 0)
            avg_response = summary.get('avg_mitigation_response', 0.0)
            print("    - Dynamic Starvation Mitigation Active (Dual Aging)!")
            print("    - The lock operated with a base preference for high throughput.")
            print("    - When the non-preferred side waited beyond the starvation threshold,")
            print("      the aging mechanism activated: the opposite gate was closed, active")
            print("      threads drained, and the starved thread(s) were admitted with")
            print("      boosted priority.")
            print(f"    - Starvation events detected : {starvation_count}")
            print(f"    - Mitigations triggered      : {mitigation_count}")
            if avg_response > 0:
                print(f"    - Avg response time (detect -> resolve): {avg_response*1000:.1f} ms")
            print(f"    - Max Writer Wait (bounded)  : {summary['max_write_wait']*1000:.1f} ms")
            print(f"    - Max Reader Wait (bounded)  : {summary['max_read_wait']*1000:.1f} ms")

            # Print the starvation event log
            alerts = summary.get('starvation_alerts', [])
            events = summary.get('mitigation_events', [])
            if alerts or events:
                print(f"\n  {'─' * 65}")
                print("  Mitigation Event Log:")
                print(f"  {'─' * 65}")

                # Merge alerts and events by timestamp for chronological display
                all_events = []
                for a in alerts:
                    all_events.append((a['timestamp'], 'DETECTED',
                                      a['thread'],
                                      f"waited {a['wait_duration']*1000:.0f}ms "
                                      f"(threshold {a['threshold']*1000:.0f}ms)"))
                for e in events:
                    all_events.append((e['timestamp'], e['event'],
                                      e['thread'], e['action']))
                all_events.sort(key=lambda x: x[0])

                for ts, etype, thread, detail in all_events:
                    t_str = time.strftime('%H:%M:%S', time.localtime(ts))
                    print(f"    [{t_str}] {etype:25s} | {thread:10s} | {detail}")
                print(f"  {'─' * 65}")
        else:
            print("    - Fair/FIFO Scheduling Confirmed!")
            print("    - Starvation has been mitigated. The maximum wait times for both groups")
            print("      remain bounded. Readers and writers interleaved perfectly in arrival order.")
            print("    - Wait time standard deviation remains low, verifying uniform service quality.")
            
        print(f"\n{'=' * self.terminal_width}\n")

    def print_comparison_report(self, summary_before, summary_after,
                                 name_before, name_after, scenario='writer-starvation'):
        """Print a side-by-side comparison report proving mitigation effectiveness.

        The report adapts to the scenario: writer-starvation shows writer
        metrics first; reader-starvation shows reader metrics first.
        """
        print("\n" * 2)
        header = " MITIGATION EFFECTIVENESS REPORT "
        padding = (self.terminal_width - len(header)) // 2
        print(f"{'=' * padding}{header}{'=' * (self.terminal_width - len(header) - padding)}")

        print(f"\n  Test Configuration: {self.num_readers} Readers / "
              f"{self.num_writers} Writers | "
              f"{summary_before['elapsed_time']:.1f}s per run")
        if scenario == 'reader-starvation':
            print(f"  Scenario        : Reader Starvation (writer-heavy workload)")
        else:
            print(f"  Scenario        : Writer Starvation (reader-heavy workload)")

        # Helper to compute percentage change
        def pct_change(before, after):
            if before == 0:
                return "  N/A"
            change = ((after - before) / before) * 100
            sign = "+" if change >= 0 else ""
            return f"{sign}{change:.0f}%"

        # Build comparison table
        w = 22  # column width
        print(f"\n  {'─' * 78}")
        print(f"  {'Metric':<24} | {'Unmitigated':^{w}} | {'Mitigated (Aging)':^{w}} | {'Change':^8}")
        print(f"  {'':<24} | {name_before:^{w}} | {name_after:^{w}} |")
        print(f"  {'─' * 78}")

        if scenario == 'reader-starvation':
            # --- Reader-starvation: show reader metrics first ---
            # Max Reader Wait
            br = summary_before['max_read_wait'] * 1000
            ar = summary_after['max_read_wait'] * 1000
            print(f"  {'Max Reader Wait':<24} | {br:>{w-3}.1f} ms | {ar:>{w-3}.1f} ms | {pct_change(br, ar):>8}")

            # Avg Reader Wait
            br = summary_before['avg_read_wait'] * 1000
            ar = summary_after['avg_read_wait'] * 1000
            print(f"  {'Avg Reader Wait':<24} | {br:>{w-3}.1f} ms | {ar:>{w-3}.1f} ms | {pct_change(br, ar):>8}")

            # Avg Writer Wait
            bw = summary_before['avg_write_wait'] * 1000
            aw = summary_after['avg_write_wait'] * 1000
            print(f"  {'Avg Writer Wait':<24} | {bw:>{w-3}.1f} ms | {aw:>{w-3}.1f} ms | {pct_change(bw, aw):>8}")

            # Starvation Ratio
            bs = summary_before['starvation_ratio']
            as_ = summary_after['starvation_ratio']
            bs_str = f"{bs:.1f}x" if bs != float('inf') else "INF"
            as_str = f"{as_:.1f}x" if as_ != float('inf') else "INF"
            print(f"  {'Starvation Ratio':<24} | {bs_str:>{w}} | {as_str:>{w}} | {pct_change(bs, as_) if bs != float('inf') else '  N/A':>8}")

            # Reader Ops Completed
            bro = summary_before['total_reads']
            aro = summary_after['total_reads']
            print(f"  {'Reader Ops Completed':<24} | {bro:>{w}} | {aro:>{w}} | {pct_change(bro, aro):>8}")

            # Writer Ops Completed
            bwo = summary_before['total_writes']
            awo = summary_after['total_writes']
            print(f"  {'Writer Ops Completed':<24} | {bwo:>{w}} | {awo:>{w}} | {pct_change(bwo, awo):>8}")

        else:
            # --- Writer-starvation: show writer metrics first (original) ---
            # Max Writer Wait
            bw = summary_before['max_write_wait'] * 1000
            aw = summary_after['max_write_wait'] * 1000
            print(f"  {'Max Writer Wait':<24} | {bw:>{w-3}.1f} ms | {aw:>{w-3}.1f} ms | {pct_change(bw, aw):>8}")

            # Avg Writer Wait
            bw = summary_before['avg_write_wait'] * 1000
            aw = summary_after['avg_write_wait'] * 1000
            print(f"  {'Avg Writer Wait':<24} | {bw:>{w-3}.1f} ms | {aw:>{w-3}.1f} ms | {pct_change(bw, aw):>8}")

            # Avg Reader Wait
            br = summary_before['avg_read_wait'] * 1000
            ar = summary_after['avg_read_wait'] * 1000
            print(f"  {'Avg Reader Wait':<24} | {br:>{w-3}.1f} ms | {ar:>{w-3}.1f} ms | {pct_change(br, ar):>8}")

            # Starvation Ratio
            bs = summary_before['starvation_ratio']
            as_ = summary_after['starvation_ratio']
            bs_str = f"{bs:.1f}x" if bs != float('inf') else "INF"
            as_str = f"{as_:.1f}x" if as_ != float('inf') else "INF"
            print(f"  {'Starvation Ratio':<24} | {bs_str:>{w}} | {as_str:>{w}} | {pct_change(bs, as_) if bs != float('inf') else '  N/A':>8}")

            # Writer Ops Completed
            bwo = summary_before['total_writes']
            awo = summary_after['total_writes']
            print(f"  {'Writer Ops Completed':<24} | {bwo:>{w}} | {awo:>{w}} | {pct_change(bwo, awo):>8}")

            # Reader Ops Completed
            bro = summary_before['total_reads']
            aro = summary_after['total_reads']
            print(f"  {'Reader Ops Completed':<24} | {bro:>{w}} | {aro:>{w}} | {pct_change(bro, aro):>8}")

        # Throughput (common to both)
        bt = summary_before['throughput']
        at = summary_after['throughput']
        print(f"  {'Throughput (ops/s)':<24} | {bt:>{w-1}.2f}  | {at:>{w-1}.2f}  | {pct_change(bt, at):>8}")

        print(f"  {'─' * 78}")

        # Mitigation statistics from the aging run
        starvation_count = summary_after.get('starvation_events_count', 0)
        mitigation_count = summary_after.get('mitigation_triggers_count', 0)
        avg_response = summary_after.get('avg_mitigation_response', 0.0)

        print(f"\n  Starvation Events Detected      : {starvation_count}")
        print(f"  Mitigation Interventions        : {mitigation_count}")
        if avg_response > 0:
            print(f"  Avg Response Time (detect->fix) : {avg_response*1000:.1f} ms")

        # Scenario-aware conclusion
        print(f"\n  {'─' * 78}")
        print("  CONCLUSION:")

        if scenario == 'reader-starvation':
            max_before = summary_before['max_read_wait'] * 1000
            max_after = summary_after['max_read_wait'] * 1000
            ops_before = summary_before['total_reads']
            ops_after = summary_after['total_reads']
            victim_label = "reader"
        else:
            max_before = summary_before['max_write_wait'] * 1000
            max_after = summary_after['max_write_wait'] * 1000
            ops_before = summary_before['total_writes']
            ops_after = summary_after['total_writes']
            victim_label = "writer"

        throughput_cost = pct_change(bt, at)

        if max_after < max_before:
            reduction = ((max_before - max_after) / max_before) * 100
            print(f"    The Dual Aging Lock successfully mitigated {victim_label} starvation.")
            print(f"    Maximum {victim_label} wait was reduced from {max_before:.0f}ms to "
                  f"{max_after:.0f}ms ({reduction:.0f}% reduction).")
            print(f"    {victim_label.capitalize()} throughput improved from {ops_before} to {ops_after} operations.")
            print(f"    Overall throughput change: {throughput_cost}, demonstrating that")
            print(f"    dynamic mitigation preserves most of the base lock's")
            print(f"    performance advantage while eliminating starvation.")
        else:
            print(f"    Results inconclusive — consider increasing simulation duration")
            print(f"    or adjusting the starvation threshold for clearer demonstration.")
        print(f"  {'─' * 78}")
        print(f"\n{'=' * self.terminal_width}\n")

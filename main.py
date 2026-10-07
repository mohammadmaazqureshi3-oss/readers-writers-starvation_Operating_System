import argparse
import time
import sys
import threading
from lock import ReaderPreferredLock, WriterPreferredLock, FairLock, FIFOLock, AgingLock
from simulation import SimulationManager
from visualizer import TerminalVisualizer

def get_preset_config(scenario):
    """Returns timing configurations tailored to show specific synchronization characteristics."""
    if scenario == 'writer-starvation':
        return {
            'reader_idle_min': 0.02,
            'reader_idle_max': 0.08,
            'reader_work_min': 0.08,
            'reader_work_max': 0.15,
            'writer_idle_min': 0.15,
            'writer_idle_max': 0.30,
            'writer_work_min': 0.10,
            'writer_work_max': 0.20
        }
    elif scenario == 'reader-starvation':
        return {
            'reader_idle_min': 0.15,
            'reader_idle_max': 0.30,
            'reader_work_min': 0.05,
            'reader_work_max': 0.10,
            'writer_idle_min': 0.02,
            'writer_idle_max': 0.08,
            'writer_work_min': 0.15,
            'writer_work_max': 0.25
        }
    else: # Balanced
        return {
            'reader_idle_min': 0.10,
            'reader_idle_max': 0.20,
            'reader_work_min': 0.05,
            'reader_work_max': 0.12,
            'writer_idle_min': 0.10,
            'writer_idle_max': 0.20,
            'writer_work_min': 0.10,
            'writer_work_max': 0.20
        }


def create_lock(policy, metrics_collector=None, scenario='writer-starvation',
                starvation_threshold=0.8):
    """Factory function to create the appropriate lock and its display name.
    
    The AgingLock requires a MetricsCollector reference so it can log
    detection / trigger / resolution events in real time.
    """
    if policy == 'reader-pref':
        return ReaderPreferredLock(), "Reader-Preferred Lock"
    elif policy == 'writer-pref':
        return WriterPreferredLock(), "Writer-Preferred Lock"
    elif policy == 'fair':
        return FairLock(), "Fair Lock (Service Queue)"
    elif policy == 'fifo':
        return FIFOLock(), "Strict FIFO Lock (Custom Monitor)"
    elif policy == 'aging':
        base_pref = 'writer' if scenario == 'reader-starvation' else 'reader'
        lock = AgingLock(starvation_threshold=starvation_threshold,
                         metrics_collector=metrics_collector,
                         base_preference=base_pref)
        return lock, f"Aging Lock (Dynamic Mitigation, {base_pref.capitalize()}-Pref Base)"
    else:
        print(f"Unknown locking policy: {policy}")
        sys.exit(1)


def resolve_thread_counts(scenario, policy, readers, writers):
    """Automatically adjust thread counts for specific starvation scenario presets."""
    readers_count = readers
    writers_count = writers
    if scenario == 'writer-starvation' and policy in ('reader-pref', 'aging'):
        # Ensure heavy reader load to guarantee writer starvation
        readers_count = max(8, readers_count)
        writers_count = min(2, writers_count)
    elif scenario == 'reader-starvation' and policy in ('writer-pref', 'aging'):
        # Ensure heavy writer load to guarantee reader starvation
        readers_count = min(2, readers_count)
        writers_count = max(4, writers_count)
    return readers_count, writers_count


def run_single_simulation(policy, readers_count, writers_count, duration,
                          scenario, show_dashboard=True, threshold=0.8):
    """Run one simulation run and return the final summary dict.
    
    If show_dashboard is True, the live terminal dashboard is rendered
    during the run.  Returns the metrics summary dictionary.
    """
    config = get_preset_config(scenario)

    # Create a SimulationManager with a dummy lock first so we can grab
    # its MetricsCollector, then create the real lock.
    # (AgingLock needs the MetricsCollector at construction time.)
    dummy_lock = ReaderPreferredLock()
    manager = SimulationManager(
        lock=dummy_lock,
        num_readers=readers_count,
        num_writers=writers_count,
        config=config
    )

    # Now create the real lock, passing the metrics collector for aging
    lock, policy_name = create_lock(policy, manager.metrics,
                                    scenario=scenario,
                                    starvation_threshold=threshold)
    manager.lock = lock  # swap in the real lock before starting threads

    if show_dashboard:
        visualizer = TerminalVisualizer(
            policy_name=policy_name,
            num_readers=readers_count,
            num_writers=writers_count
        )

    print(f"\nInitializing {policy_name} simulation...")
    time.sleep(0.5)

    manager.start()

    start_time = time.time()
    try:
        while True:
            elapsed = time.time() - start_time
            if elapsed >= duration:
                break

            if show_dashboard:
                snapshot = manager.metrics.get_snapshot()
                summary = manager.metrics.get_summary()

                # Pass lock reference for aging introspection
                aging_info = None
                if isinstance(lock, AgingLock):
                    aging_info = {
                        'active': lock.is_mitigation_active(),
                        'mitigation_side': lock.get_mitigation_side(),
                        'boosted_writer': lock.get_boosted_writer(),
                        'boosted_readers': lock.get_boosted_readers(),
                        'writer_ages': lock.get_waiting_writer_ages(),
                        'reader_ages': lock.get_waiting_reader_ages(),
                        'threshold': lock.get_threshold(),
                        'base_preference': lock.get_base_preference()
                    }
                visualizer.draw_dashboard(elapsed, snapshot, summary,
                                          aging_info=aging_info)

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\nSimulation interrupted by user. Stopping gracefully...")
    finally:
        manager.stop()

    # Final snapshot
    final_summary = manager.metrics.get_summary()

    if show_dashboard:
        final_elapsed = time.time() - start_time
        snapshot = manager.metrics.get_snapshot()
        aging_info = None
        if isinstance(lock, AgingLock):
            aging_info = {
                'active': lock.is_mitigation_active(),
                'mitigation_side': lock.get_mitigation_side(),
                'boosted_writer': lock.get_boosted_writer(),
                'boosted_readers': lock.get_boosted_readers(),
                'writer_ages': lock.get_waiting_writer_ages(),
                'reader_ages': lock.get_waiting_reader_ages(),
                'threshold': lock.get_threshold(),
                'base_preference': lock.get_base_preference()
            }
        visualizer.draw_dashboard(final_elapsed, snapshot, final_summary,
                                  aging_info=aging_info)
        time.sleep(0.5)
        visualizer.print_final_report(final_summary)

    return final_summary, policy_name


def run_comparison(readers_count, writers_count, duration, scenario, threshold=0.8):
    """Run unmitigated vs Aging (mitigated) back-to-back
    and print a side-by-side comparison proving mitigation effectiveness."""
    if scenario == 'reader-starvation':
        unmitigated_policy = 'writer-pref'
        unmitigated_name = "Writer-Preferred Lock"
    else:
        unmitigated_policy = 'reader-pref'
        unmitigated_name = "Reader-Preferred Lock"

    print("\n" + "=" * 80)
    print("  MITIGATION COMPARISON MODE")
    print(f"  Phase 1: Running UNMITIGATED simulation ({unmitigated_name})")
    print("=" * 80)
    summary_before, name_before = run_single_simulation(
        unmitigated_policy, readers_count, writers_count, duration, scenario,
        show_dashboard=True, threshold=threshold
    )

    print("\n\nPreparing Phase 2...")
    time.sleep(2.0)

    print("\n" + "=" * 80)
    print("  MITIGATION COMPARISON MODE")
    print("  Phase 2: Running MITIGATED simulation (Dual Aging Lock)")
    print("=" * 80)
    summary_after, name_after = run_single_simulation(
        'aging', readers_count, writers_count, duration, scenario,
        show_dashboard=True, threshold=threshold
    )

    # Print the comparison report
    visualizer = TerminalVisualizer(
        policy_name="Comparison",
        num_readers=readers_count,
        num_writers=writers_count
    )
    visualizer.print_comparison_report(summary_before, summary_after,
                                        name_before, name_after,
                                        scenario=scenario)


def main():
    parser = argparse.ArgumentParser(
        description="Simulate and Mitigate Starvation in the Readers-Writers Problem.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Scenarios:
  writer-starvation  High Reader frequency, low Writer frequency. Demonstrates starvation of Writers under Reader-Preferred lock.
  reader-starvation  High Writer frequency, low Reader frequency. Demonstrates starvation of Readers under Writer-Preferred lock.
  balanced           Evenly balanced threads. Good for demonstrating the efficiency and latency of Fair locks.

Policies:
  reader-pref   Reader-Preferred Lock (writers may starve)
  writer-pref   Writer-Preferred Lock (readers may starve)
  fair          Fair Lock with service queue
  fifo          Strict FIFO ordering
  aging         Aging Lock with dynamic starvation mitigation

Comparison Mode:
  --compare     Automatically run Reader-Preferred then Aging back-to-back
                and print a before/after mitigation effectiveness report.
"""
    )
    
    parser.add_argument(
        '--policy', 
        choices=['reader-pref', 'writer-pref', 'fair', 'fifo', 'aging'], 
        default='reader-pref',
        help="Locking policy to simulate (default: reader-pref)"
    )
    parser.add_argument(
        '--readers', 
        type=int, 
        default=6,
        help="Number of Reader threads"
    )
    parser.add_argument(
        '--writers', 
        type=int, 
        default=2,
        help="Number of Writer threads"
    )
    parser.add_argument(
        '--duration', 
        type=float, 
        default=5.0,
        help="Simulation run duration in seconds"
    )
    parser.add_argument(
        '--scenario', 
        choices=['writer-starvation', 'reader-starvation', 'balanced'], 
        default='writer-starvation',
        help="Workload timing preset to apply (default: writer-starvation)"
    )
    parser.add_argument(
        '--threshold', 
        type=float, 
        default=0.8,
        help="Aging starvation threshold in seconds (default: 0.8)"
    )
    parser.add_argument(
        '--compare',
        action='store_true',
        help="Run Unmitigated vs. Aging back-to-back and print comparison report"
    )

    args = parser.parse_args()

    # Interactive mode: if the script is run without any command‑line arguments,
    # present a simple menu to choose defaults or a custom configuration.
    if len(sys.argv) == 1:
        print("\n--- Readers‑Writers Simulation & Dynamic Mitigation ---")
        print("Options:")
        print("  (d)  Default single run        (Reader-Preferred, writer-starvation)")
        print("  (a)  Aging mitigation single   (Aging Lock, writer-starvation)")
        print("  (m)  Mitigation comparison     (Writer starvation: Reader-Pref vs Aging)")
        print("  (mr) Mitigation comparison     (Reader starvation: Writer-Pref vs Aging)")
        print("  (c)  Custom configuration")
        choice = input("\nSelect mode [d/a/m/mr/c]: ").strip().lower()

        threshold = 0.8
        if choice == 'c':
            policy = input("Lock policy (reader-pref, writer-pref, fair, fifo, aging): ").strip()
            readers = int(input("Number of Reader threads: ").strip())
            writers = int(input("Number of Writer threads: ").strip())
            duration = float(input("Simulation duration (seconds): ").strip())
            scenario = input("Scenario (writer-starvation, reader-starvation, balanced): ").strip()
            if policy == 'aging':
                t_input = input("Starvation threshold in seconds [0.8]: ").strip()
                if t_input:
                    threshold = float(t_input)
            compare = False
        elif choice == 'a':
            policy = 'aging'
            readers = 6
            writers = 2
            duration = 8.0
            scenario = 'writer-starvation'
            compare = False
        elif choice == 'mr':
            policy = 'writer-pref'
            readers = 2
            writers = 4
            duration = 8.0
            scenario = 'reader-starvation'
            compare = True
        elif choice in ('m', 'mw'):
            policy = 'reader-pref'  # will be compared against aging
            readers = 6
            writers = 2
            duration = 8.0
            scenario = 'writer-starvation'
            compare = True
        else:
            # defaults match the argparse defaults
            policy = 'reader-pref'
            readers = 6
            writers = 2
            duration = 8.0
            scenario = 'writer-starvation'
            compare = False

        # Build a lightweight namespace‑like object to mimic argparse.Namespace
        class SimpleArgs:
            pass
        args = SimpleArgs()
        args.policy = policy
        args.readers = readers
        args.writers = writers
        args.duration = duration
        args.scenario = scenario
        args.compare = compare
        args.threshold = threshold

    # Resolve thread counts for the scenario
    readers_count, writers_count = resolve_thread_counts(
        args.scenario, args.policy, args.readers, args.writers
    )

    # ---- COMPARISON MODE ----
    if args.compare:
        run_comparison(readers_count, writers_count, args.duration, args.scenario,
                       threshold=args.threshold)
        return

    # ---- SINGLE RUN MODE ----
    run_single_simulation(
        args.policy, readers_count, writers_count, args.duration, args.scenario,
        show_dashboard=True, threshold=args.threshold
    )

if __name__ == '__main__':
    main()

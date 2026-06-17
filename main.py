import argparse
import time
import sys
import threading
from lock import ReaderPreferredLock, WriterPreferredLock, FairLock, FIFOLock
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

def main():
    parser = argparse.ArgumentParser(
        description="Simulate and Mitigate Starvation in the Readers-Writers Problem.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Scenarios:
  writer-starvation  High Reader frequency, low Writer frequency. Demonstrates starvation of Writers under Reader-Preferred lock.
  reader-starvation  High Writer frequency, low Reader frequency. Demonstrates starvation of Readers under Writer-Preferred lock.
  balanced           Evenly balanced threads. Good for demonstrating the efficiency and latency of Fair locks.
"""
    )
    
    parser.add_argument(
        '--policy', 
        choices=['reader-pref', 'writer-pref', 'fair', 'fifo'], 
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

    args = parser.parse_args()

    # Interactive mode: if the script is run without any command‑line arguments,
    # present a simple menu to choose defaults or a custom configuration.
    if len(sys.argv) == 1:
        print("\n--- Readers‑Writers Simulation ---")
        choice = input("Run with (d)efault configuration or (c)ustom? [d/c]: ").strip().lower()
        if choice == 'c':
            policy = input("Lock policy (reader-pref, writer-pref, fair, fifo): ").strip()
            readers = int(input("Number of Reader threads: ").strip())
            writers = int(input("Number of Writer threads: ").strip())
            duration = float(input("Simulation duration (seconds): ").strip())
            scenario = input("Scenario (writer-starvation, reader-starvation, balanced): ").strip()
        else:
            # defaults match the argparse defaults
            policy = 'reader-pref'
            readers = 6
            writers = 2
            duration = 8.0
            scenario = 'writer-starvation'
        # Build a lightweight namespace‑like object to mimic argparse.Namespace
        class SimpleArgs:
            pass
        args = SimpleArgs()
        args.policy = policy
        args.readers = readers
        args.writers = writers
        args.duration = duration
        args.scenario = scenario

    # Configure Locks
    if args.policy == 'reader-pref':
        lock = ReaderPreferredLock()
        policy_name = "Reader-Preferred Lock"
    elif args.policy == 'writer-pref':
        lock = WriterPreferredLock()
        policy_name = "Writer-Preferred Lock"
    elif args.policy == 'fair':
        lock = FairLock()
        policy_name = "Fair Lock (Service Queue)"
    elif args.policy == 'fifo':
        lock = FIFOLock()
        policy_name = "Strict FIFO Lock (Custom Monitor)"
    else:
        print(f"Unknown locking policy: {args.policy}")
        sys.exit(1)

    # Automatically set optimal thread counts for specific starvation scenario presets
    readers_count = args.readers
    writers_count = args.writers
    if args.scenario == 'writer-starvation' and args.policy == 'reader-pref':
        # Ensure heavy reader load to guarantee writer starvation
        readers_count = max(8, readers_count)
        writers_count = min(2, writers_count)
    elif args.scenario == 'reader-starvation' and args.policy == 'writer-pref':
        # Ensure heavy writer load to guarantee reader starvation
        readers_count = min(2, readers_count)
        writers_count = max(4, writers_count)

    config = get_preset_config(args.scenario)
    
    # Initialize components
    manager = SimulationManager(
        lock=lock,
        num_readers=readers_count,
        num_writers=writers_count,
        config=config
    )
    
    visualizer = TerminalVisualizer(
        policy_name=policy_name,
        num_readers=readers_count,
        num_writers=writers_count
    )

    print("Initializing threads and preparing dashboard...")
    time.sleep(1.0)
    
    manager.start()
    
    start_time = time.time()
    try:
        while True:
            elapsed = time.time() - start_time
            if elapsed >= args.duration:
                break
                
            # Get real-time snapshots
            snapshot = manager.metrics.get_snapshot()
            summary = manager.metrics.get_summary()
            
            visualizer.draw_dashboard(elapsed, snapshot, summary)
            
            # High refresh rate for smooth real-time animation
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n\nSimulation interrupted by user. Stopping gracefully...")
    finally:
        manager.stop()
        
    # Draw one last final dashboard state
    final_elapsed = time.time() - start_time
    snapshot = manager.metrics.get_snapshot()
    summary = manager.metrics.get_summary()
    visualizer.draw_dashboard(final_elapsed, snapshot, summary)
    time.sleep(0.5)

    # Print comprehensive analytics report
    visualizer.print_report_header = lambda: None # Override or direct call
    visualizer.print_final_report(summary)

if __name__ == '__main__':
    main()

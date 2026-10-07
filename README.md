# Simulating and Dynamically Mitigating Starvation in the Readers-Writers Problem

### *Design, Implementation, and Empirical Evaluation of Symmetric Dual Aging Locks with Real-Time Telemetry*

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![Concurrency](https://img.shields.io/badge/concurrency-multi--threading-orange.svg)]()
[![Mitigation](https://img.shields.io/badge/starvation-dynamically_mitigated-brightgreen.svg)]()
[![Telemetry](https://img.shields.io/badge/telemetry-real--time_ANSI-informational.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 📖 Table of Contents

- [Overview](#-overview)
- [The Core Dilemma: Starvation vs. Throughput](#-the-core-dilemma-starvation-vs-throughput)
- [The Solution: Symmetric Dual Aging Lock](#-the-solution-symmetric-dual-aging-lock)
- [System Architecture & Code Structure](#-system-architecture--code-structure)
- [Real-Time Terminal Telemetry Dashboard](#-real-time-terminal-telemetry-dashboard)
- [Quick Start & Demo Guide](#-quick-start--demo-guide)
- [Empirical Results (Numerical & Graphical)](#-empirical-results-numerical--graphical)
  - [1. Writer Starvation Mitigation](#1-writer-starvation-mitigation-reader-preferred-vs-dual-aging)
  - [2. Reader Starvation Mitigation](#2-reader-starvation-mitigation-writer-preferred-vs-dual-aging)
  - [3. Comprehensive 5-Policy Comparison Matrix](#3-comprehensive-5-policy-comparison-matrix)
- [Formal Project Deliverables](#-formal-project-deliverables)
- [Author](#-author)

---

## 📌 Overview

In concurrent computing, the classical **Readers-Writers Problem** models concurrent access to a shared resource between two classes of threads:
- **Readers:** Only read shared data without modifying it; arbitrarily many readers can safely execute concurrently.
- **Writers:** Modify shared state; require strict mutual exclusion with respect to both readers and all other writers.

While basic mutual exclusion is straightforward, **starvation freedom** represents a fundamental challenge in operating systems design.

---

## ⚖️ The Core Dilemma: Starvation vs. Throughput

Traditional locking policies force an undesirable compromise:

1. **Static Preference Locks (*Reader-Preferred* / *Writer-Preferred*):**
   - Maximize concurrency throughput by continuously admitting the preferred thread class.
   - **Fatal Flaw:** Induce **catastrophic, unbounded starvation** for the non-preferred class under heavy traffic. Writers can be blocked indefinitely under continuous reads, or vice versa.
2. **Static Fair Solutions (*Service-Queue Fair* / *Strict FIFO Monitors*):**
   - Guarantee arrival-order fairness and bounded latency.
   - **Fatal Flaw:** Impose an ongoing **"fairness tax"** (a permanent **76–77% throughput penalty**), serializing reads and destroying concurrency even during quiescent periods when no thread is starved.

```
+--------------------------------------------------------------------------------+
|                               CONCURRENCY SPECTRUM                             |
|                                                                                |
|  [Reader-Preferred Lock]                     [Fair / Strict FIFO Locks]        |
|  • Peak throughput (39+ ops/s)               • Bounded latency                 |
|  • UNBOUNDED STARVATION (469x disparity)     • 76% THROUGHPUT TAX (9 ops/s)    |
|                                                                                |
|                              ★ OUR SOLUTION ★                                  |
|                         [Symmetric Dual Aging Lock]                            |
|             • High concurrency base mode (32.7 ops/s, 83% retained)            |
|             • Zero starvation (latencies strictly bounded to ~1.0s)            |
+--------------------------------------------------------------------------------+
```

---

## 💡 The Solution: Symmetric Dual Aging Lock

The **Dual Aging Lock (`AgingLock`)** breaks this compromise by adapting the operating system concept of **dynamic priority aging** directly to synchronization primitives:

1. **Normal Preference Mode:** Operates in high-throughput preference mode by default. Admission gates remain open, permitting full parallel concurrency.
2. **Dynamic Detection:** A non-blocking telemetry engine monitors queued thread latencies. If any thread waits longer than the starvation threshold ($\tau = 0.8\text{s}$), a `STARVATION_DETECTED` event is triggered.
3. **Admission Gate Closure:** The lock immediately closes the counterpart admission gate (`READER_GATE_CLOSED` or `WRITER_GATE_CLOSED`), blocking newly arriving threads of the favored group.
4. **Controlled Drainage & Priority Boost:** Active threads drain naturally. Once the resource clears, the starved thread is granted boosted priority (single writer boost, or parallel batch boost for all waiting readers).
5. **Self-Healing Recovery:** Upon completion, the lock reopens the gate (`GATE_REOPENED`), records `MITIGATION_RESOLVED`, and restores high-concurrency operation.

![4-Phase Mitigation Lifecycle](figures/mitigation_lifecycle_diagram.png)

---

## 🏗️ System Architecture & Code Structure

The project is structured into five modular, decoupled Python components:

```
operation_system_project/
├── lock.py                   # 5 locking policies (including Dual Aging Lock)
├── simulation.py             # Multi-threaded simulation engine & shared resource
├── metrics.py                # Telemetry collector & starvation event logger
├── visualizer.py             # Real-time ANSI dashboard & comparative reporter
├── main.py                   # CLI orchestrator & benchmark runner
├── generate_report_charts.py # Script generating publication-quality figures
├── build_master_report_docx.py # Script compiling formal Project_Report.docx
├── figures/                  # High-resolution 300-DPI evaluation figures
├── Project_Report.docx       # Master academic project report (Word)
├── PROJECT_REPORT.md         # Comprehensive markdown project report
└── README.md                 # Project documentation & GitHub guide
```

### Module Breakdown

| Module | Core Classes | Architectural Responsibility |
| :--- | :--- | :--- |
| [`lock.py`](lock.py) | `AgingLock`, `ReaderPreferredLock`, `WriterPreferredLock`, `FairLock`, `FIFOLock` | Synchronization primitives implementing `acquire_read`, `release_read`, `acquire_write`, and `release_write`. Features condition variable predicate loops with 50ms polling. |
| [`simulation.py`](simulation.py) | `SharedResource`, `ReaderThread`, `WriterThread`, `SimulationManager` | Multi-threaded workload engine managing thread lifecycles, randomized idle/work duty cycles, and clean thread shutdown via `stop_event`. |
| [`metrics.py`](metrics.py) | `MetricsCollector` | Thread-safe telemetry collector utilizing `threading.RLock()`. Tracks state transitions, millisecond latencies, and logs immutable starvation detection/resolution events. |
| [`visualizer.py`](visualizer.py) | `TerminalVisualizer` | 10 Hz ANSI terminal dashboard, ASCII wait disparity progress bars, active gate monitor, and scenario-aware comparative report generator. |
| [`main.py`](main.py) | CLI entry point | Workload scenario presets, policy selection, threshold tuning (`--threshold`), and automated back-to-back mitigation benchmarking (`--compare`). |

---

## 🖥️ Real-Time Terminal Telemetry Dashboard

During simulation runs, the `TerminalVisualizer` renders an interactive ANSI terminal dashboard updated at 10 Hz:

```
====================== READER-WRITER SIMULATION DASHBOARD ======================
Policy: Aging Lock (Dynamic Mitigation, Reader-Pref Base) | Elapsed Time: 4.2s | Threads: 8 Readers / 2 Writers
--------------------------------------------------------------------------------
Readers: RUNNING: 3 | WAITING: 2 | IDLE: 3
Writers: RUNNING: 1 | WAITING: 0 | IDLE: 1
--------------------------------------------------------------------------------
Starvation Analysis:
  Avg Reader Wait: [##-----------------------]   42.1 ms
  Avg Writer Wait: [####################-----]  480.5 ms
  System Status  : HIGH STARVATION (Ratio 11.4x wait disparity)
--------------------------------------------------------------------------------
Mitigation Monitor (Dual Aging Lock — Reader-Preferred Base):
  Status         : >>> ACTIVE — Writer-1 BOOSTED (reader gate CLOSED) <<<
  Writer-1     age: 0.86s (threshold: 0.80s) <-- BOOSTED
  Starvation Detections: 4 | Mitigation Interventions: 4
  Recent Events:
    [16:54:12] STARVATION_DETECTED: Writer-1 (waited 862ms)
    [16:54:12] MITIGATION_TRIGGERED: Writer-1 (READER_GATE_CLOSED)
    [16:54:13] MITIGATION_RESOLVED: Writer-1 (READER_GATE_REOPENED)
--------------------------------------------------------------------------------
Live Activity Feed:
  [16:54:13] Writer-1 completed WRITE. Wait time: 862 ms
  [16:54:13] Reader-3 completed READ. Wait time: 38 ms
================================================================================
Press Ctrl+C to terminate simulation early.
```

---

## 🚀 Quick Start & Demo Guide

### Requirements
- Python 3.8 or higher
- Optional dependencies for chart and Word report generation:
  ```bash
  pip install matplotlib python-docx
  ```

### 1. Automated Mitigation Comparison (Recommended for Demos)
Runs the unmitigated lock first to demonstrate starvation, followed immediately by the Dual Aging Lock under the exact same workload, outputting a side-by-side verification table:

```bash
# Compare Writer Starvation (Reader-Preferred vs Dual Aging Lock)
python3 main.py --compare --scenario writer-starvation --duration 8

# Compare Reader Starvation (Writer-Preferred vs Dual Aging Lock)
python3 main.py --compare --scenario reader-starvation --duration 8
```

### 2. Live Dashboard Simulation
Run a single simulation with the interactive terminal dashboard:

```bash
# Observe Dual Aging Lock actively mitigating writer starvation
python3 main.py --policy aging --scenario writer-starvation --threshold 0.8 --duration 10
```

### 3. Interactive Walkthrough Menu
Launch the guided CLI menu:

```bash
python3 main.py
```

### 4. Regenerate High-Resolution Figures & Word Report
```bash
# Regenerate all PNG figures in figures/
python3 generate_report_charts.py

# Recompile the master academic Word report
python3 build_master_report_docx.py
```

---

## 📊 Empirical Results (Numerical & Graphical)

All benchmarks were evaluated over 8.0-second intervals under identical CPU configurations.

### 1. Writer Starvation Mitigation: Reader-Preferred vs Dual Aging
*Workload: 8 Readers, 2 Writers, heavy read frequency.*

| Metric | Reader-Preferred (Unmitigated) | Dual Aging Lock (Mitigated) | Improvement | Status |
| :--- | :---: | :---: | :---: | :--- |
| **Max Writer Wait** | 5,795.2 ms | **1,061.4 ms** | **-81.7%** | **Bounded to ~1.0s** |
| **Avg Writer Wait** | 2,850.0 ms | **520.0 ms** | **-81.8%** | **Equitable** |
| **Completed Writes** | 4 ops | **14 ops** | **+250% (3.5x)** | **Active progress** |
| **System Throughput** | 39.3 ops/s | **32.7 ops/s** | -16.8% | **83.2% peak retained** |
| **Starvation Ratio** | 469.1x (Lockout) | **15.4x** | **-96.7%** | **Eliminated** |
| **Mitigation Events** | 0 | **10 detections / fixes** | N/A | **Self-healing** |

![Writer Starvation Mitigation](figures/writer_starvation_mitigation.png)

---

### 2. Reader Starvation Mitigation: Writer-Preferred vs Dual Aging
*Workload: 2 Readers, 4 Writers, heavy writer frequency.*

| Metric | Writer-Preferred (Unmitigated) | Dual Aging Lock (Mitigated) | Improvement | Status |
| :--- | :---: | :---: | :---: | :--- |
| **Max Reader Wait** | 8,335.3 ms | **1,234.3 ms** | **-85.2%** | **Bounded to ~1.2s** |
| **Avg Reader Wait** | 5,400.0 ms | **410.0 ms** | **-92.4%** | **Equitable** |
| **Completed Reads** | 3 ops | **13 ops** | **+333% (4.3x)** | **4.3x progress** |
| **System Throughput** | 4.8 ops/s | **5.6 ops/s** | **+16.7%** | **Parallel batch drain** |
| **Starvation Ratio** | 10.6x (Lockout) | **1.6x** | **-84.9%** | **Near-ideal 1.0 parity** |
| **Mitigation Events** | 0 | **15 detections / fixes** | N/A | **Batch boost active** |

![Reader Starvation Mitigation](figures/reader_starvation_mitigation.png)

---

### 3. Comprehensive 5-Policy Comparison Matrix

| Locking Policy | System Throughput | Starvation Ratio | Max Wait Time | Concurrency Profile | Fairness Tax |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **Reader-Preferred** | **39.3 ops/s** | 469.1x (Severe) | 5,795 ms | Unlimited concurrent reads | 0% (No tax) |
| **Writer-Preferred** | 4.8 ops/s | 10.6x (Severe) | 8,335 ms | Serialized writes | High static tax |
| **Fair Lock (Turnstile)** | 9.1 ops/s | **1.08x (Fair)** | 620 ms | Alternating queue | 77% throughput tax |
| **Strict FIFO Monitor** | 9.4 ops/s | **1.08x (Fair)** | 593 ms | Strict queue order | 76% throughput tax |
| **Dual Aging Lock (Ours)** | **32.7 ops/s** | **15.4x (Bounded)** | **1,061 ms** | **Adaptive peak concurrency** | **17% dynamic tax** |

![Policy Comparison Matrix](figures/policy_comparison_matrix.png)

---

## 📄 Formal Project Deliverables

- **Master Word Report:** [`Project_Report.docx`](Project_Report.docx) — Formal academic report complete with executive summary, mathematical formulas, code breakdown, 6 data tables, and 4 embedded high-resolution figures.
- **Master Markdown Report:** [`PROJECT_REPORT.md`](PROJECT_REPORT.md) — GitHub-formatted comprehensive analytical report.
- **Evaluation Figures:** High-resolution 300-DPI charts in the [`figures/`](figures/) directory.

---

## 👨‍💻 Author

**Mohammad Maaz Quershi**  
Operating Systems & Concurrent Computing  
October 2026

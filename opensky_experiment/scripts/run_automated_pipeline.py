#!/usr/bin/env python3
"""
OpenSky Automated Hourly Pipeline (Build Folder Centric)
========================================================
Designed to be executed directly from the `build/` directory:
  cd build/
  python3 ../opensky_experiment/scripts/run_automated_pipeline.py [OPTIONS]

Reference points from build/:
  - Raw Data Archives       : ../opensky_experiment/data/<date>/
  - Cleaned & .bin Datasets : ../opensky_experiment/data/<date>_hourly/
  - Benchmark Executable    : ./experiment_opensky_hourly
  - Final Results           : ../opensky_experiment/results/
"""

import sys
import os
import time
import glob
import argparse
import subprocess
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from fetch_dates import get_available_dates, get_hourly_keys_for_date, find_qualified_dates
from downloader import download_hourly_dataset
from preprocess_hourly_opensky import preprocess_hourly

def resolve_paths():
    project_root = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
    
    # Check if executable exists in current working directory
    if os.path.isfile("./experiment_opensky_hourly") and os.access("./experiment_opensky_hourly", os.X_OK):
        binary_cmd = os.path.abspath("./experiment_opensky_hourly")
    elif os.path.isfile(os.path.join(project_root, "build", "experiment_opensky_hourly")):
        binary_cmd = os.path.join(project_root, "build", "experiment_opensky_hourly")
    else:
        binary_cmd = os.path.join(project_root, "build", "experiment_opensky_hourly")

    base_data = os.path.join(project_root, "opensky_experiment", "data")
    base_results = os.path.join(project_root, "opensky_experiment", "results")

    return base_data, base_results, binary_cmd


def ensure_compiled_binary(binary_cmd):
    if os.path.isfile(binary_cmd) and os.access(binary_cmd, os.X_OK):
        return True
    
    project_root = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
    print(f"[Build] Target binary '{binary_cmd}' not found. Compiling via cmake in {project_root}/build...")
    try:
        build_dir = os.path.join(project_root, "build")
        subprocess.run(["cmake", "--build", build_dir, "--target", "experiment_opensky_hourly", "-j4"], check=True)
        return True
    except Exception as e:
        print(f"[Build Error] Failed to compile: {e}")
        return False


def process_date(date_str, s3_prefix, hourly_keys, args, base_data, base_results, binary_cmd, day_idx=1, total_days=1, custom_csv=None):
    print("\n" + "#" * 80)
    print(f"  PROCESSING DAY [{day_idx}/{total_days}]: {date_str} ({len(hourly_keys)} hours)")
    print("#" * 80)

    raw_date_dir = os.path.join(base_data, date_str)
    hourly_out_dir = os.path.join(base_data, f"{date_str}_hourly")
    os.makedirs(raw_date_dir, exist_ok=True)
    os.makedirs(hourly_out_dir, exist_ok=True)

    # 1. Download
    if not args.skip_download:
        print(f"\n[Step 1/3] Downloading archives for {date_str} into {raw_date_dir}...")
        if hourly_keys:
            download_hourly_dataset(hourly_keys, raw_date_dir, max_workers=args.workers or 6)
        else:
            print(f"[Downloader] Using existing local files in {raw_date_dir}")
    else:
        print(f"\n[Step 1/3] Skipping download (--skip-download active).")

    # 2. Preprocessing
    if not args.skip_preprocess:
        print(f"\n[Step 2/3] Preprocessing hourly files into {hourly_out_dir}...")
        preprocess_hourly(raw_date_dir, hourly_out_dir, workers=args.workers)
    else:
        print(f"\n[Step 2/3] Skipping preprocessing (--skip-preprocess active).")

    # Optional clean raw
    if args.clean_raw and os.path.isdir(raw_date_dir):
        print(f"[Cleanup] Removing raw .csv.gz archives in {raw_date_dir} to save disk space...")
        shutil.rmtree(raw_date_dir, ignore_errors=True)

    # 3. Benchmark Execution
    target_csv = custom_csv if custom_csv else os.path.join(base_results, f"opensky_hourly_{date_str}_{time.strftime('%Y%m%d_%H%M%S')}.csv")

    # Check if this date has already finished all tests in target_csv
    if os.path.isfile(target_csv):
        try:
            with open(target_csv, 'r') as f_chk:
                content = f_chk.read()
            record_count = content.count(f"states_{date_str}-")
            max_tests = (args.max_hours if args.max_hours else len(hourly_keys)) * 4
            if max_tests > 0 and record_count >= max_tests:
                print(f"\n[Resume Checkpoint] Date {date_str} is already 100% completed ({record_count}/{max_tests} test cases in CSV).")
                print(f"  Skipping download, preprocessing, and benchmark for {date_str}!\n")
                return True
        except Exception:
            pass

    print(f"\n[Step 3/3] Executing C++ Hourly Benchmark ({binary_cmd})...")
    print(f"[Real-Time CSV] Every test case (4 per hour) is written & flushed live to:\n  --> {target_csv}\n")
    cmd = [
        binary_cmd,
        hourly_out_dir,
        str(args.iterations),
        str(args.min_sep),
        target_csv
    ]
    print(f"[Benchmark Command] {' '.join(cmd)}\n")
    proc = subprocess.run(cmd)
    return proc.returncode == 0

def main():
    default_data, default_results, default_binary = resolve_paths()

    parser = argparse.ArgumentParser(description="OpenSky Automated Hourly Pipeline (Build Folder Centric)")
    parser.add_argument("--date", type=str, default=None,
                        help="Specific date to process (YYYY-MM-DD). If omitted, uses existing or latest date.")
    parser.add_argument("--all-dates", action="store_true",
                        help="Run batch pipeline across ALL available dates with 24 hours.")
    parser.add_argument("--min-hours", type=int, default=24,
                        help="Minimum number of hours required (default: 24).")
    parser.add_argument("--max-hours", type=int, default=24,
                        help="Maximum hours per date to run (default: 24).")
    parser.add_argument("--limit-dates", type=int, default=25,
                        help="Max dates to benchmark when --all-dates is active (default: 25).")
    parser.add_argument("--iterations", type=int, default=10,
                        help="Iterations per test scenario (default: 10).")
    parser.add_argument("--min-sep", type=float, default=0.05,
                        help="Minimum separation in meters to eliminate duplicate sensor artifacts (default: 0.05).")
    parser.add_argument("--workers", type=int, default=None,
                        help="Number of CPU worker processes.")
    parser.add_argument("--clean-raw", action="store_true",
                        help="Delete raw compressed .csv.gz archives after preprocessing.")
    parser.add_argument("--list-dates", action="store_true",
                        help="List available OpenSky dates and exit.")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip downloading.")
    parser.add_argument("--skip-preprocess", action="store_true",
                        help="Skip preprocessing.")
    parser.add_argument("--resume", nargs="?", const="AUTO", default=None,
                        help="Resume pipeline from existing CSV (auto-detects most recent CSV if no path given).")

    args = parser.parse_args()

    os.makedirs(default_data, exist_ok=True)
    os.makedirs(default_results, exist_ok=True)

    print("=" * 80)
    print("      OPENSKY AUTOMATED PIPELINE (BUILD-FOLDER REFERENCE POINT)        ")
    print("=" * 80)
    print(f"Working Directory   : {os.getcwd()}")
    print(f"Data Base Dir       : {default_data}")
    print(f"Results Base Dir    : {default_results}")
    print(f"Binary Path         : {default_binary}")
    print(f"Iterations / test   : {args.iterations}")
    print(f"Min Separation (m)  : {args.min_sep} m (strictly non-zero)")
    print("=" * 80)

    if args.list_dates:
        print("\n[Mode] Listing available OpenSky dates...")
        qualified = find_qualified_dates(min_hours=args.min_hours, limit=args.limit_dates)
        for item in qualified:
            print(f"  - Date: {item['date']} | Hours: {item['hours']}/24")
        return

    if not ensure_compiled_binary(default_binary):
        sys.exit(1)

    t_start = time.time()

    if args.all_dates:
        print(f"\n[Batch Mode] Querying OpenSky S3 API for all dates with >= {args.min_hours} hours...")
        qualified_dates = find_qualified_dates(min_hours=args.min_hours, limit=args.limit_dates)
        if not qualified_dates:
            print(f"[Error] No dates found with >= {args.min_hours} hours.")
            sys.exit(1)

        master_csv = None
        if args.resume:
            if args.resume != "AUTO" and os.path.isfile(args.resume):
                master_csv = os.path.abspath(args.resume)
            else:
                candidates = glob.glob(os.path.join(default_results, "opensky_*.csv"))
                if candidates:
                    candidates.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                    master_csv = candidates[0]
                    print(f"\n[Resume Checkpoint] Auto-detected most recent master CSV to resume:\n  --> {master_csv}")

        if not master_csv:
            master_csv = os.path.join(default_results, f"opensky_all_dates_results_{time.strftime('%Y%m%d_%H%M%S')}.csv")
            print(f"\n[Real-Time Continuous CSV] All dates will continuously log & flush every test case to:")
            print(f"  --> {master_csv}\n")
        else:
            print(f"\n[Resume Continuous CSV] Resuming pipeline and appending test cases to:")
            print(f"  --> {master_csv}\n")

        for idx, date_info in enumerate(qualified_dates, 1):
            date_str = date_info["date"]
            s3_prefix = date_info["prefix"]
            hourly_keys = date_info["keys"]
            if args.max_hours and len(hourly_keys) > args.max_hours:
                hourly_keys = hourly_keys[:args.max_hours]

            process_date(date_str, s3_prefix, hourly_keys, args, default_data, default_results, default_binary,
                         day_idx=idx, total_days=len(qualified_dates), custom_csv=master_csv)

        total_elapsed = time.time() - t_start
        print("\n" + "=" * 80)
        print(f" BATCH BENCHMARK COMPLETE!")
        print(f" Elapsed Time : {total_elapsed/3600:.2f} hours ({total_elapsed:.1f} s)")
        print(f" Master CSV   : {master_csv}")
        print("=" * 80)
        return

    # Single date
    selected_date = args.date
    s3_prefix = None
    hourly_keys = []

    if selected_date is None:
        if os.path.isdir(os.path.join(default_data, "2019-05-27")):
            selected_date = "2019-05-27"
            print(f"\n[Auto-Select] Found existing local data for: {selected_date}")

    if selected_date:
        print(f"\n[Step 1/3] Validating date {selected_date}...")
        all_dates = get_available_dates()
        match = next((d for d in all_dates if d["date"] == selected_date), None)
        if match:
            s3_prefix = match["prefix"]
            hourly_keys = get_hourly_keys_for_date(s3_prefix)
    else:
        print(f"\n[Step 1/3] Auto-fetching latest available date from OpenSky...")
        qualified = find_qualified_dates(min_hours=args.min_hours, limit=1)
        if not qualified:
            print("[Error] No qualified dates found!")
            sys.exit(1)
        selected_date = qualified[0]["date"]
        s3_prefix = qualified[0]["prefix"]
        hourly_keys = qualified[0]["keys"]

    if args.max_hours and len(hourly_keys) > args.max_hours:
        hourly_keys = hourly_keys[:args.max_hours]

    day_csv = None
    if args.resume:
        if args.resume != "AUTO" and os.path.isfile(args.resume):
            day_csv = os.path.abspath(args.resume)
        else:
            candidates = glob.glob(os.path.join(default_results, f"opensky_*{selected_date}*.csv")) + \
                         glob.glob(os.path.join(default_results, "opensky_all_dates_results_*.csv"))
            if candidates:
                candidates.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                day_csv = candidates[0]
                print(f"\n[Resume Checkpoint] Auto-detected CSV to resume:\n  --> {day_csv}")

    if not day_csv:
        day_csv = os.path.join(default_results, f"opensky_hourly_{selected_date}_{time.strftime('%Y%m%d_%H%M%S')}.csv")
    ok = process_date(selected_date, s3_prefix, hourly_keys, args, default_data, default_results, default_binary, custom_csv=day_csv)
    if ok:
        print("\n" + "=" * 80)
        print(f" PIPELINE COMPLETED FOR {selected_date}!")
        print(f" Intermediate Outputs : {os.path.join(default_data, f'{selected_date}_hourly')}")
        print(f" Result CSV           : {day_csv}")
        print("=" * 80)

if __name__ == '__main__':
    main()

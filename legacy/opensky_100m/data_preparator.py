#!/usr/bin/env python3
"""
OpenSky 100-Million 4D Dataset Preparator Pipeline (Official S3 Sourced)
========================================================================
Automates downloading from OpenSky's official S3 repository, unpacking,
transforming, and streaming 3 full days (72 hours) into a single 4D binary file.

S3 Repository Endpoint:
https://s3.opensky-network.org/data-samples/states/.<date>/<hour>/states_<date>-<hour>.csv.tar
"""

import os
import sys
import io
import json
import glob
import time
import struct
import tarfile
import urllib.request
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd

EARTH_RADIUS_M = 6371000.0
S3_DEFAULT_BASE = "https://s3.opensky-network.org/data-samples"

def load_config(config_path="config.json"):
    candidates = [
        config_path,
        os.path.join(os.path.dirname(__file__), config_path),
        os.path.join(os.getcwd(), config_path),
        os.path.join(os.getcwd(), "..", config_path)
    ]
    for c in candidates:
        if os.path.isfile(c):
            print(f"[Config] Loaded configuration: {os.path.abspath(c)}")
            with open(c, 'r') as f:
                return json.load(f), os.path.dirname(os.path.abspath(c))

    print(f"[Warning] Config file '{config_path}' not found, using default configuration.")
    return {
        "dates": ["2019-05-20", "2019-05-27", "2019-06-03"],
        "min_hours_per_day": 24,
        "alpha_velocity_m_s": 250.0,
        "min_separation_m": 0.05,
        "contiguous_3days": True,
        "time_reference_mode": "day1_midnight_utc",
        "data_dir": "data",
        "results_dir": "results",
        "output_bin": "data/opensky_3days_100M_4d.bin",
        "s3_base_url": S3_DEFAULT_BASE
    }, os.getcwd()

def download_single_hour(date_str, hour, dest_file, s3_base, max_retries=3):
    """
    Downloads one hourly archive from OpenSky S3 and extracts the .csv.gz file.
    URL: {s3_base}/states/.{date_str}/{hour:02d}/states_{date_str}-{hour:02d}.csv.tar
    """
    if os.path.isfile(dest_file) and os.path.getsize(dest_file) > 1024 * 1024:
        return {"hour": hour, "status": "cached", "path": dest_file}

    tar_url = f"{s3_base.rstrip('/')}/states/.{date_str}/{hour:02d}/states_{date_str}-{hour:02d}.csv.tar"
    tmp_file = dest_file + ".tmp"

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(tar_url, headers={'User-Agent': 'Mozilla/5.0'})
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=120) as resp:
                content = resp.read()

            # Extract the .csv.gz member from the tar archive
            extracted_ok = False
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as tar:
                for member in tar.getmembers():
                    if member.name.endswith(".csv.gz") or member.name.endswith(".csv"):
                        extracted = tar.extractfile(member)
                        if extracted:
                            with open(tmp_file, "wb") as f_out:
                                f_out.write(extracted.read())
                            extracted_ok = True
                            break

            if not extracted_ok:
                with open(tmp_file, "wb") as f_out:
                    f_out.write(content)

            if os.path.isfile(tmp_file) and os.path.getsize(tmp_file) > 1024 * 1024:
                os.replace(tmp_file, dest_file)
                elapsed = time.time() - t0
                size_mb = os.path.getsize(dest_file) / (1024 * 1024)
                return {"hour": hour, "status": "downloaded", "path": dest_file, "size_mb": size_mb, "elapsed": elapsed}

        except Exception as e:
            if os.path.isfile(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass
            if attempt < max_retries:
                time.sleep(2 * attempt)
            else:
                return {"hour": hour, "status": "error", "error": str(e)}

    return {"hour": hour, "status": "error", "error": "max retries exceeded"}


def acquire_date_data(date_str, data_root, s3_base, max_workers=4):
    """
    Ensures that all 24 hourly .csv.gz files are available for the given date.
    Reuses existing local files, extracts from local tars, or downloads from S3.
    """
    date_dir = os.path.join(data_root, date_str)
    os.makedirs(date_dir, exist_ok=True)

    # Check existing files
    files = sorted(glob.glob(os.path.join(date_dir, f"states_{date_str}-*.csv.gz")))
    if len(files) >= 24:
        print(f"[{date_str}] All 24 hourly .csv.gz files already present in {date_dir}")
        return files

    # Check parent directory opensky_experiment/data/
    parent_check = os.path.abspath(os.path.join(data_root, "..", "..", "opensky_experiment", "data", date_str))
    if os.path.isdir(parent_check):
        parent_files = sorted(glob.glob(os.path.join(parent_check, f"states_{date_str}-*.csv.gz")))
        if len(parent_files) >= 24:
            print(f"[{date_str}] Found all 24 files in parent repository: {parent_check}")
            return parent_files

    print(f"[{date_str}] Downloading missing hourly data from OpenSky S3 ({s3_base})...")
    tasks = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for hour in range(24):
            dest_file = os.path.join(date_dir, f"states_{date_str}-{hour:02d}.csv.gz")
            tasks.append(executor.submit(download_single_hour, date_str, hour, dest_file, s3_base))

        for future in as_completed(tasks):
            res = future.result()
            h = res.get("hour", 0)
            if res.get("status") == "downloaded":
                print(f"  [{date_str}] Hour {h:02d}: Downloaded ({res['size_mb']:.1f} MB in {res.get('elapsed', 0):.1f}s)")
            elif res.get("status") == "cached":
                pass
            else:
                print(f"  [{date_str}] Hour {h:02d}: Failed ({res.get('error', 'unknown')})")

    files = sorted(glob.glob(os.path.join(date_dir, f"states_{date_str}-*.csv.gz")))
    return files

def get_day_midnight_utc(date_str):
    dt = datetime.datetime.strptime(f"{date_str} 00:00:00", "%Y-%m-%d %H:%M:%S")
    dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.timestamp()

def stream_dates_to_binary(date_file_map, output_bin_path, alpha, contiguous=True):
    """
    Streams all 3 days into ONE unified 4D binary file (OPS2 format).
    Contiguous mode stitches the 3 dates into a continuous 72-hour window:
      t_rel = day_index * 86400.0 + (t - t_midnight)
      w = alpha * t_rel
    Ensures Delta_t in [0, 259200] so w <= 6.48e7 m (full single-precision float accuracy).
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_bin_path)), exist_ok=True)
    print(f"\n[Binary Streamer] Initializing binary dataset: {output_bin_path}")

    first_date = list(date_file_map.keys())[0]
    t_ref_global = get_day_midnight_utc(first_date)

    # Write header: Magic(4s) + Dim(uint32) + Count(uint64) + Alpha(float) + t_ref(double)
    with open(output_bin_path, 'wb') as f_out:
        f_out.write(b"OPS2")
        f_out.write(struct.pack("<I", 4))          # Dim = 4
        f_out.write(struct.pack("<Q", 0))          # Placeholder for point count
        f_out.write(struct.pack("<f", float(alpha)))
        f_out.write(struct.pack("<d", float(t_ref_global)))

    total_points = 0
    total_hours = sum(len(flist) for flist in date_file_map.values())
    hour_counter = 0

    point_dtype = np.dtype([
        ('x', '<f4'),
        ('y', '<f4'),
        ('z', '<f4'),
        ('w', '<f4'),
        ('flight_id', '<u4')
    ])

    for day_idx, (d_str, file_list) in enumerate(date_file_map.items()):
        day_midnight = get_day_midnight_utc(d_str)
        day_offset_sec = day_idx * 86400.0 if contiguous else (day_midnight - t_ref_global)

        print(f"\n>>> Processing Day {day_idx + 1}/3: [{d_str}] ({len(file_list)} hourly files)")
        print(f"    Timeline Offset: +{day_offset_sec / 3600.0:.1f} hours from reference")

        for f_path in file_list:
            hour_counter += 1
            base_name = os.path.basename(f_path)
            try:
                use_cols = ['time', 'icao24', 'lat', 'lon', 'geoaltitude']
                try:
                    df = pd.read_csv(f_path, usecols=use_cols, compression='gzip')
                except Exception:
                    use_cols = ['time', 'icao24', 'lat', 'lon', 'baroaltitude']
                    df = pd.read_csv(f_path, usecols=use_cols, compression='gzip')
                    df.rename(columns={'baroaltitude': 'geoaltitude'}, inplace=True)

                df.dropna(subset=['time', 'icao24', 'lat', 'lon'], inplace=True)
                df['geoaltitude'] = df['geoaltitude'].fillna(0.0)

                df = df[(df['lat'] >= -90.0) & (df['lat'] <= 90.0) &
                        (df['lon'] >= -180.0) & (df['lon'] <= 180.0) &
                        (df['geoaltitude'] >= -1000.0) & (df['geoaltitude'] <= 30000.0)]

                if df.empty:
                    continue

                def hex_to_id(val):
                    try:
                        return int(str(val).strip(), 16) & 0xFFFFFFFF
                    except Exception:
                        return 0

                flight_ids = df['icao24'].apply(hex_to_id).to_numpy(dtype=np.uint32)

                # Vectorized 3D ECEF Cartesian Coordinates
                lat_rad = np.radians(df['lat'].to_numpy(dtype=np.float64))
                lon_rad = np.radians(df['lon'].to_numpy(dtype=np.float64))
                r = EARTH_RADIUS_M + df['geoaltitude'].to_numpy(dtype=np.float64)

                x = (r * np.cos(lat_rad) * np.cos(lon_rad)).astype(np.float32)
                y = (r * np.cos(lat_rad) * np.sin(lon_rad)).astype(np.float32)
                z = (r * np.sin(lat_rad)).astype(np.float32)

                # 4th Temporal Dimension: continuous 72-hour window
                raw_times = df['time'].to_numpy(dtype=np.float64)
                if contiguous:
                    rel_time_sec = day_offset_sec + (raw_times - day_midnight)
                else:
                    rel_time_sec = raw_times - t_ref_global

                w = (rel_time_sec * alpha).astype(np.float32)

                n_pts = len(x)
                packed = np.empty(n_pts, dtype=point_dtype)
                packed['x'] = x
                packed['y'] = y
                packed['z'] = z
                packed['w'] = w
                packed['flight_id'] = flight_ids

                with open(output_bin_path, 'ab') as f_out:
                    f_out.write(packed.tobytes())

                total_points += n_pts
                print(f"  [{hour_counter:02d}/{total_hours}] {base_name}: +{n_pts:,} pts (Total: {total_points:,})")

            except Exception as e:
                print(f"  [Error] Failed to process {base_name}: {e}")

    # Update final count in header
    with open(output_bin_path, 'r+b') as f_out:
        f_out.seek(8)
        f_out.write(struct.pack("<Q", total_points))

    file_size_gb = os.path.getsize(output_bin_path) / (1024 * 1024 * 1024)
    print("\n===============================================================")
    print("                100M DATASET CREATION COMPLETE                 ")
    print("===============================================================")
    print(f"  Output Binary:     {output_bin_path}")
    print(f"  Total 4D Points:   {total_points:,}")
    print(f"  File Size on Disk: {file_size_gb:.2f} GB")
    print(f"  Time Reference:    {t_ref_global:.1f} UTC ({first_date} 00:00:00 UTC)")
    print(f"  Alpha Velocity:    {alpha:.1f} m/s")
    print("===============================================================\n")
    return total_points

def main():
    print("===============================================================")
    print("     OpenSky 3-Day 100M Telemetry Preparator (S3 Pipeline)     ")
    print("===============================================================")

    config_arg = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    cfg, project_root = load_config(config_arg)

    dates = cfg.get("dates", ["2019-05-20", "2019-05-27", "2019-06-03"])
    alpha = float(cfg.get("alpha_velocity_m_s", 250.0))
    s3_base = cfg.get("s3_base_url", S3_DEFAULT_BASE)
    contiguous = cfg.get("contiguous_3days", True)

    data_dir = os.path.join(project_root, cfg.get("data_dir", "data"))
    output_bin = os.path.join(project_root, cfg.get("output_bin", "data/opensky_3days_100M_4d.bin"))

    print(f"[Setup] S3 Endpoint:      {s3_base}")
    print(f"[Setup] Target Dates:     {dates}")
    print(f"[Setup] Alpha Scale:      {alpha} m/s")
    print(f"[Setup] Contiguous 3-Day: {'Enabled (72-hour window)' if contiguous else 'Calendar Absolute'}")
    print(f"[Setup] Output Binary:    {output_bin}")

    date_files = {}
    for d in dates:
        files = acquire_date_data(d, data_dir, s3_base)
        print(f"[{d}] Retrieved {len(files)} hourly files.")
        if files:
            date_files[d] = files

    if not date_files:
        print("[Error] No files found or downloaded. Exiting.")
        sys.exit(1)

    stream_dates_to_binary(date_files, output_bin, alpha, contiguous)

if __name__ == '__main__':
    main()

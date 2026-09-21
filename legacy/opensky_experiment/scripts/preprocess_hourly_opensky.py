#!/usr/bin/env python3
"""
Hourly OpenSky Multi-core Preprocessor
- Converts all 24 raw hourly .csv.gz files from a given day directory into:
    1) 24 Cleaned CSV files (ECEF coordinates + time coordinate + raw metadata)
    2) 24 Binary cache files (.bin) in OPS2 format for instant C++ zero-overhead loading
- Uses multi-core ProcessPoolExecutor for high-throughput parallel processing.
"""

import sys
import os
import glob
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import pandas as pd

WGS84_A = 6378137.0
WGS84_E2 = 0.00669437999014

def geodetic_to_ecef(lat_deg, lon_deg, alt_m):
    lat_rad = np.radians(lat_deg)
    lon_rad = np.radians(lon_deg)
    sin_lat = np.sin(lat_rad)
    cos_lat = np.cos(lat_rad)
    sin_lon = np.sin(lon_rad)
    cos_lon = np.cos(lon_rad)

    N = WGS84_A / np.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    x = (N + alt_m) * cos_lat * cos_lon
    y = (N + alt_m) * cos_lat * sin_lon
    z = (N * (1.0 - WGS84_E2) + alt_m) * sin_lat
    return x, y, z

def parse_icao_to_uint32(val):
    try:
        return int(str(val).strip(), 16) & 0xFFFFFFFF
    except Exception:
        return hash(str(val)) & 0xFFFFFFFF

def process_single_hour(fpath, output_dir, global_alpha):
    fname = os.path.basename(fpath)
    hour_tag = fname.replace(".csv.gz", "").replace(".csv", "").replace(".tar", "")
    out_csv = os.path.join(output_dir, f"{hour_tag}_cleaned_4d.csv")
    out_bin = os.path.join(output_dir, f"{hour_tag}_4d.bin")

    t0 = time.time()
    df = pd.read_csv(fpath)
    col_time = next((c for c in ['time', 'timestamp'] if c in df.columns), None)
    col_lat = next((c for c in ['lat', 'latitude'] if c in df.columns), None)
    col_lon = next((c for c in ['lon', 'longitude'] if c in df.columns), None)
    col_alt = next((c for c in ['geoaltitude', 'baroaltitude', 'altitude'] if c in df.columns), None)
    col_id = next((c for c in ['icao24', 'flight_id'] if c in df.columns), None)

    if not all([col_time, col_lat, col_lon, col_alt, col_id]):
        return {"hour": hour_tag, "status": "skipped", "reason": "missing columns", "points": 0}

    df = df.dropna(subset=[col_time, col_lat, col_lon, col_alt, col_id]).copy()
    df = df[(df[col_lat] >= -90.0) & (df[col_lat] <= 90.0) &
            (df[col_lon] >= -180.0) & (df[col_lon] <= 180.0) &
            (df[col_alt] >= -100.0) & (df[col_alt] <= 25000.0)]

    chunk_len = len(df)
    if chunk_len == 0:
        return {"hour": hour_tag, "status": "skipped", "reason": "empty after filter", "points": 0}

    hour_t_min = float(df[col_time].min())
    x, y, z = geodetic_to_ecef(df[col_lat].values, df[col_lon].values, df[col_alt].values)
    t_norm = (df[col_time].values - hour_t_min).astype(np.float32)
    w_time = t_norm * global_alpha

    flight_uints = np.array([parse_icao_to_uint32(x_id) for x_id in df[col_id].values], dtype=np.uint32)

    # 1. Save Cleaned Hourly CSV
    processed_csv = pd.DataFrame({
        'flight_id': flight_uints,
        'icao24': df[col_id].values,
        'x_m': x.astype(np.float32),
        'y_m': y.astype(np.float32),
        'z_m': z.astype(np.float32),
        'w_time_m': w_time.astype(np.float32),
        'raw_time': df[col_time].values,
        'lat': df[col_lat].values,
        'lon': df[col_lon].values,
        'alt_m': df[col_alt].values
    })
    processed_csv.to_csv(out_csv, index=False)

    # 2. Save Hourly Binary (.bin) in OPS2 format
    rec_dtype = np.dtype([
        ('id', np.uint32),
        ('coords', np.float32, (4,))
    ])
    with open(out_bin, 'wb') as f_bin:
        magic = b'OPS2'
        dim = np.uint32(4)
        count = np.uint64(chunk_len)
        alpha_val = np.float32(global_alpha)
        t_min_val = np.float64(hour_t_min)

        f_bin.write(magic)
        f_bin.write(dim.tobytes())
        f_bin.write(count.tobytes())
        f_bin.write(alpha_val.tobytes())
        f_bin.write(t_min_val.tobytes())

        bin_data = np.empty(chunk_len, dtype=rec_dtype)
        bin_data['id'] = flight_uints
        bin_data['coords'][:, 0] = x.astype(np.float32)
        bin_data['coords'][:, 1] = y.astype(np.float32)
        bin_data['coords'][:, 2] = z.astype(np.float32)
        bin_data['coords'][:, 3] = w_time.astype(np.float32)
        f_bin.write(bin_data.tobytes())

    elapsed = time.time() - t0
    return {
        "hour": hour_tag,
        "status": "success",
        "points": chunk_len,
        "t_min": hour_t_min,
        "alpha": global_alpha,
        "csv": out_csv,
        "bin": out_bin,
        "elapsed_sec": round(elapsed, 2)
    }

def preprocess_hourly(input_dir, output_dir=None, workers=None):
    print(f"[HourlyPreprocess] Source directory : {input_dir}")
    files = sorted(glob.glob(os.path.join(input_dir, "states_*.csv.gz")))
    if not files:
        files = sorted(glob.glob(os.path.join(input_dir, "states_*.csv")))
    if not files:
        print(f"[Error] No states_*.csv.gz or .csv files found in {input_dir}!")
        sys.exit(1)

    base_name = os.path.basename(os.path.normpath(input_dir))
    if output_dir is None:
        data_parent = "../opensky_experiment/data" if os.path.isdir("../opensky_experiment/data") else "opensky_experiment/data"
        output_dir = os.path.join(data_parent, f"{base_name}_hourly")

    os.makedirs(output_dir, exist_ok=True)
    print(f"[HourlyPreprocess] Destination directory: {output_dir}")
    print(f"[HourlyPreprocess] Found {len(files)} files to convert.")

    # Check for existing metadata to get global alpha
    global_alpha = 186.44778
    meta_candidates = [
        os.path.join("../opensky_experiment/data", f"opensky_{base_name}_full_day_4d_metadata.json"),
        os.path.join("../opensky_experiment/data", "opensky_2019-05-27_full_day_4d_metadata.json"),
        os.path.join("opensky_experiment", "data", f"opensky_{base_name}_full_day_4d_metadata.json"),
        os.path.join("opensky_experiment", "data", "opensky_2019-05-27_full_day_4d_metadata.json")
    ]
    for meta_path in meta_candidates:
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, 'r') as f_meta:
                    meta_info = json.load(f_meta)
                    if "velocity_alpha_mps" in meta_info:
                        global_alpha = float(meta_info["velocity_alpha_mps"])
                        print(f"[HourlyPreprocess] Loaded global velocity alpha: {global_alpha:.4f} m/s from {meta_path}")
                        break
            except Exception:
                pass

    if workers is None:
        workers = min(os.cpu_count() or 4, len(files))

    print(f"[HourlyPreprocess] Launching {workers} parallel worker processes...")
    start_all = time.time()
    results = []

    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(process_single_hour, fpath, output_dir, global_alpha): fpath
            for fpath in files
        }

        completed_count = 0
        for fut in as_completed(future_map):
            completed_count += 1
            res = fut.result()
            results.append(res)
            print(f"  [{completed_count:2d}/{len(files):2d}] {res['hour']} -> {res.get('points', 0):,} points ({res.get('elapsed_sec', 0.0)}s)")

    results.sort(key=lambda r: r['hour'])
    total_points = sum(r.get('points', 0) for r in results if r['status'] == 'success')
    total_sec = time.time() - start_all

    # Save metadata index
    index_json_path = os.path.join(output_dir, "hourly_index.json")
    with open(index_json_path, 'w') as f_idx:
        json.dump({
            "source_directory": os.path.abspath(input_dir),
            "output_directory": os.path.abspath(output_dir),
            "total_hourly_files": len(results),
            "total_4d_points": total_points,
            "velocity_alpha_mps": global_alpha,
            "preprocessing_time_seconds": round(total_sec, 2),
            "hours": results
        }, f_idx, indent=2)

    print(f"\n[Done] Processed {len(results)} files ({total_points:,} points) in {total_sec:.1f}s.")
    print(f"  Output folder: {output_dir}")
    print(f"  Index JSON   : {index_json_path}")

if __name__ == '__main__':
    default_base = "../opensky_experiment/data" if os.path.isdir("../opensky_experiment/data") else "opensky_experiment/data"
    default_in = os.path.join(default_base, "2019-05-27")
    default_out = os.path.join(default_base, "2019-05-27_hourly")

    in_dir = sys.argv[1] if len(sys.argv) > 1 else default_in
    out_dir = sys.argv[2] if len(sys.argv) > 2 else default_out
    n_workers = int(sys.argv[3]) if len(sys.argv) > 3 else None
    preprocess_hourly(in_dir, out_dir, n_workers)

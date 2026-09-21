#!/usr/bin/env python3
"""
Batch OpenSky 24-Hour Day Preprocessor
- Streams each hourly .csv.gz directly into the final .bin file
- Zero temporary file overhead, completely safe on disk
- Writes OPS2 header and all points reliably
"""

import sys
import os
import glob
import json
import struct
import numpy as np
import pandas as pd

# WGS-84 ellipsoid constants
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

def batch_preprocess_day(input_dir, output_bin_path):
    print(f"[BatchPreprocess] Scanning directory: {input_dir}")
    
    files = sorted(glob.glob(os.path.join(input_dir, "states_*.csv.gz")))
    if not files:
        files = sorted(glob.glob(os.path.join(input_dir, "states_*.csv")))
    
    if not files:
        print(f"[Error] No states_*.csv.gz or .csv files found in {input_dir}!")
        sys.exit(1)

    print(f"[BatchPreprocess] Found {len(files)} hourly state files to process.")

    # Phase 1: Pass 1 to find global t_min, global t_max, and alpha
    print("\n[Pass 1/2] Computing global temporal origin (t_min) and average velocity...")
    global_t_min = float('inf')
    global_t_max = float('-inf')
    vel_sum = 0.0
    vel_count = 0
    id_map = {}
    next_id = 1

    for idx, fpath in enumerate(files):
        print(f"  Scanning file [{idx+1}/{len(files)}]: {os.path.basename(fpath)}...", end='\r')
        try:
            df_quick = pd.read_csv(fpath, usecols=lambda c: c in ['time', 'velocity', 'icao24'])
            if 'time' in df_quick.columns:
                t_min = df_quick['time'].min()
                t_max = df_quick['time'].max()
                if pd.notna(t_min) and t_min < global_t_min:
                    global_t_min = float(t_min)
                if pd.notna(t_max) and t_max > global_t_max:
                    global_t_max = float(t_max)

            if 'velocity' in df_quick.columns:
                valid_vel = df_quick['velocity'].dropna()
                valid_vel = valid_vel[(valid_vel > 10.0) & (valid_vel < 400.0)]
                vel_sum += float(valid_vel.sum())
                vel_count += len(valid_vel)

            if 'icao24' in df_quick.columns:
                for plane in df_quick['icao24'].dropna().unique():
                    if plane not in id_map:
                        id_map[plane] = next_id
                        next_id += 1
        except Exception as e:
            print(f"\n[Warning] Could not scan {fpath}: {e}")

    alpha = (vel_sum / vel_count) if vel_count > 0 else 186.45
    print(f"\n[Pass 1 Complete]")
    print(f"  Global t_min: {global_t_min:.1f} s (Epoch UTC)")
    print(f"  Global t_max: {global_t_max:.1f} s (Epoch UTC)")
    print(f"  Day Duration: {(global_t_max - global_t_min)/3600.0:.2f} hours")
    print(f"  Global Alpha: {alpha:.2f} m/s ({alpha * 3.6:.1f} km/h)")
    print(f"  Unique Aircraft across 24h: {len(id_map):,}")

    # Phase 2: Stream directly into final output binary
    print(f"\n[Pass 2/2] Writing records directly to: {output_bin_path}")
    os.makedirs(os.path.dirname(os.path.abspath(output_bin_path)), exist_ok=True)

    # We write a placeholder header (28 bytes) first
    # Header: [OPS2 (4B)][dim: uint32 (4B)][count: uint64 (8B)][alpha: float32 (4B)][t_min: float64 (8B)] = 28 bytes
    total_valid_points = 0

    with open(output_bin_path, 'wb') as f_out:
        # Write dummy header to reserve exact 28 bytes
        f_out.write(b'\x00' * 28)

        rec_dtype = np.dtype([
            ('id', np.uint32),
            ('coords', np.float32, (4,))
        ])

        for idx, fpath in enumerate(files):
            fname = os.path.basename(fpath)
            print(f"  Converting [{idx+1}/{len(files)}]: {fname}...")

            df = pd.read_csv(fpath)
            
            col_time = next((c for c in ['time', 'timestamp'] if c in df.columns), None)
            col_lat = next((c for c in ['lat', 'latitude'] if c in df.columns), None)
            col_lon = next((c for c in ['lon', 'longitude'] if c in df.columns), None)
            col_alt = next((c for c in ['geoaltitude', 'baroaltitude', 'altitude'] if c in df.columns), None)
            col_id = next((c for c in ['icao24', 'flight_id'] if c in df.columns), None)

            if not all([col_time, col_lat, col_lon, col_alt, col_id]):
                continue

            df = df.dropna(subset=[col_time, col_lat, col_lon, col_alt, col_id]).copy()

            df = df[(df[col_lat] >= -90.0) & (df[col_lat] <= 90.0) &
                    (df[col_lon] >= -180.0) & (df[col_lon] <= 180.0) &
                    (df[col_alt] >= -100.0) & (df[col_alt] <= 25000.0)]

            chunk_len = len(df)
            if chunk_len == 0:
                continue

            x, y, z = geodetic_to_ecef(df[col_lat].values, df[col_lon].values, df[col_alt].values)
            t_norm = (df[col_time].values - global_t_min).astype(np.float32)
            w_time = t_norm * alpha
            flight_uints = df[col_id].map(id_map).fillna(0).astype(np.uint32).values

            bin_chunk = np.empty(chunk_len, dtype=rec_dtype)
            bin_chunk['id'] = flight_uints
            bin_chunk['coords'][:, 0] = x.astype(np.float32)
            bin_chunk['coords'][:, 1] = y.astype(np.float32)
            bin_chunk['coords'][:, 2] = z.astype(np.float32)
            bin_chunk['coords'][:, 3] = w_time.astype(np.float32)

            f_out.write(bin_chunk.tobytes())
            total_valid_points += chunk_len

        # Rewind to byte 0 and write the REAL header
        f_out.seek(0)
        magic = b'OPS2'
        dim = np.uint32(4)
        count = np.uint64(total_valid_points)
        alpha_val = np.float32(alpha)
        t_min_val = np.float64(global_t_min)

        f_out.write(magic)
        f_out.write(dim.tobytes())
        f_out.write(count.tobytes())
        f_out.write(alpha_val.tobytes())
        f_out.write(t_min_val.tobytes())
        f_out.flush()
        os.fsync(f_out.fileno())

    # Metadata JSON
    metadata_path = os.path.splitext(output_bin_path)[0] + "_metadata.json"
    metadata = {
        "dataset_directory": os.path.abspath(input_dir),
        "total_hourly_files": len(files),
        "total_4d_points": int(total_valid_points),
        "unique_aircraft_count": int(len(id_map)),
        "t_min_epoch_utc": global_t_min,
        "t_max_epoch_utc": global_t_max,
        "duration_hours": (global_t_max - global_t_min) / 3600.0,
        "velocity_alpha_mps": alpha,
        "coordinate_system": "ECEF (meters) + time (w = alpha * (t - t_min))"
    }
    with open(metadata_path, 'w') as f_meta:
        json.dump(metadata, f_meta, indent=2)

    print(f"\n[Done] Successfully saved full-day binary dataset!")
    print(f"  Binary File     : {output_bin_path} ({os.path.getsize(output_bin_path) / (1024*1024):.1f} MB)")
    print(f"  Metadata JSON   : {metadata_path}")
    print(f"  Total 4D Points : {total_valid_points:,}")

if __name__ == '__main__':
    default_base = "../opensky_experiment/data" if os.path.isdir("../opensky_experiment/data") else "opensky_experiment/data"
    default_in = os.path.join(default_base, "2019-05-27")
    default_out = os.path.join(default_base, "opensky_2019-05-27_full_day_4d.bin")

    in_dir = sys.argv[1] if len(sys.argv) > 1 else default_in
    out_bin = sys.argv[2] if len(sys.argv) > 2 else default_out
    batch_preprocess_day(in_dir, out_bin)

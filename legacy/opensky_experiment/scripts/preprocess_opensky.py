#!/usr/bin/env python3
"""
OpenSky 4D Preprocessing Script
- Filters rows missing essential fields (time, lat, lon, geoaltitude/baroaltitude)
- Calculates alpha as the average velocity (m/s)
- Converts spherical coordinates (lat, lon, alt) to Earth-Centered Earth-Fixed (ECEF) in meters
- Encodes flight ID (icao24) as uint32
- Produces normalized 4D point dataset: [x_m, y_m, z_m, alpha * (t - t_min)] with flight_id
- Saves t_min and metadata directly into binary header and sidecar JSON
- Saves both a clean CSV and a high-performance binary (.bin) file
"""

import sys
import os
import json
import struct
import numpy as np
import pandas as pd

# WGS-84 ellipsoid constants for GPS coordinates to ECEF (meters)
WGS84_A = 6378137.0         # semi-major axis (meters)
WGS84_E2 = 0.00669437999014 # first eccentricity squared

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

def preprocess_opensky(input_csv_path, output_csv_path, output_bin_path):
    print(f"[Preprocess] Loading raw OpenSky CSV: {input_csv_path}")
    if not os.path.exists(input_csv_path):
        print(f"[Error] File not found: {input_csv_path}")
        sys.exit(1)

    df = pd.read_csv(input_csv_path)
    initial_count = len(df)
    print(f"[Preprocess] Total raw rows: {initial_count:,}")

    col_time = next((c for c in ['time', 'timestamp', 'lastposupdate'] if c in df.columns), None)
    col_lat = next((c for c in ['lat', 'latitude'] if c in df.columns), None)
    col_lon = next((c for c in ['lon', 'longitude'] if c in df.columns), None)
    col_alt = next((c for c in ['geoaltitude', 'baroaltitude', 'altitude'] if c in df.columns), None)
    col_id = next((c for c in ['icao24', 'flight_id', 'callsign'] if c in df.columns), None)
    col_vel = next((c for c in ['velocity', 'speed', 'groundspeed'] if c in df.columns), None)

    if not all([col_time, col_lat, col_lon, col_alt, col_id]):
        print(f"[Error] Missing required columns! Found: time={col_time}, lat={col_lat}, lon={col_lon}, alt={col_alt}, id={col_id}")
        sys.exit(1)

    print(f"[Preprocess] Mapped columns: time='{col_time}', lat='{col_lat}', lon='{col_lon}', alt='{col_alt}', id='{col_id}'")

    df = df.dropna(subset=[col_time, col_lat, col_lon, col_alt, col_id]).copy()
    valid_coord_count = len(df)
    print(f"[Preprocess] Rows with valid coordinates: {valid_coord_count:,} (Dropped {initial_count - valid_coord_count:,} missing rows)")

    df = df[(df[col_lat] >= -90.0) & (df[col_lat] <= 90.0) &
            (df[col_lon] >= -180.0) & (df[col_lon] <= 180.0) &
            (df[col_alt] >= -100.0) & (df[col_alt] <= 25000.0)]

    if col_vel and col_vel in df.columns:
        valid_vel = df[col_vel].dropna()
        valid_vel = valid_vel[(valid_vel > 10.0) & (valid_vel < 400.0)]
        if len(valid_vel) > 0:
            alpha = float(valid_vel.mean())
            print(f"[Preprocess] Computed average velocity (alpha): {alpha:.2f} m/s ({alpha * 3.6:.1f} km/h)")
        else:
            alpha = 240.0
            print(f"[Preprocess] Fallback cruise velocity (alpha): {alpha:.2f} m/s")
    else:
        alpha = 240.0
        print(f"[Preprocess] Default cruise velocity (alpha): {alpha:.2f} m/s")

    unique_ids = df[col_id].unique()
    id_map = {id_str: idx + 1 for idx, id_str in enumerate(unique_ids)}
    df['flight_uint_id'] = df[col_id].map(id_map).astype(np.uint32)
    print(f"[Preprocess] Unique flights mapped: {len(unique_ids):,}")

    x, y, z = geodetic_to_ecef(df[col_lat].values, df[col_lon].values, df[col_alt].values)

    # Save exact original t_min safely
    t_min = float(df[col_time].min())
    t_max = float(df[col_time].max())
    print(f"[Preprocess] Dataset temporal range: t_min={t_min:.1f} s, t_max={t_max:.1f} s (Span: {(t_max - t_min)/3600.0:.2f} hours)")

    t_norm = (df[col_time].values - t_min).astype(np.float32)
    time_coord = t_norm * alpha

    processed = pd.DataFrame({
        'flight_id': df['flight_uint_id'].values,
        'icao24': df[col_id].values,
        'x_m': x.astype(np.float32),
        'y_m': y.astype(np.float32),
        'z_m': z.astype(np.float32),
        'w_time_m': time_coord.astype(np.float32),
        'raw_time': df[col_time].values,
        'lat': df[col_lat].values,
        'lon': df[col_lon].values,
        'alt_m': df[col_alt].values
    })

    print(f"[Preprocess] Writing cleaned CSV to: {output_csv_path}")
    processed.to_csv(output_csv_path, index=False)

    # Save sidecar metadata JSON file safely preserving t_min
    metadata_path = os.path.splitext(output_bin_path)[0] + "_metadata.json"
    metadata = {
        "dataset_name": os.path.basename(input_csv_path),
        "total_points": int(len(processed)),
        "unique_flights": int(len(unique_ids)),
        "t_min_epoch_utc": t_min,
        "t_max_epoch_utc": t_max,
        "duration_seconds": t_max - t_min,
        "velocity_alpha_mps": alpha,
        "coordinate_system": "ECEF (meters) + time_dimension (w = alpha * (t - t_min))"
    }
    with open(metadata_path, 'w') as f_meta:
        json.dump(metadata, f_meta, indent=2)
    print(f"[Preprocess] Preserved t_min and metadata safely to: {metadata_path}")

    # Binary Format (Enhanced with t_min in header):
    # Magic: 'O', 'P', 'S', '2' (4 bytes - v2 format with double t_min)
    # Dimension: uint32 (4)
    # Count: uint64
    # Alpha: float32
    # T_min: float64 (preserves absolute epoch seconds to full microsecond precision)
    # Records: count * [uint32 flight_id, float32 x, float32 y, float32 z, float32 w]
    print(f"[Preprocess] Writing binary dataset to: {output_bin_path}")
    with open(output_bin_path, 'wb') as f:
        magic = b'OPS2'
        dim = np.uint32(4)
        count = np.uint64(len(processed))
        alpha_val = np.float32(alpha)
        t_min_val = np.float64(t_min)

        f.write(magic)
        f.write(dim.tobytes())
        f.write(count.tobytes())
        f.write(alpha_val.tobytes())
        f.write(t_min_val.tobytes())

        rec_dtype = np.dtype([
            ('id', np.uint32),
            ('coords', np.float32, (4,))
        ])
        binary_data = np.empty(len(processed), dtype=rec_dtype)
        binary_data['id'] = processed['flight_id'].values
        binary_data['coords'][:, 0] = processed['x_m'].values
        binary_data['coords'][:, 1] = processed['y_m'].values
        binary_data['coords'][:, 2] = processed['z_m'].values
        binary_data['coords'][:, 3] = processed['w_time_m'].values
        f.write(binary_data.tobytes())

    print(f"[Preprocess] Successfully generated {len(processed):,} valid 4D points!")
    print(f"[Preprocess] Binary C++ cache: {output_bin_path}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        in_path = "opensky_experiment/data/opensky_raw.csv"
        out_csv = "opensky_experiment/data/opensky_cleaned_4d.csv"
        out_bin = "opensky_experiment/data/opensky_4d.bin"
    else:
        in_path = sys.argv[1]
        out_csv = sys.argv[2] if len(sys.argv) > 2 else "opensky_experiment/data/opensky_cleaned_4d.csv"
        out_bin = sys.argv[3] if len(sys.argv) > 3 else "opensky_experiment/data/opensky_4d.bin"

    preprocess_opensky(in_path, out_csv, out_bin)

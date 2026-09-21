#!/usr/bin/env python3
"""
OpenSky Hourly Multi-Threaded Dataset Downloader
Downloads hourly state vector archives from the OpenSky S3 repository and extracts them to .csv.gz
"""

import sys
import os
import io
import time
import tarfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

S3_BASE = "https://s3.opensky-network.org/data-samples"

def download_and_extract_key(key, target_dir):
    url = f"{S3_BASE}/{key}"
    fname = os.path.basename(key)
    
    # Target file name inside target_dir
    expected_gz = fname.replace(".tar", ".gz") if fname.endswith(".tar") else fname
    final_path = os.path.join(target_dir, expected_gz)
    
    # Check if file already exists and is non-empty
    if os.path.isfile(final_path) and os.path.getsize(final_path) > 1024 * 1024:
        return {"key": key, "status": "cached", "path": final_path, "size_mb": round(os.path.getsize(final_path) / (1024*1024), 2)}

    t0 = time.time()
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    with urllib.request.urlopen(req, timeout=120) as resp:
        content = resp.read()

    # If it's a tar archive, extract .csv.gz or .csv directly
    if key.endswith(".tar"):
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as tar:
            for member in tar.getmembers():
                if member.name.endswith(".csv.gz") or member.name.endswith(".csv"):
                    extracted_path = os.path.join(target_dir, os.path.basename(member.name))
                    f_out = tar.extractfile(member)
                    if f_out:
                        with open(extracted_path, "wb") as f_dst:
                            f_dst.write(f_out.read())
                        elapsed = time.time() - t0
                        size_mb = os.path.getsize(extracted_path) / (1024 * 1024)
                        return {"key": key, "status": "downloaded", "path": extracted_path, "size_mb": round(size_mb, 2), "elapsed": round(elapsed, 1)}
    else:
        with open(final_path, "wb") as f_dst:
            f_dst.write(content)
        elapsed = time.time() - t0
        size_mb = os.path.getsize(final_path) / (1024 * 1024)
        return {"key": key, "status": "downloaded", "path": final_path, "size_mb": round(size_mb, 2), "elapsed": round(elapsed, 1)}

    return {"key": key, "status": "failed", "path": None, "size_mb": 0}

def download_hourly_dataset(keys, target_dir, max_workers=6):
    os.makedirs(target_dir, exist_ok=True)
    print(f"\n[Downloader] Target directory: {target_dir}")
    print(f"[Downloader] Downloading {len(keys)} hourly archives using {max_workers} worker threads...")
    
    t_start = time.time()
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {pool.submit(download_and_extract_key, key, target_dir): key for key in keys}
        
        completed = 0
        for fut in as_completed(future_map):
            completed += 1
            res = fut.result()
            results.append(res)
            status_tag = "Cached" if res["status"] == "cached" else f"Downloaded in {res.get('elapsed', 0)}s"
            fname = os.path.basename(res.get("path") or res["key"])
            print(f"  [{completed:2d}/{len(keys):2d}] {fname} ({res['size_mb']} MB) -> {status_tag}")
            
    total_sec = time.time() - t_start
    total_mb = sum(r["size_mb"] for r in results)
    print(f"[Downloader] Download completed: {len(results)} files ({total_mb:.1f} MB) in {total_sec:.1f}s.\n")
    return results

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 downloader.py <date_prefix> <target_dir>")
        sys.exit(1)
    prefix = sys.argv[1]
    out_dir = sys.argv[2]

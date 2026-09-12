#!/usr/bin/env python3
"""
OpenSky Available Dates Inspector
Queries the official OpenSky S3 repository to list available dates and verify hourly data coverage.
"""

import sys
import re
import urllib.request
import xml.etree.ElementTree as ET

S3_BASE = "https://s3.opensky-network.org/data-samples"

def get_available_dates():
    url = f"{S3_BASE}?list-type=2&delimiter=/&prefix=states/"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        xml_data = resp.read()

    root = ET.fromstring(xml_data)
    ns = {'s3': 'http://s3.amazonaws.com/doc/2006-03-01/'}
    
    date_entries = []
    for elem in root.findall('s3:CommonPrefixes', ns):
        prefix = elem.find('s3:Prefix', ns).text
        raw = prefix.replace('states/', '').replace('/', '')
        clean = raw.lstrip('.')
        # Match YYYY-MM-DD pattern
        if re.match(r'^\d{4}-\d{2}-\d{2}$', clean):
            date_entries.append({
                "date": clean,
                "prefix": prefix
            })
            
    date_entries.sort(key=lambda x: x["date"])
    return date_entries

def get_hourly_keys_for_date(prefix):
    url = f"{S3_BASE}?list-type=2&prefix={prefix}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        xml_data = resp.read()

    root = ET.fromstring(xml_data)
    ns = {'s3': 'http://s3.amazonaws.com/doc/2006-03-01/'}
    
    keys = []
    for elem in root.findall('s3:Contents', ns):
        key = elem.find('s3:Key', ns).text
        if key.endswith('.csv.tar') or key.endswith('.csv.gz'):
            keys.append(key)
    keys.sort()
    return keys

def find_qualified_dates(min_hours=10, limit=20):
    all_dates = get_available_dates()
    print(f"[OpenSky API] Fetched {len(all_dates)} total dates from repository.")
    print(f"[OpenSky API] Scanning for dates with >= {min_hours} hours...")
    
    qualified = []
    # Check newest to oldest
    for item in reversed(all_dates):
        try:
            keys = get_hourly_keys_for_date(item["prefix"])
            hour_count = len(keys)
            if hour_count >= min_hours:
                item["hours"] = hour_count
                item["keys"] = keys
                qualified.append(item)
                print(f"  --> Date: {item['date']} | Hours Available: {hour_count}/24")
                if len(qualified) >= limit:
                    break
        except Exception as e:
            continue
            
    return qualified

if __name__ == '__main__':
    min_h = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    dates = find_qualified_dates(min_hours=min_h, limit=10)
    print(f"\n[Summary] Found {len(dates)} dates matching criteria (>= {min_h} hours).")

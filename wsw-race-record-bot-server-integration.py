import configparser
import gzip
import io
import json
import os
import re
import shutil
import sqlite3
import struct
import sys
from datetime import datetime, timedelta
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

config = configparser.ConfigParser()
config.read('config.cfg')

server_url = config.get('Settings', 'server_url')

RECORD_CHANNELS = json.loads(config.get("RECORD_CHANNELS","CHANNELS"))

ERROR_LOG_CHANNEL = config.getint('Settings', 'ERROR_LOG_CHANNEL')

# URL of your SQLite file
url = config.get('Settings', 'url')
server_url = config.get('Settings', 'server_url')
# Output file name
new_db_path = config.get('Settings', 'new_db_path')

changes = []

pending_error_message = None
# Download the file

from datetime import datetime
import string

def find_demo_and_map_link(map_name: str, target_time: str, demos_dir: str,
                           server_url: str ,
                           record_update: dict | None = None):
    # ---------------- CONFIG ----------------
    BASE_URL = config.get('Settings', 'BASE_URL')
    MAPLIST_URL = config.get('Settings', 'MAPLIST_URL')

    # helper to sanitize filenames (remove characters Windows/Unix don't like)
    INVALID_CHARS = '<>:"/\\|?*'
    def sanitize_filename(s: str):
        # remove invalid chars and collapse whitespace
        out = "".join(c for c in s if c not in INVALID_CHARS)
        out = " ".join(out.split())  # collapse multiple spaces
        return out.strip()

    def fetch_map_url(map_name: str):
        try:
            r = requests.get(MAPLIST_URL, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a['href']
                if href.endswith(".pk3") and map_name in href:
                    if href.startswith("http"):
                        return href
                    else:
                        return "http://livesow.net" + href
            return None
        except requests.RequestException as e:
            print(f"Error fetching map URL: {e}")
            return None

    def fetch_demo_links(map_name: str):
        try:
            r = requests.get(BASE_URL, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            links = []
            for a in soup.find_all("a", href=True):
                href = a['href']
                if href.endswith(".wdz20") and map_name.lower() in href.lower():
                    if href.startswith("http"):
                        links.append(href)
                    else:
                        href = href.lstrip('/')
                        links.append(f"{BASE_URL.rstrip('/')}/{href}")
            return links
        except requests.RequestException as e:
            print(f"Error fetching demo links: {e}")
            return []

    def download_file(url: str, out_path: str):
        try:
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            with open(out_path, 'wb') as f:
                f.write(r.content)
            print(f"Downloaded: {out_path}")
            return out_path
        except requests.RequestException as e:
            print(f"Error downloading {url}: {e}")
            return None

    def formatTime(millis: int):
        secs = millis // 1000
        mins = secs // 60
        secs = secs % 60
        return f"{mins:02d}:{secs:02d}"

    def recTimeToMillis(time: str):
        split = re.split(r"\.|:", time)
        return int(split[-1]) + int(split[-2]) * 1000 + int(split[-3]) * 1000 * 60

    finish_pattern = re.compile(r".*Race Finished.*Current: \^\d([\d:\.]*)")

    def parseFinishTimes(file):
        buf = io.BytesIO(file.read())
        server_time_start = -1
        while True:
            # read message length (same as before)
            msg_len, = struct.unpack('<l', buf.read(4))
            if msg_len <= 0: break
            msg_buf = io.BytesIO(buf.read(msg_len))
            cmd, = struct.unpack('<b', msg_buf.read(1))
            if cmd == 12:  # svc_frame
                _, serverTime = struct.unpack('<hl', msg_buf.read(6))
                if server_time_start == -1:
                    server_time_start = serverTime
                data = msg_buf.read()
                data_str = "".join(filter(str.isprintable, data.decode('ascii', errors='ignore')))
                m = finish_pattern.match(data_str)
                if m != None:
                    rec_time = m.group(1)
                    server_time_end = serverTime - server_time_start - 3000
                    yield (
                        formatTime(server_time_end),
                        rec_time,
                        formatTime(server_time_end - recTimeToMillis(rec_time))
                    )

    def check_demo_for_time(demo_path: str, target_time: str):
        try:
            with gzip.open(demo_path, 'rb') as file:
                for server_time, rec_time, time_start in parseFinishTimes(file):
                    if rec_time == target_time:
                        return True, time_start
        except Exception as e:
            print(f"Error parsing demo {demo_path}: {e}")
            return False, None
        return False, None

    # helpers to format times so filename does not contain illegal chars
    def time_to_seconds_str(t: str):
        # Converts "MM:SS.xxx" or "SS.xxx" or "MM:SS" to "total_seconds.xxx"
        if not t:
            return "unknown"
        parts = t.split(':')
        try:
            if len(parts) == 1:
                return f"{float(parts[0]):.3f}"
            else:
                mins = int(parts[0])
                secs = float(parts[1])
                total = mins * 60 + secs
                return f"{total:.3f}"
        except Exception:
            # fallback: replace colon with dot
            return t.replace(':', '.')

    def server_time_safe(t: str):
        if not t:
            return "unknown"
        return t.replace(':', '.').strip()

    # ---------------- MAIN LOGIC ----------------
    map_url = fetch_map_url(map_name)
    demo_links = fetch_demo_links(map_name)

    server_time = None
    found_demo_url = None
    final_demo_path = None

    if not demo_links:
        print(f"No demos found for map {map_name}")
        return map_url, None, None, None

    print(f"Found {len(demo_links)} demos for map {map_name}")

    os.makedirs(demos_dir, exist_ok=True)

    for url in demo_links:
        demo_filename = os.path.basename(url)
        demo_path = os.path.join(demos_dir, demo_filename)

        downloaded_path = download_file(url, demo_path)
        if not downloaded_path:
            continue

        found, time_start = check_demo_for_time(downloaded_path, target_time)
        if found:
            print(f"✓ Found the demo with target time!")
            print(f"  Original URL: {url}")
            print(f"  Jump time: {time_start}")
            print(f"  Saved to: {demo_path}")

            # Build a pretty name if record_update provided; otherwise keep original filename
            pretty_name = demo_filename
            try:
                if record_update:
                    # map name sanitized
                    safe_map = sanitize_filename(map_name)

                    # is it a WR?
                    is_wr = record_update.get('type') == 'NEW GLOBAL 1ST'

                    # convert bracket time to seconds.millis (no colon)
                    seconds_str = time_to_seconds_str(target_time)

                    # player
                    raw_player = str(record_update.get('player', '')).strip()
                    safe_player = sanitize_filename(raw_player)

                    # --- date: try to extract YYYY-MM-DD from original demo filename ---
                    # demo_filename example: "2025-10-13_20-08_hrace_kool_haster01-wjfix_auto0217.wdz20"
                    date_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})_', demo_filename)
                    if date_match:
                        year, month, day = date_match.groups()
                        date_str = f"{day}-{month}-{year}"  # "13-10-2025"
                    else:
                        # fallback if not present
                        date_str = datetime.now().strftime("%d-%m-%Y")

                    # demo jump safe
                    demo_jump = server_time_safe(time_start)

                    # extension from original
                    ext = os.path.splitext(demo_filename)[1] or ".wdz20"

                    # Compose name:
                    # e.g. "kool_haster01-wjfix WR [50.836] by ngc.JebKemov 08-10-2025 (31.03).wdz20"
                    pretty_name = f"{safe_map}{' WR' if is_wr else ''} [{seconds_str}] by {safe_player} {date_str} ({demo_jump}){ext}"

                    # final sanitize (keeps the human readable structure but removes OS-invalid chars)
                    pretty_name = sanitize_filename(pretty_name)

            except Exception as ex:
                print(f"Warning: failed to build pretty name: {ex}")
                pretty_name = demo_filename

            pretty_path = os.path.join(demos_dir, pretty_name)

            # Try to rename (atomic-ish)
            try:
                # If target name already exists, add suffix to avoid collision
                if os.path.exists(pretty_path):
                    base, ext = os.path.splitext(pretty_name)
                    i = 1
                    while os.path.exists(os.path.join(demos_dir, f"{base}-{i}{ext}")):
                        i += 1
                    pretty_name = f"{base}-{i}{ext}"
                    pretty_path = os.path.join(demos_dir, pretty_name)

                os.rename(demo_path, pretty_path)
                print(f"Renamed demo to: {pretty_name}")
                final_demo_path = pretty_path
            except Exception as e:
                # don't fail the entire run if rename fails; fallback to original filename
                print(f"Warning: failed to rename demo: {e}. Keeping original filename.")
                final_demo_path = demo_path
                pretty_name = demo_filename

            # Build the public URL that points to your server
            # encode the pretty filename when building the public URL
            encoded_pretty = quote(pretty_name, safe='')
            found_demo_url = f"{server_url.rstrip('/')}/demos/{encoded_pretty}"
            server_time = time_start

            print(f"  Demo public URL (constructed): {found_demo_url}")
            print("✓ Demo processed and prepared for hosting.")
            break
        else:
            print(f"✗ Target time not found in {demo_filename}. Deleting...")
            try:
                os.remove(downloaded_path)
            except Exception:
                pass

    if found_demo_url:
        return map_url, found_demo_url, server_time, final_demo_path
    else:
        print("✗ No demo found with the specified target time.")
        return map_url, None, None, None



def format_race_time(ms):
    minutes = ms // 60000
    seconds = (ms % 60000) // 1000
    millis = ms % 1000

    return f"{minutes:02}:{seconds:02}.{millis:03d}"
    # if minutes > 0:
    #    return f"{minutes}:{seconds:02d}.{millis:03d}"
    # else:
    #    return f"{seconds:02d}.{millis:03d}"


def checkforupdates():
    changes = []

    response = requests.get(url)
    if response.status_code == 200:
        with open(new_db_path, "wb") as f:
            f.write(response.content)
        print("SQLite file downloaded successfully.")
    else:
        print(f"Failed to download file. Status code: {response.status_code}")

    new_db = config.get('Settings', 'new_db_path')
    old_db = config.get('Settings', 'main_db_path')

    # Connect to databases
    cnew = sqlite3.connect(new_db)
    cmain = sqlite3.connect(old_db)
    crsrnew = cnew.cursor()
    crsrmain = cmain.cursor()

    def get_key_records(cursor, connection):
        """Get the 4 key records for each map: global 1st, global 2nd, local 1st, local 2nd"""
        cursor.execute("SELECT COUNT(*) FROM map")
        connection.commit()
        map_count = cursor.fetchone()[0]

        key_records = {}  # map_id -> list of key records

        for map_id in range(1, map_count + 1):
            records = []

            # Get global 1st and 2nd (any version, ordered by global_rank, then version priority, then player_id)
            cursor.execute("""
                SELECT id, version_id, player_id, map_id, time, version_rank, global_rank, 'global' as record_type
                FROM race 
                WHERE map_id = ? AND global_rank <= 2 
                ORDER BY global_rank, version_id, player_id
            """, (map_id,))
            connection.commit()
            global_records = cursor.fetchall()

            # Add global records with proper labeling based on actual rank
            for record in global_records:
                record_list = list(record)
                global_rank = record[6]  # global_rank is at index 6
                record_list[-1] = f'global_{global_rank}'  # 'global_1' or 'global_2'
                records.append(tuple(record_list))

            # Get local 1st and 2nd (version_id = 1, ordered by version_rank, then player_id)
            cursor.execute("""
                SELECT id, version_id, player_id, map_id, time, version_rank, global_rank, 'local' as record_type
                FROM race 
                WHERE map_id = ? AND version_id = 1 AND version_rank <= 2 
                ORDER BY version_rank, player_id
            """, (map_id,))
            connection.commit()
            local_records = cursor.fetchall()

            # Add local records with proper labeling based on actual rank
            for record in local_records:
                record_list = list(record)
                version_rank = record[5]  # version_rank is at index 5
                record_list[-1] = f'local_{version_rank}'  # 'local_1' or 'local_2'
                records.append(tuple(record_list))

            key_records[map_id] = records

        return key_records, map_count

    def filter_database_to_key_records(cursor, connection, key_records):
        """Remove all records except the key ones and renumber IDs"""
        # Collect all key record IDs
        all_key_ids = set()
        for map_records in key_records.values():
            for record in map_records:
                all_key_ids.add(record[0])  # record[0] is the ID

        # Delete all records not in key IDs
        if all_key_ids:
            placeholders = ','.join('?' * len(all_key_ids))
            cursor.execute(f"DELETE FROM race WHERE id NOT IN ({placeholders})", list(all_key_ids))
        else:
            cursor.execute("DELETE FROM race")
        connection.commit()

        # Get remaining records and renumber them
        cursor.execute("SELECT * FROM race ORDER BY map_id, global_rank, version_id, player_id")
        connection.commit()
        remaining_records = cursor.fetchall()

        # Clear table and reinsert with new IDs
        cursor.execute("DELETE FROM race")
        connection.commit()

        updated_records = []
        for new_id, record in enumerate(remaining_records, 1):
            record_list = list(record)
            record_list[0] = new_id  # Set new ID
            updated_records.append(tuple(record_list))

        if updated_records:
            cursor.executemany("INSERT INTO race VALUES (?,?,?,?,?,?,?)", updated_records)
            connection.commit()

    # Process new database first
    print("Processing new database...")
    new_key_records, map_count = get_key_records(crsrnew, cnew)
    filter_database_to_key_records(crsrnew, cnew, new_key_records)

    # Get old database key records
    print("Processing old database...")
    old_key_records, _ = get_key_records(crsrmain, cmain)

    def normalize_record_for_comparison(record):
        """Create a comparable version of a record (ignoring ID)"""
        # record format: (id, version_id, player_id, map_id, time, version_rank, global_rank, record_type)
        return (record[1], record[2], record[3], record[4], record[5], record[6], record[7])  # exclude ID

    def detect_changes(old_records, new_records, map_id):
        """Detect what changed for a specific map"""
        changes = []

        # Create lookup by record type for easier comparison
        old_by_type = {}
        new_by_type = {}

        for record in old_records.get(map_id, []):
            old_by_type[record[7]] = normalize_record_for_comparison(record)  # record[7] is record_type

        for record in new_records.get(map_id, []):
            new_by_type[record[7]] = normalize_record_for_comparison(record)

        # Check each record type
        record_types = ['global_1', 'global_2', 'local_1', 'local_2']

        for record_type in record_types:
            old_record = old_by_type.get(record_type)
            new_record = new_by_type.get(record_type)

            if old_record != new_record:
                if new_record and not old_record:
                    # New record appeared
                    changes.append(('added', record_type, new_record))
                elif new_record and old_record:
                    # Record changed
                    changes.append(('updated', record_type, new_record, old_record))
                elif old_record and not new_record:
                    # Record disappeared (shouldn't happen often)
                    changes.append(('removed', record_type, old_record))

        return changes

    def format_record_info(cursor, connection, player_id, map_id, time):
        """Format player name, map name, and time"""
        cursor.execute("SELECT simplified FROM player WHERE id = ?", (player_id,))
        connection.commit()
        player_name = cursor.fetchone()
        player_name = player_name[0] if player_name else f"(ID {player_id})"

        cursor.execute("SELECT name FROM map WHERE id = ?", (map_id,))
        connection.commit()
        map_name = cursor.fetchone()
        map_name = map_name[0] if map_name else f"(ID {map_id})"

        formatted_time = format_race_time(time)

        return player_name, map_name, formatted_time

    def get_reference_times(cursor, connection, map_id):
        """Get reference times for context in announcements"""
        references = {}

        # Get all current records for this map
        cursor.execute("""
            SELECT version_id, player_id, time, version_rank, global_rank
            FROM race
            WHERE map_id = ?
            ORDER BY global_rank, version_id, player_id
        """, (map_id,))
        connection.commit()
        records = cursor.fetchall()

        for record in records:
            version_id, player_id, time, version_rank, global_rank = record

            if global_rank == 1:
                references['global_1'] = record
            elif global_rank == 2:
                references['global_2'] = record
            elif version_id == 1 and version_rank == 1:
                references['local_1'] = record
            elif version_id == 1 and version_rank == 2:
                references['local_2'] = record

        return references

    # Store record updates for the embed
    record_updates = []
    missing_demo = False
    processed_records = set()  # Track (player_id, map_id, time) to avoid duplicates

    print("Detecting changes...")

    # Check each map for changes
    for map_id in range(1, map_count + 1):
        map_changes = detect_changes(old_key_records, new_key_records, map_id)

        if map_changes:
            print(f"\nChanges detected in map {map_id}:")
            for change in map_changes:
                print(f"  Change: {change[0]} {change[1]}")
                if len(change) > 2:
                    print(f"    New: {change[2]}")
                if len(change) > 3:
                    print(f"    Old: {change[3]}")

            # Get reference times for context
            references = get_reference_times(crsrnew, cnew, map_id)

            for change in map_changes:
                if missing_demo:
                    break

                change_type = change[0]  # 'added', 'updated', 'removed'
                record_type = change[1]  # 'global_1', 'global_2', 'local_1', 'local_2'
                new_record = change[2] if len(change) > 2 else None
                old_record = change[3] if len(change) > 3 else None

                # Only process added or updated records (new records)
                if change_type in ['added', 'updated'] and new_record:
                    # new_record format: (version_id, player_id, map_id, time, version_rank, global_rank, record_type)
                    version_id, player_id, map_id_from_record, time, version_rank, global_rank, _ = new_record

                    # Use the record's map_id for dedup keys (safer) and avoid re-processing same (player,map,time)
                    record_key = (player_id, map_id_from_record, time)
                    if record_key in processed_records:
                        print(f"Skipping duplicate record: {record_key}")
                        continue
                    processed_records.add(record_key)

                    # If this change was an 'updated' type, extract the old record info safely
                    old_version_id = old_player_id = old_map_id = old_time = old_version_rank = old_global_rank = None
                    if change_type == 'updated' and old_record:
                        try:
                            old_version_id, old_player_id, old_map_id, old_time, old_version_rank, old_global_rank, _ = old_record
                        except Exception:
                            old_version_id = old_player_id = old_map_id = old_time = old_version_rank = old_global_rank = None

                        # If same player & same time moved to a worse rank (e.g. local_1 -> local_2 or global_1 -> global_2) skip
                        if old_player_id is not None and old_time is not None:
                            if (player_id == old_player_id and time == old_time and
                                    ((record_type == 'global_2' and old_global_rank == 1) or
                                     (record_type == 'local_2' and old_version_rank == 1))):
                                print(f"Skipping pushed-down record: player {player_id} time {time} moved down.")
                                continue

                    # Additional: new_record might be an old record from a different slot in this same set of map_changes
                    # Example: old local_1 -> new local_2 (same player+time). Detect by scanning map_changes' old entries
                    pushed_down_found = False
                    if record_type in ('local_2', 'global_2'):
                        for old_change in map_changes:
                            if len(old_change) > 3:
                                old_type = old_change[1]
                                old_rec = old_change[3]
                                # old_rec layout is (version_id, player_id, map_id, time, version_rank, global_rank, record_type)
                                try:
                                    old_rec_player = old_rec[1]
                                    old_rec_time = old_rec[3]
                                except Exception:
                                    continue
                                if old_rec_player == player_id and old_rec_time == time:
                                    # if the previous slot was the higher slot (local_1 or global_1), skip this pushed-down entry
                                    if (record_type == 'global_2' and old_type == 'global_1') or \
                                            (record_type == 'local_2' and old_type == 'local_1'):
                                        print(f"Skipping {record_type} because it is the old {old_type} pushed down.")
                                        pushed_down_found = True
                                        break
                    if pushed_down_found:
                        continue

                    # If time got worse compared to the immediate old_record, skip too (safety)
                    if change_type == 'updated' and old_record and old_time is not None:
                        try:
                            if time > old_time:
                                print(
                                    f"Skipping worse time: {format_race_time(time)} vs previous {format_race_time(old_time)}")
                                continue
                        except Exception:
                            pass

                    # Check if this exact time existed before for this map/version
                    time_already_existed = False
                    if change_type == 'updated' and old_record:
                        old_version_id, old_player_id, old_map_id, old_time, old_version_rank, old_global_rank, _ = old_record
                        time_already_existed = (old_time == time)  # Same time as old record

                        # Skip if it's just a reordering of identical times (not a real improvement)
                        if time_already_existed and record_type.startswith('global'):
                            print(
                                f"Skipping tie reordering: {player_name} vs previous holder, both with {format_race_time(time)}")
                            continue

                    player_name, map_name, formatted_time = format_record_info(crsrnew, cnew, player_id, map_id, time)
                    tie_suffix = " TIE" if time_already_existed else ""

                    # Create record update object
                    record_update = {
                        'type': '',
                        'player': player_name,
                        'map': map_name,
                        'time': formatted_time,
                        'tie': tie_suffix,
                        'global_1st': None,
                        'global_2nd': None,
                        'local_1st': None,
                        'map_link': None,
                        'demo_link': None,
                        'demo_jump': None
                    }

                    # Determine record type and set reference times
                    if record_type == 'global_1':
                        record_update['type'] = 'NEW GLOBAL 1ST'
                        if 'global_2' in references:
                            ref = references['global_2']
                            g2_player, _, g2_time = format_record_info(crsrnew, cnew, ref[1], map_id, ref[2])
                            crsrnew.execute("SELECT name FROM version WHERE id = ?", (ref[0],))
                            cnew.commit()
                            g2_version = crsrnew.fetchone()
                            g2_version = g2_version[0] if g2_version else f"Version {ref[0]}"
                            record_update['global_2nd'] = f"{g2_time} by {g2_player} in {g2_version}"

                    elif record_type == 'global_2':
                        record_update['type'] = 'NEW GLOBAL 2ND'
                        if 'global_1' in references:
                            ref = references['global_1']
                            g1_player, _, g1_time = format_record_info(crsrnew, cnew, ref[1], map_id, ref[2])
                            crsrnew.execute("SELECT name FROM version WHERE id = ?", (ref[0],))
                            cnew.commit()
                            g1_version = crsrnew.fetchone()
                            g1_version = g1_version[0] if g1_version else f"Version {ref[0]}"
                            record_update['global_1st'] = f"{g1_time} by {g1_player} in {g1_version}"

                    elif record_type == 'local_1':
                        # Only announce local 1st if it's not also global 2nd
                        if global_rank != 2:
                            record_update['type'] = 'NEW LOCAL 1ST'
                            if 'global_1' in references:
                                ref = references['global_1']
                                g1_player, _, g1_time = format_record_info(crsrnew, cnew, ref[1], map_id, ref[2])
                                crsrnew.execute("SELECT name FROM version WHERE id = ?", (ref[0],))
                                cnew.commit()
                                g1_version = crsrnew.fetchone()
                                g1_version = g1_version[0] if g1_version else f"Version {ref[0]}"
                                record_update['global_1st'] = f"{g1_time} by {g1_player} in {g1_version}"

                    elif record_type == 'local_2':
                        record_update['type'] = 'NEW LOCAL 2ND'
                        if 'global_1' in references:
                            ref = references['global_1']
                            g1_player, _, g1_time = format_record_info(crsrnew, cnew, ref[1], map_id, ref[2])
                            crsrnew.execute("SELECT name FROM version WHERE id = ?", (ref[0],))
                            cnew.commit()
                            g1_version = crsrnew.fetchone()
                            g1_version = g1_version[0] if g1_version else f"Version {ref[0]}"
                            record_update['global_1st'] = f"{g1_time} by {g1_player} in {g1_version}"

                        # Show local 1st if different from global 1st
                        if 'local_1' in references and 'global_1' in references:
                            local_ref = references['local_1']
                            global_ref = references['global_1']
                            if local_ref[1] != global_ref[1] or local_ref[2] != global_ref[
                                2]:  # different player or time
                                l1_player, _, l1_time = format_record_info(crsrnew, cnew, local_ref[1], map_id,
                                                                           local_ref[2])
                                record_update['local_1st'] = f"{l1_time} by {l1_player}"

                    # Get demo and map links
                    if record_update['type']:  # Only if we have a valid record type
                        DEMOS_DIR = config.get('Settings', 'demos_output_path')
                        print(f"Starting search for map: {map_name} with time: {formatted_time}")

                        try:
                            # call the demo finder and unpack safely (supports 3- or 4-item returns)
                            result = find_demo_and_map_link(map_name, formatted_time, DEMOS_DIR,
                                                            server_url=config.get('Settings', 'server_url'),
                                                            record_update=record_update)

                            map_link = demo_link = server_time = demo_path = None
                            if result:
                                # result may be a tuple of length 2..4; unpack defensively
                                if len(result) >= 1:
                                    map_link = result[0]
                                if len(result) >= 2:
                                    demo_link = result[1]
                                if len(result) >= 3:
                                    server_time = result[2]
                                if len(result) >= 4:
                                    demo_path = result[3]

                            # If neither a public URL (demo_link) nor a local file (demo_path exists) are present,
                            # then the demo isn't available yet — abort the cycle.
                            if not demo_link and not (demo_path and os.path.exists(demo_path)):
                                print(f"Demo not available yet for {map_name} ({formatted_time}) — will skip this cycle.")
                                global pending_error_message
                                pending_error_message = f"@here Demo not available yet for {map_name} ({formatted_time})."
                                missing_demo = True
                                break

                            # at this point demo_link (public URL) or demo_path (local renamed file) exists,
                            # so continue processing this record. DO NOT set missing_demo again.

                            record_update['map_link'] = map_link
                            record_update['demo_link'] = demo_link
                            record_update['demo_jump'] = server_time

                        except Exception as e:
                            missing_demo = True
                            break

                        record_updates.append(record_update)

        if missing_demo:
            break

    # If any new record lacked a demo, skip the entire cycle
    if missing_demo:
        try:
            crsrmain.close()
            cmain.close()
            crsrnew.close()
            cnew.close()
        except Exception:
            pass
        print("Demo not available yet; skipping this cycle without updating or posting.")
        return []

    # Replace old database with new one
    print("Replacing old database...")
    crsrmain.close()
    cmain.close()
    crsrnew.close()
    cnew.close()

    if os.path.exists(old_db):
        os.remove(old_db)
        print("Deleted old database.")

    shutil.move(new_db, old_db)
    print("New database has replaced old database.")

    return record_updates

import discord
from discord.ext import commands, tasks
import asyncio

bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

# Store the last embed message for editing
last_embed_message = None


def create_records_embeds(record_updates, max_per_embed=4):
    """Create multiple embeds if needed to handle Discord limits"""
    if not record_updates:
        embed = discord.Embed(
            title="🏁 Warsow Race Records Update",
            description="No new records found.",
            color=0x00ff00,
            timestamp=discord.utils.utcnow()
        )
        return [embed]

    # Group updates by type for better organization
    global_1st = [r for r in record_updates if r['type'] == 'NEW GLOBAL 1ST']
    global_2nd = [r for r in record_updates if r['type'] == 'NEW GLOBAL 2ND']
    local_1st = [r for r in record_updates if r['type'] == 'NEW LOCAL 1ST']
    local_2nd = [r for r in record_updates if r['type'] == 'NEW LOCAL 2ND']

    def format_record_text(record):
        text = f"__**{record['time']}** on **{record['map']}** by **{record['player']}** {record['tie']}__\n"

        if record['global_1st']:
            text += f"🥇 Global 1st: {record['global_1st']}\n"
        if record['global_2nd']:
            text += f"🥈 Global 2nd: {record['global_2nd']}\n"
        if record['local_1st']:
            text += f"🏠 Local 1st: {record['local_1st']}\n"

        # Add links
        links = []
        if record['map_link']:
            links.append(f"[Map]({record['map_link']})")
        if record['demo_link']:
            links.append(f"[Demo]({record['demo_link']})")
        if record['demo_jump']:
            links.append(f"demojump {record['demo_jump']}")

        if links:
            text += f"🔗 {' | '.join(links)}\n"

        return text

    def create_embed_for_records(records_dict, embed_number=1, total_embeds=1):
        """Create a single embed for a subset of records"""
        title = "🏁 Warsow Race Records Update"
        if total_embeds > 1:
            title += f" ({embed_number}/{total_embeds})"

        embed = discord.Embed(
            title=title,
            color=0x00ff00,
            timestamp=discord.utils.utcnow()
        )

        # Add fields for each category in this embed
        if records_dict.get('global_1st'):
            field_text = ""
            for record in records_dict['global_1st']:
                field_text += format_record_text(record) + "\n"
            embed.add_field(name="🏆 New World Record", value=field_text[:1024], inline=False)

        if records_dict.get('global_2nd'):
            field_text = ""
            for record in records_dict['global_2nd']:
                field_text += format_record_text(record) + "\n"
            embed.add_field(name="🥈 New Second Place", value=field_text[:1024], inline=False)

        if records_dict.get('local_1st'):
            field_text = ""
            for record in records_dict['local_1st']:
                field_text += format_record_text(record) + "\n"
            embed.add_field(name="🏠 New WSW 2.1 World Record", value=field_text[:1024], inline=False)

        if records_dict.get('local_2nd'):
            field_text = ""
            for record in records_dict['local_2nd']:
                field_text += format_record_text(record) + "\n"
            embed.add_field(name="🏡 New WSW 2.1 Second Place", value=field_text[:1024], inline=False)

        return embed

    def estimate_embed_size(records_dict):
        """Estimate the character count of an embed"""
        size = 100  # Base size for title, timestamp, etc.

        for category, records in records_dict.items():
            if records:
                # Field name + field content
                field_size = 50  # Field name overhead
                for record in records:
                    field_size += len(format_record_text(record))
                size += field_size

        return size

    # Try to fit records into embeds without exceeding Discord limits
    embeds = []
    all_records = {
        'global_1st': global_1st,
        'global_2nd': global_2nd,
        'local_1st': local_1st,
        'local_2nd': local_2nd
    }

    # Simple approach: if we have too many records, split them into chunks
    total_records = len(record_updates)

    if total_records <= max_per_embed:
        # Single embed can handle all records
        embed = create_embed_for_records(all_records)
        embed.set_footer(text=f"Total new records: {total_records}")
        embeds.append(embed)
    else:
        # Need to split into multiple embeds
        # Prioritize global 1st > global 2nd > local 1st > local 2nd
        priority_order = [
            ('global_1st', global_1st, "🏆 New World Record"),
            ('global_2nd', global_2nd, "🥈 New Second Place"),
            ('local_1st', local_1st, "🏠 New WSW 2.1 World Record"),
            ('local_2nd', local_2nd, "🏡 New WSW 2.1 Second Place")
        ]

        current_embed_records = {}
        current_embed_count = 0
        embed_number = 1

        # Estimate total embeds needed
        estimated_embeds = (total_records + max_per_embed - 1) // max_per_embed

        for category, records, field_name in priority_order:
            if not records:
                continue

            for record in records:
                # Check if we need to start a new embed
                if current_embed_count >= max_per_embed:
                    # Create embed with current records
                    embed = create_embed_for_records(current_embed_records, embed_number, estimated_embeds)
                    embed.set_footer(
                        text=f"Part {embed_number}/{estimated_embeds} • Total new records: {total_records}")
                    embeds.append(embed)

                    # Reset for next embed
                    current_embed_records = {}
                    current_embed_count = 0
                    embed_number += 1

                # Add record to current embed
                if category not in current_embed_records:
                    current_embed_records[category] = []
                current_embed_records[category].append(record)
                current_embed_count += 1

        # Create final embed with remaining records
        if current_embed_records:
            embed = create_embed_for_records(current_embed_records, embed_number, embed_number)
            embed.set_footer(text=f"Part {embed_number}/{embed_number} • Total new records: {total_records}")
            embeds.append(embed)

    return embeds



# Store last embed messages for each channel
last_embed_messages = {}  # channel_id -> message object

# Global reference to the bot for logging
_bot_instance = None

# Message batching system
log_batch = []
batch_timer = None


async def send_batched_logs():
    """Send all batched log messages as plain text messages with aggressive delays"""
    global log_batch, _bot_instance

    if not log_batch or not _bot_instance:
        return

    error_channel = _bot_instance.get_channel(ERROR_LOG_CHANNEL)
    if not error_channel:
        original_print("Error channel not found for batch logging")
        log_batch.clear()
        return

    try:
        # Create header with timestamp and summary
        errors = [msg for msg in log_batch if msg['is_error']]
        total_messages = len(log_batch)
        error_count = len(errors)

        # Create one big message with all logs
        header = f"📊 **Bot Activity Log** - {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        header += f"Total: {total_messages} messages ({error_count} errors)\n"
        header += "─" * 50 + "\n"

        # Add all messages in chronological order
        log_text = ""
        for msg in log_batch:
            timestamp = msg['timestamp'].strftime('%H:%M:%S')
            prefix = "🚨" if msg['is_error'] else "ℹ️"
            log_text += f"[{timestamp}] {prefix} {msg['content']}\n"

        full_message = header + log_text

        # Split into multiple messages if too long (Discord limit is 2000 characters)
        max_length = 1700  # Even more conservative buffer

        if len(full_message) <= max_length:
            # Single message
            await error_channel.send(f"```\n{full_message}\n```")
        else:
            # Split into multiple messages with VERY long delays
            # Send header first
            await error_channel.send(f"```\n{header}\n```")
            await asyncio.sleep(10)  # 10 second delay after header

            # Split the log content
            lines = log_text.split('\n')
            current_chunk = ""
            chunk_number = 1

            for line in lines:
                # Check if adding this line would exceed the limit
                test_chunk = current_chunk + line + "\n"
                if len(test_chunk) > max_length and current_chunk:
                    # Send current chunk
                    chunk_header = f"📄 Part {chunk_number}:\n" + "─" * 20 + "\n"
                    await error_channel.send(f"```\n{chunk_header}{current_chunk}\n```")
                    await asyncio.sleep(15)  # 15 second delay between parts!!
                    current_chunk = line + "\n"
                    chunk_number += 1
                else:
                    current_chunk = test_chunk

            # Send final chunk if any content remains
            if current_chunk.strip():
                chunk_header = f"📄 Part {chunk_number}:\n" + "─" * 20 + "\n"
                await error_channel.send(f"```\n{chunk_header}{current_chunk}\n```")

    except Exception as e:
        # Fallback to console if Discord fails
        original_print(f"Failed to send batched logs: {e}")
        for msg in log_batch:
            original_print(f"[BATCH] {msg['content']}")

    # Clear the batch
    log_batch.clear()


def schedule_batch_send():
    """Schedule sending batched logs after a delay"""
    global batch_timer, _bot_instance

    if batch_timer:
        batch_timer.cancel()

    if not _bot_instance:
        return


    async def delayed_send():
        await asyncio.sleep(30)  # Wait 30 seconds to batch more messages
        await send_batched_logs()

    try:
        loop = asyncio.get_event_loop()
        batch_timer = loop.create_task(delayed_send())
    except Exception as e:
        original_print(f"Failed to schedule batch send: {e}")


async def log_error(message, error=None, is_info=False):
    """Log critical errors immediately (bypasses batching for important errors)"""
    if not _bot_instance:
        original_print(f"Bot not ready for logging: {message}")
        return

    error_channel = _bot_instance.get_channel(ERROR_LOG_CHANNEL)
    if error_channel:
        timestamp = discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        prefix = "ℹ️ INFO" if is_info else "🚨 CRITICAL ERROR"

        log_message = f"**{prefix}** - {timestamp} UTC\n"
        log_message += f"```\n{message}\n"

        if error and not is_info:
            log_message += f"\nError Details:\n{str(error)[:500]}\n"

        log_message += "```"

        try:
            await error_channel.send(log_message)
        except Exception as e:
            original_print(f"Failed to send critical error log: {e}")
    else:
        original_print(f"Error channel not found. Message: {message}")


def log_to_discord_batch(message, is_error=False):
    """Add message to batch for later sending"""
    global log_batch

    # Add to batch
    log_batch.append({
        'content': message,
        'is_error': is_error,
        'timestamp': discord.utils.utcnow()
    })

    # Schedule batch sending
    schedule_batch_send()

    # If batch gets very large, send immediately to avoid memory issues
    if len(log_batch) >= 100:  # Much higher threshold
        if _bot_instance:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(send_batched_logs())
            except:
                pass


# Custom print function that batches messages
original_print = print


def discord_print(*args, **kwargs):
    """Replace print to send output to both console and Discord (batched)"""
    # Print to console as normal
    original_print(*args, **kwargs)

    # Also add to Discord batch
    if args and _bot_instance:
        message = ' '.join(str(arg) for arg in args)
        # Determine if this looks like an error
        error_keywords = ['error', 'failed', 'exception', 'critical', 'missing demo', '❌', '🚨', '⚠️']
        is_error = any(keyword in message.lower() for keyword in error_keywords)
        log_to_discord_batch(message, is_error)


# Replace the built-in print function
print = discord_print


@bot.event
async def on_ready():
    global _bot_instance
    _bot_instance = bot  # Store bot reference for logging

    print(f"Bot ready! Connected to {len(bot.guilds)} servers")
    print(f"Monitoring {len(RECORD_CHANNELS)} channels for record updates")
    if ERROR_LOG_CHANNEL:
        print(f"Error logging enabled for channel {ERROR_LOG_CHANNEL}")
    auto_check.start()  # start the background loop when the bot is ready
    backup_database.start()

@bot.command()
async def update(ctx):
    global last_embed_messages

    await ctx.send("🔄 Checking for updates...")
    try:
        record_updates = checkforupdates()
        embeds = create_records_embeds(record_updates)

        channel_id = ctx.channel.id

        last_embed_messages[channel_id] = await ctx.send(embeds=embeds)

    except Exception as e:
        await ctx.send(f"❌ Error occurred: {e}")
        await log_error(f"Error in manual update command", e)


@tasks.loop(minutes= config.getint('Settings', 'poll_rate'))  # change 60 to however many minutes you want
async def auto_check():
    global last_embed_messages

    try:
        pending_error_message = None
        record_updates = checkforupdates()

        if pending_error_message:
            error_channel = bot.get_channel(ERROR_LOG_CHANNEL)
            if error_channel:
                await error_channel.send(pending_error_message)
            print("⏭️ Skipping due to missing demo.")
            return

        # Only send/update if there are actual updates
        if record_updates:
            embeds = create_records_embeds(record_updates)

            # Send to all configured channels
            successful_updates = 0
            failed_updates = 0

            for channel_id in RECORD_CHANNELS:
                channel = bot.get_channel(channel_id)

                if channel is None:
                    await log_error(
                        f"Channel {channel_id} not found. Bot may not be in that server or lacks permissions.")
                    failed_updates += 1
                    continue

                try:
                    if channel_id in last_embed_messages:
                        try:
                            # Try to edit the existing message with new embeds
                            await last_embed_messages[channel_id].edit(embeds=embeds)
                            print(f"✅ Updated existing embeds in {channel.guild.name}#{channel.name}")
                            successful_updates += 1
                        except discord.NotFound:
                            # Message was deleted, send a new one
                            last_embed_messages[channel_id] = await channel.send(embeds=embeds)
                            print(
                                f"✅ Sent new embeds in {channel.guild.name}#{channel.name} (previous message not found)")
                            successful_updates += 1
                        except discord.HTTPException as e:
                            # Some other error, send a new message
                            await log_error(f"Error editing message in {channel.guild.name}#{channel.name}", e)
                            last_embed_messages[channel_id] = await channel.send(embeds=embeds)
                            print(f"✅ Sent new embeds in {channel.guild.name}#{channel.name} due to edit error")
                            successful_updates += 1
                    else:
                        # No previous message, send a new one
                        last_embed_messages[channel_id] = await channel.send(embeds=embeds)
                        print(f"✅ Sent new embeds in {channel.guild.name}#{channel.name} (no previous message)")
                        successful_updates += 1

                except discord.Forbidden:
                    await log_error(f"No permission to send messages in {channel.guild.name}#{channel.name}")
                    failed_updates += 1
                except Exception as e:
                    await log_error(f"Unexpected error sending to {channel.guild.name}#{channel.name}", e)
                    failed_updates += 1

            # Log summary
            total_records = len(record_updates)
            summary = f"📊 Update Summary: {total_records} new records sent to {successful_updates}/{len(RECORD_CHANNELS)} channels"
            if failed_updates > 0:
                summary += f" ({failed_updates} failed)"
            print(summary)

            if failed_updates > 0:
                await log_error(summary)

        else:
            print("ℹ️ No new records found")

    except Exception as e:
        error_msg = f"Critical error in auto_check: {str(e)}"
        print(f"❌ {error_msg}")
        await log_error("Critical error in auto_check loop", e)


# Add command to clear the stored message references
@bot.command()
async def clear_embed(ctx):
    global last_embed_messages
    last_embed_messages.clear()
    await ctx.send("✅ Cleared all embed message references. Next update will create new embeds.")


# Add command to get embed info
@bot.command()
async def embed_info(ctx):
    global last_embed_messages
    if last_embed_messages:
        info_text = f"📋 Tracking {len(last_embed_messages)} embed messages:\n"
        for channel_id, message in last_embed_messages.items():
            try:
                channel = bot.get_channel(channel_id)
                channel_name = f"{channel.guild.name}#{channel.name}" if channel else f"Channel {channel_id}"
                embed_count = len(message.embeds) if hasattr(message, 'embeds') else 1
                info_text += f"• {channel_name}: Message {message.id} ({embed_count} embeds)\n"
            except:
                info_text += f"• Channel {channel_id}: Message {message.id}\n"
        await ctx.send(info_text[:2000])  # Discord message limit
    else:
        await ctx.send("❌ No embed messages currently tracked.")

DB_PATH = config.get('Settings', 'main_db_path')

# Define where you want to store your backups
BACKUP_DIR = config.get('BACKUP', 'backup_dir')
import datetime,time
backup_interval_hours = config.getint('BACKUP', 'backup_interval_hours')
max_backup_days = config.getint('BACKUP', 'max_backup_days')
@tasks.loop(hours=backup_interval_hours)  # Run every 72 hours (3 days)
async def backup_database():
    # Generate a timestamp for the backup filename
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    backup_filename = f"backup_{timestamp}.sqlite"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    # Perform the database backup (copy the database file)
    try:
        shutil.copy(DB_PATH, backup_path)
        print(f"Backup successful: {backup_filename}")
    except Exception as e:
        print(f"Error while backing up the database: {e}")

    for filename in os.listdir(BACKUP_DIR):
        file_path = os.path.join(BACKUP_DIR, filename)
        file_creation_time = os.path.getctime(file_path)
        # If the file is older than 30 days, delete it
        if (time.time() - file_creation_time) > max_backup_days * 86400:
            os.remove(file_path)
token = config.get('Settings', 'token')
bot.run(token)

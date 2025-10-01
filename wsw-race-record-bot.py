import sqlite3
import os
import shutil
import time

import requests
import subprocess
import re
from bs4 import BeautifulSoup
import gzip, sys, struct, io, re

RECORD_CHANNELS = [
    1387767813325721661,  # Your main server channel
    1342037348761862195,  # Add more channel IDs here for other servers
]

ERROR_LOG_CHANNEL = 1421923420836331531

# URL of your SQLite file
url = "http://livesow.net/race/api/db.sqlite"

# Output file name
output_path = "C:\\Users\\Admin\\Desktop\\Warsow Server Records\\.hrace_record_bot\\db.sqlite"

changes = []


# Download the file

def find_demo_and_map_link(map_name: str, target_time: str, demos_dir: str):
    # ---------------- CONFIG ----------------
    BASE_URL = "http://livesow.net/race/demos/"
    MAPLIST_URL = "http://livesow.net/race/maplist.php"

    def fetch_map_url(map_name: str):
        """Fetch the full .pk3 URL for a given map name from maplist.php"""
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
        """Fetch all demo URLs for a given map from livesow.net"""
        try:
            r = requests.get(BASE_URL, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            links = []
            for a in soup.find_all("a", href=True):
                href = a['href']
                if href.endswith(".wdz20") and map_name in href:
                    links.append(BASE_URL + href)
            return links
        except requests.RequestException as e:
            print(f"Error fetching demo links: {e}")
            return []

    def download_file(url: str, out_path: str):
        """Download a file (map or demo) from url to out_path"""
        try:
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            with open(out_path, 'wb') as f:
                f.write(r.content)
            #print(f"Downloaded: {out_path}")
            return out_path
        except requests.RequestException as e:
            print(f"Error downloading {url}: {e}")
            return None

    def formatTime(millis: int):
        secs = millis // 1000
        mins = secs // 60
        secs = secs % 60

        return f"{mins:02d}:{secs:02d}"

    def check_demo_for_time(demo_path: str, target_time: str):
        """Returns (True, server_time) if demo contains target_time, otherwise (False, None)"""
        try:
            with gzip.open(demo_path, 'rb') as file:
                for server_time, rec_time, time_start in parseFinishTimes(file):
                    if rec_time == target_time:
                        return True, server_time
        except Exception as e:
            print(f"Error parsing demo {demo_path}: {e}")
            return False, None
        return False, None

    def recTimeToMillis(time: str):
        split = re.split(r"\.|:", time)
        return int(split[-1]) + int(split[-2]) * 1000 + int(split[-3]) * 1000 * 60

    finish_pattern = re.compile(r".*Race Finished.*Current: \^\d([\d:\.]*)")

    def parseFinishTimes(file):
        buf = io.BytesIO(file.read())
        server_time_start = -1
        while True:
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
                    formatTime(server_time_end), rec_time, formatTime(server_time_end - recTimeToMillis(rec_time)))

    def check_demo_for_time(demo_path: str, target_time: str):
        """Returns (True, server_time) if demo contains target_time, otherwise (False, None)"""
        try:
            with gzip.open(demo_path, 'rb') as file:
                for server_time, rec_time, time_start in parseFinishTimes(file):
                    if rec_time == target_time:
                        return True, time_start  # Return the calculated jump time, not server_time
        except Exception as e:
            print(f"Error parsing demo {demo_path}: {e}")
            return False, None
        return False, None

    # ---------------- MAIN LOGIC ----------------
    map_url = fetch_map_url(map_name)
    demo_links = fetch_demo_links(map_name)

    server_time = None
    found_demo_url = None

    if not demo_links:
        print(f"No demos found for map {map_name}")
        return map_url, None, None  # FIXED: Always return 3 values

    print(f"Found {len(demo_links)} demos for map {map_name}")

    for url in demo_links:
        demo_file = os.path.join(demos_dir, os.path.basename(url))
        downloaded_path = download_file(url, demo_file)

        if downloaded_path:
            found, server_time = check_demo_for_time(downloaded_path, target_time)
            if found:
                print(f"Found the demo with the target time. URL: {url}, Server time: {server_time}")
                found_demo_url = url
                os.remove(downloaded_path)
                break  # Exit the loop once a matching demo is found
            else:
                #print(f"Target time not found in this demo. Deleting: {downloaded_path}")
                os.remove(downloaded_path)

    if found_demo_url:
        print("All remaining demos have been processed and deleted.")
    else:
        print("No demo found with the specified target time.")

    return map_url, found_demo_url, server_time  # FIXED: Always return 3 values


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
        with open(output_path, "wb") as f:
            f.write(response.content)
        print("SQLite file downloaded successfully.")
    else:
        print(f"Failed to download file. Status code: {response.status_code}")

    new_db = "db.sqlite"
    old_db = "main_db.sqlite"

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

                    # Check if we've already processed this exact record
                    record_key = (player_id, map_id, time)
                    if record_key in processed_records:
                        print(f"Skipping duplicate record: {record_key}")
                        continue
                    processed_records.add(record_key)

                    # Skip records that were pushed down or are not actual improvements
                    if change_type == 'updated' and old_record:
                        old_version_id, old_player_id, old_map_id, old_time, old_version_rank, old_global_rank, _ = old_record

                        # If this is the same player/time but moved to a worse rank, skip it (was pushed down)
                        if (player_id == old_player_id and time == old_time and
                                ((record_type == 'global_2' and old_global_rank == 1) or
                                 (record_type == 'local_2' and old_version_rank == 1))):
                            print(
                                f"Skipping pushed-down record: {player_name} moved from rank {old_global_rank} to rank {global_rank}")
                            continue

                        # Skip if it's a worse time taking over a rank (shouldn't happen but just in case)
                        if time > old_time:
                            print(
                                f"Skipping worse time: {format_race_time(time)} vs previous {format_race_time(old_time)}")
                            continue

                        # Skip global_2 changes where the "new" record was actually pushed down from global_1
                        # Check if this player/time combination was the old global_1
                        if record_type == 'global_2':
                            # Look for this exact player/time in the old global_1 slot
                            old_global_1 = None
                            for old_change in map_changes:
                                if len(old_change) > 3 and old_change[1] == 'global_1':
                                    old_global_1_record = old_change[3]  # old record from global_1 change
                                    if (old_global_1_record[1] == player_id and  # same player
                                            old_global_1_record[3] == time):  # same time
                                        print(f"Skipping global_2 - this was the old global_1 that got pushed down")
                                        old_global_1 = True
                                        break
                            if old_global_1:
                                continue

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
                        script_dir = os.path.dirname(os.path.abspath(__file__))
                        DEMOS_DIR = os.path.join(script_dir, 'demos')

                        print(f"Starting search for map: {map_name} with time: {formatted_time}")

                        try:
                            result = find_demo_and_map_link(map_name, formatted_time, DEMOS_DIR)

                            if len(result) == 3:
                                map_link, demo_link, server_time = result
                            elif len(result) == 2:
                                map_link, demo_link = result
                                server_time = None
                            else:
                                map_link = demo_link = server_time = None

                            # If no demo is available, abort the whole cycle
                            if not demo_link:
                                missing_demo = True
                                break

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
            time.sleep((10))

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


@bot.command()
async def update(ctx):
    global last_embed_messages

    await ctx.send("🔄 Checking for updates...")
    try:
        record_updates = checkforupdates()
        embeds = create_records_embeds(record_updates)

        channel_id = ctx.channel.id

        if channel_id in last_embed_messages:
            try:
                # Try to edit the existing message with new embeds
                await last_embed_messages[channel_id].edit(embeds=embeds)
                await ctx.send("✅ Updated existing embed with new records!")
            except discord.NotFound:
                # Message was deleted, send a new one
                last_embed_messages[channel_id] = await ctx.send(embeds=embeds)
                await ctx.send("✅ Sent new embeds (previous message not found)!")
            except discord.HTTPException as e:
                # Some other error, send a new message
                await log_error(f"Error editing embed in channel {channel_id}", e)
                last_embed_messages[channel_id] = await ctx.send(embeds=embeds)
                await ctx.send("✅ Sent new embeds due to edit error!")
        else:
            # No previous message, send a new one
            last_embed_messages[channel_id] = await ctx.send(embeds=embeds)
            await ctx.send("✅ Sent new embeds!")

    except Exception as e:
        await ctx.send(f"❌ Error occurred: {e}")
        await log_error(f"Error in manual update command", e)


@tasks.loop(minutes=60)  # change 60 to however many minutes you want
async def auto_check():
    global last_embed_messages

    try:
        record_updates = checkforupdates()

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
                            print(f"✅ Updated existing embeds in {channel.name}")
                            successful_updates += 1
                        except discord.NotFound:
                            # Message was deleted, send a new one
                            last_embed_messages[channel_id] = await channel.send(embeds=embeds)
                            print(
                                f"✅ Sent new embeds in {channel.name} (previous message not found)")
                            successful_updates += 1
                        except discord.HTTPException as e:
                            # Some other error, send a new message
                            await log_error(f"Error editing message in {channel.name}", e)
                            last_embed_messages[channel_id] = await channel.send(embeds=embeds)
                            print(f"✅ Sent new embeds in {channel.name} due to edit error")
                            successful_updates += 1
                    else:
                        # No previous message, send a new one
                        last_embed_messages[channel_id] = await channel.send(embeds=embeds)
                        print(f"✅ Sent new embeds in {channel.name} (no previous message)")
                        successful_updates += 1

                except discord.Forbidden:
                    await log_error(f"No permission to send messages in {channel.name}")
                    failed_updates += 1
                except Exception as e:
                    await log_error(f"Unexpected error sending to {channel.name}", e)
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


# Add command to test console output (batched)
@bot.command()
async def test_console(ctx):
    """Test that console outputs are being batched and sent to error channel"""
    print("🧪 This is a test info message 1")
    print("✅ This is a test info message 2")
    print("ℹ️ This is a test info message 3")
    print("❌ This is a test error message with keyword 'error'")
    print("⚠️ Demo not available for testing - this should trigger error detection")
    print("🚨 Another error message")
    print("📊 Processing complete")
    await ctx.send("✅ Test messages sent! They will be batched and appear in error channel within ~5 seconds.")


# Add command to force send current batch
@bot.command()
async def flush_logs(ctx):
    """Force send any pending batched logs immediately"""
    global log_batch
    if log_batch:
        await send_batched_logs()
        await ctx.send(f"✅ Flushed {len(log_batch)} pending log messages to error channel.")
    else:
        await ctx.send("ℹ️ No pending log messages to flush.")


# Add command to check batch status
@bot.command()
async def log_status(ctx):
    """Check the current logging batch status"""
    global log_batch
    await ctx.send(f"📊 Current batch: {len(log_batch)} messages pending")


# Add command to test error logging (immediate)
@bot.command()
async def test_error(ctx):
    await log_error("🧪 Test Error", "This is a test error to verify immediate error logging is working.")
    await ctx.send("✅ Test error sent immediately to error log channel!")


# Add command to test demo not found scenario
@bot.command()
async def test_demo_missing(ctx):
    print("🎥 Demo not available yet; skipping this cycle without updating or posting.")
    print("❌ Failed to find demo for map test-map with time 00:12.345")
    print("⚠️ Retrying in next update cycle")
    await ctx.send("✅ Demo missing messages sent! Will be batched and sent to error channel.")


# Add command to add/remove channels
@bot.command()
@commands.has_permissions(administrator=True)
async def add_channel(ctx, channel_id: int):
    if channel_id not in RECORD_CHANNELS:
        RECORD_CHANNELS.append(channel_id)
        await ctx.send(f"✅ Added channel {channel_id} to record updates list.")
    else:
        await ctx.send(f"❌ Channel {channel_id} is already in the list.")


@bot.command()
@commands.has_permissions(administrator=True)
async def remove_channel(ctx, channel_id: int):
    if channel_id in RECORD_CHANNELS:
        RECORD_CHANNELS.remove(channel_id)
        if channel_id in last_embed_messages:
            del last_embed_messages[channel_id]
        await ctx.send(f"✅ Removed channel {channel_id} from record updates list.")
    else:
        await ctx.send(f"❌ Channel {channel_id} is not in the list.")


@bot.command()
async def list_channels(ctx):
    if RECORD_CHANNELS:
        channel_list = "📋 **Record Update Channels:**\n"
        for i, channel_id in enumerate(RECORD_CHANNELS, 1):
            channel = bot.get_channel(channel_id)
            if channel:
                channel_list += f"{i}. {channel.guild.name}#{channel.name} ({channel_id})\n"
            else:
                channel_list += f"{i}. Channel {channel_id} (not accessible)\n"
        await ctx.send(channel_list[:2000])
    else:
        await ctx.send("❌ No channels configured for record updates.")


with open("token.txt") as file:
    token = file.read()

bot.run(token)


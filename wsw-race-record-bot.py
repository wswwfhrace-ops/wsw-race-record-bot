import sqlite3
import os
import shutil
import requests
import subprocess
import re
from bs4 import BeautifulSoup
import gzip, sys, struct, io, re

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
                    server_time_end = serverTime - server_time_start - 1000
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
                print(f"Target time not found in this demo. Deleting: {downloaded_path}")
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

def row_key(row):
    version_id, player_id, map_id, time, version_rank, global_rank = row
    # identify a record uniquely by version, player, map, and time
    return (version_id, player_id, map_id, time)


def checkforupdates():
    changes = []

    response = requests.get(url)
    if response.status_code == 200:
        with open(output_path, "wb") as f:
            f.write(response.content)
        print("SQLite file downloaded successfully.")
    else:
        print(f"Failed to download file. Status code: {response.status_code}")

    # new_db = "unaltered - Copy.sqlite"
    new_db = "db.sqlite"
    old_db = "main_db.sqlite"

    # connecting to the database
    cnew = sqlite3.connect(new_db)
    cmain = sqlite3.connect(old_db)
    # cursor object
    crsrnew = cnew.cursor()
    crsrmain = cmain.cursor()

    # Modified filtering logic: keep global 1st, global 2nd, local 1st, local 2nd
    crsrnew.execute("""
        SELECT id FROM race
        WHERE 
            (version_id != 1 AND global_rank <= 2)
    """)
    cnew.commit()
    To_keep = crsrnew.fetchall()

    crsrnew.execute("""
        SELECT id FROM race
        WHERE
            (version_id = 1 AND version_rank <= 2)
    """)
    cnew.commit()
    To_keep += crsrnew.fetchall()

    # Step 2: Extract only the IDs into a flat list
    ids_to_keep = {row[0] for row in To_keep}

    # Step 3: Delete everything NOT in ids_to_keep
    crsrnew.execute("SELECT id FROM race")
    cnew.commit()
    all_ids = {row[0] for row in crsrnew.fetchall()}

    ids_to_delete = [(i,) for i in all_ids - ids_to_keep]  # List of tuples

    # Step 4: Execute deletions
    crsrnew.executemany("DELETE FROM race WHERE id = ?", ids_to_delete)
    cnew.commit()

    crsrnew.execute("""
        SELECT * FROM race
        ORDER BY map_id, global_rank, version_rank
    """)
    cnew.commit()

    crsrnew.execute("Select COUNT (*) FROM map")
    cnew.commit()
    maptotal = crsrnew.fetchone()[0]

    # delete and sort by map_id and version_rank
    versionrank = 1
    map_index = 1
    listrow = []
    seen_combinations = set()  # Track (player_id, map_id, version_id) combinations

    while map_index <= maptotal:

        # Get global 1st and 2nd
        crsrnew.execute(
            "Select * From race WHERE map_id = ? AND version_id != 1 AND global_rank <= 2 ORDER BY global_rank",
            (map_index,))
        cnew.commit()
        newrows = crsrnew.fetchall()
        for row in newrows:
            combination = (row[2], row[3], row[1])  # (player_id, map_id, version_id)
            if combination not in seen_combinations:
                listrow.append(row)
                seen_combinations.add(combination)

        # Get local 1st and 2nd
        crsrnew.execute(
            "Select * From race WHERE map_id = ? AND version_rank <= 2 AND version_id = 1 ORDER BY version_rank",
            (map_index,))
        cnew.commit()
        newrows = crsrnew.fetchall()
        for row in newrows:
            combination = (row[2], row[3], row[1])  # (player_id, map_id, version_id)
            if combination not in seen_combinations:
                listrow.append(row)
                seen_combinations.add(combination)

        map_index = map_index + 1

    updated_rows = []
    for index, row in enumerate(listrow):
        row_list = list(row)  # convert tuple to list
        row_list[0] = index + 1  # reset ID to start from 1
        updated_rows.append(tuple(row_list))  # convert back to tuple

    crsrnew.execute("DELETE From race")
    cnew.commit()

    crsrnew.executemany("INSERT INTO race VALUES (?,?,?,?,?,?,?)", updated_rows)
    cnew.commit()

    crsrnew.execute("Select COUNT (*) FROM race")
    cnew.commit()
    newtotal = crsrnew.fetchone()[0]

    crsrmain.execute("Select COUNT (*) FROM race")
    cmain.commit()
    maintotal = crsrmain.fetchone()[0]

    crsrmain.execute("Select * From race")
    crsrnew.execute("Select * From race")

    cmain.commit()
    cnew.commit()

    newrows = crsrnew.fetchall()
    mainrows = crsrmain.fetchall()

    map_index = 1

    from collections import defaultdict

    map_index = 1

    def get_reference_records(map_id, cursor, connection):
        """Get global and local reference records for comparison"""
        # Get global 1st and 2nd
        cursor.execute("""
            SELECT version_id, player_id, time, version_rank, global_rank
            FROM race
            WHERE map_id = ? AND global_rank <= 2
            ORDER BY global_rank
        """, (map_id,))
        connection.commit()
        global_records = cursor.fetchall()

        global_1st = global_records[0] if len(global_records) > 0 else None
        global_2nd = global_records[1] if len(global_records) > 1 else None

        # Get local 1st and 2nd (version_id = 1)
        cursor.execute("""
            SELECT version_id, player_id, time, version_rank, global_rank
            FROM race
            WHERE map_id = ? AND version_id = 1 AND version_rank <= 2
            ORDER BY version_rank
        """, (map_id,))
        connection.commit()
        local_records = cursor.fetchall()

        local_1st = local_records[0] if len(local_records) > 0 else None
        local_2nd = local_records[1] if len(local_records) > 1 else None

        return global_1st, global_2nd, local_1st, local_2nd

    def format_record_info(cursor, player_id, map_id, time):
        """Format player name, map name, and time"""
        cursor.execute("SELECT simplified FROM player WHERE id = ?", (player_id,))
        player_name = cursor.fetchone()
        player_name = player_name[0] if player_name else f"(ID {player_id})"

        cursor.execute("SELECT name FROM map WHERE id = ?", (map_id,))
        map_name = cursor.fetchone()
        map_name = map_name[0] if map_name else f"(ID {map_id})"

        formatted_time = format_race_time(time)

        return player_name, map_name, formatted_time

    # Store record updates for the embed
    record_updates = []

    # NEW: if we ever fail to find a demo for a new record, abort this cycle
    missing_demo = False

    while map_index <= maptotal:
        crsrnew.execute("""
            SELECT version_id, player_id, map_id, time, version_rank, global_rank
            FROM race
            WHERE map_id = ?
            ORDER BY global_rank, version_rank, player_id
        """, (map_index,))
        cnew.commit()
        newrows = crsrnew.fetchall()

        crsrmain.execute("""
            SELECT version_id, player_id, map_id, time, version_rank, global_rank
            FROM race
            WHERE map_id = ?
            ORDER BY global_rank, version_rank, player_id
        """, (map_index,))
        cmain.commit()
        mainrows = crsrmain.fetchall()

        if mainrows != newrows:
            print(f"\nChanges detected in map {map_index}:")

            old_keys = {row_key(r) for r in mainrows}
            new_keys = {row_key(r) for r in newrows}

            # Find truly new records (not just re-ranked ones)
            added = [r for r in newrows if row_key(r) not in old_keys]

            # Get reference records for output
            global_1st, global_2nd, local_1st, local_2nd = get_reference_records(map_index, crsrnew, cnew)

            # Process each new record
            for row in added:
                if missing_demo:
                    break  # already decided to abort this cycle

                version_id, player_id, map_id, time, version_rank, global_rank = row

                # Check if this time already existed in the old list for same map/version
                time_already_existed = any(
                    r[2] == map_id and r[3] == time and r[0] == version_id
                    for r in mainrows
                )

                player_name, map_name, formatted_time = format_record_info(crsrnew, player_id, map_id, time)

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

                # Determine what record was achieved and gather reference times
                if global_rank == 1:
                    record_update['type'] = 'NEW GLOBAL 1ST'
                    if global_2nd:
                        g2_player, g2_map, g2_time = format_record_info(crsrnew, global_2nd[1], map_id, global_2nd[2])
                        crsrnew.execute("SELECT name FROM version WHERE id = ?", (global_2nd[0],))
                        g2_version = crsrnew.fetchone()
                        g2_version = g2_version[0] if g2_version else f"Version {global_2nd[0]}"
                        record_update['global_2nd'] = f"{g2_time} by {g2_player} in {g2_version}"

                elif global_rank == 2:
                    record_update['type'] = 'NEW GLOBAL 2ND'
                    if global_1st:
                        g1_player, g1_map, g1_time = format_record_info(crsrnew, global_1st[1], map_id, global_1st[2])
                        crsrnew.execute("SELECT name FROM version WHERE id = ?", (global_1st[0],))
                        g1_version = crsrnew.fetchone()
                        g1_version = g1_version[0] if g1_version else f"Version {global_1st[0]}"
                        record_update['global_1st'] = f"{g1_time} by {g1_player} in {g1_version}"

                elif version_rank == 1 and version_id == 1:
                    if global_rank != 2:
                        record_update['type'] = 'NEW LOCAL 1ST'
                        if global_1st:
                            g1_player, g1_map, g1_time = format_record_info(crsrnew, global_1st[1], map_id,
                                                                            global_1st[2])
                            crsrnew.execute("SELECT name FROM version WHERE id = ?", (global_1st[0],))
                            g1_version = crsrnew.fetchone()
                            g1_version = g1_version[0] if g1_version else f"Version {global_1st[0]}"
                            record_update['global_1st'] = f"{g1_time} by {g1_player} in {g1_version}"

                elif version_rank == 2 and version_id == 1:
                    record_update['type'] = 'NEW LOCAL 2ND'
                    if global_1st:
                        g1_player, g1_map, g1_time = format_record_info(crsrnew, global_1st[1], map_id, global_1st[2])
                        crsrnew.execute("SELECT name FROM version WHERE id = ?", (global_1st[0],))
                        g1_version = crsrnew.fetchone()
                        g1_version = g1_version[0] if g1_version else f"Version {global_1st[0]}"
                        record_update['global_1st'] = f"{g1_time} by {g1_player} in {g1_version}"

                    # Only show local 1st if it's different from global 1st
                    if local_1st and global_1st and (local_1st[1] != global_1st[1] or local_1st[2] != global_1st[2]):
                        l1_player, l1_map, l1_time = format_record_info(crsrnew, local_1st[1], map_id, local_1st[2])
                        record_update['local_1st'] = f"{l1_time} by {l1_player}"

                # Get demo and map links
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

                    # If no demo is available for this new record, abort the whole cycle now.
                    if not demo_link:
                        missing_demo = True
                        break

                    record_update['map_link'] = map_link
                    record_update['demo_link'] = demo_link
                    record_update['demo_jump'] = server_time

                except Exception as e:
                    # Treat any error during demo retrieval as "demo not yet available"
                    missing_demo = True
                    break

                if record_update['type']:  # Only add if we have a valid record type
                    record_updates.append(record_update)

        if missing_demo:
            break  # stop processing further maps

        map_index += 1

    # If any new record lacked a demo, skip the entire cycle: no DB replacement, no output.
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

    # insert record into main
    # reset main - keep global 1st, 2nd and local 1st, 2nd
    map_index = 1
    listrow = []
    seen_combinations = set()  # Track (player_id, map_id, version_id) combinations

    while map_index <= maptotal:
        # Get global 1st and 2nd
        crsrnew.execute("Select * From race WHERE map_id = ? AND global_rank <= 2 ORDER BY global_rank", (map_index,))
        cnew.commit()
        newrows = crsrnew.fetchall()
        for row in newrows:
            combination = (row[2], row[3], row[1])  # (player_id, map_id, version_id)
            if combination not in seen_combinations:
                listrow.append(row)
                seen_combinations.add(combination)

        # Get local 1st and 2nd
        crsrnew.execute(
            "Select * From race WHERE map_id = ? AND version_rank <= 2 AND version_id = 1 ORDER BY version_rank",
            (map_index,))
        cnew.commit()
        newrows = crsrnew.fetchall()
        for row in newrows:
            combination = (row[2], row[3], row[1])  # (player_id, map_id, version_id)
            if combination not in seen_combinations:
                listrow.append(row)
                seen_combinations.add(combination)

        map_index = map_index + 1

    updated_rows = []
    for index, row in enumerate(listrow):
        row_list = list(row)  # convert tuple to list
        row_list[0] = index + 1  # reset ID to start from 1
        updated_rows.append(tuple(row_list))  # convert back to tuple

    crsrnew.execute("DELETE From race")
    cnew.commit()

    crsrnew.executemany("INSERT INTO race VALUES (?,?,?,?,?,?,?)", updated_rows)
    cnew.commit()

    crsrmain.close()
    cmain.close()
    crsrnew.close()
    cnew.close()

    if os.path.exists(old_db):
        os.remove(old_db)
        print("Deleted old database.")

    shutil.move(new_db, old_db)
    print("test.sqlite has replaced main.sqlite.")

    return record_updates



import discord
from discord.ext import commands, tasks

bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

# Store the last embed message for editing
last_embed_message = None


def create_records_embed(record_updates):
    """Create a comprehensive embed with all record updates"""
    embed = discord.Embed(
        title="🏁 Warsow Race Records Update",
        color=0x00ff00,
        timestamp=discord.utils.utcnow()
    )

    if not record_updates:
        embed.description = "No new records found."
        return embed

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

    # Add fields for each category
    if global_1st:
        field_text = ""
        for record in global_1st[:3]:  # Limit to 3 to avoid embed limits
            field_text += format_record_text(record) + "\n"
        if len(global_1st) > 3:
            field_text += f"... and {len(global_1st) - 3} more"
        embed.add_field(name="🏆 New World Record", value=field_text[:1024], inline=False)

    if global_2nd:
        field_text = ""
        for record in global_2nd[:3]:
            field_text += format_record_text(record) + "\n"
        if len(global_2nd) > 3:
            field_text += f"... and {len(global_2nd) - 3} more"
        embed.add_field(name="🥈 New Second Place", value=field_text[:1024], inline=False)

    if local_1st:
        field_text = ""
        for record in local_1st[:3]:
            field_text += format_record_text(record) + "\n"
        if len(local_1st) > 3:
            field_text += f"... and {len(local_1st) - 3} more"
        embed.add_field(name="🏠 New WSW 2.1 World Record", value=field_text[:1024], inline=False)

    if local_2nd:
        field_text = ""
        for record in local_2nd[:3]:
            field_text += format_record_text(record) + "\n"
        if len(local_2nd) > 3:
            field_text += f"... and {len(local_2nd) - 3} more"
        embed.add_field(name="🏡 New WSW 2.1 Second Place", value=field_text[:1024], inline=False)

    # Add summary
    total_records = len(record_updates)
    embed.set_footer(text=f"Total new records: {total_records}")

    return embed


@bot.event
async def on_ready():
    print("Bot ready")
    auto_check.start()  # start the background loop when the bot is ready


@bot.command()
async def update(ctx):
    global last_embed_message

    await ctx.send("Checking for updates...")
    try:
        record_updates = checkforupdates()
        embed = create_records_embed(record_updates)

        if last_embed_message:
            try:
                # Try to edit the existing message
                await last_embed_message.edit(embed=embed)
                await ctx.send(" Updated existing embed with new records!")
            except discord.NotFound:
                # Message was deleted, send a new one
                last_embed_message = await ctx.send(embed=embed)
            except discord.HTTPException:
                # Some other error, send a new message
                last_embed_message = await ctx.send(embed=embed)
        else:
            # No previous message, send a new one
            last_embed_message = await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f" Error occurred: {e}")


@tasks.loop(minutes=60)  # change 60 to however many minutes you want
async def auto_check():
    global last_embed_message

    channel_id = 1387767813325721661  # <-- replace with your Discord channel ID
    channel = bot.get_channel(channel_id)

    if channel is None:
        print(" Channel not found, check the channel ID")
        return

    try:
        record_updates = checkforupdates()

        # Only send/update if there are actual updates
        if record_updates:
            embed = create_records_embed(record_updates)

            if last_embed_message:
                try:
                    # Try to edit the existing message
                    await last_embed_message.edit(embed=embed)
                    print("Updated existing embed with new records")
                except discord.NotFound:
                    # Message was deleted, send a new one
                    last_embed_message = await channel.send(embed=embed)
                    print(" Sent new embed (previous message not found)")
                except discord.HTTPException as e:
                    # Some other error, send a new message
                    print(f" Error editing message: {e}")
                    last_embed_message = await channel.send(embed=embed)
                    print(" Sent new embed due to edit error")
            else:
                # No previous message, send a new one
                last_embed_message = await channel.send(embed=embed)
                print(" Sent new embed (no previous message)")
        else:
            print(" No new records found")

    except Exception as e:
        print(f"Error in auto_check: {e}")


# Add command to clear the stored message reference
@bot.command()
async def clear_embed(ctx):
    global last_embed_message
    last_embed_message = None
    await ctx.send("✅ Cleared embed message reference. Next update will create a new embed.")


# Add command to get embed info
@bot.command()
async def embed_info(ctx):
    global last_embed_message
    if last_embed_message:
        await ctx.send(
            f"📋 Current embed message ID: {last_embed_message.id} in channel {last_embed_message.channel.mention}")
    else:
        await ctx.send("❌ No embed message currently tracked.")


with open("token.txt") as file:
    token = file.read()

bot.run(token)

import pyewf # To open E01 files
import pytsk3 # To inspect those opened E01 files
import os
import sqlite3
from datetime import datetime
import tempfile
import shutil
import sys
import csv
import json
import re
import hashlib

def setup_logging(image_name):
    """
    Setup logging configuration for error tracking. This config will be used by the logs from now on.
    
    Args:
        image_name: Name of the E01 image being processed
    
    Returns:
        logger: Configured logging object
    """
    import logging
    from datetime import datetime
    
    # Create logs directory if it doesn't exist
    try:
        os.makedirs('logs')
    except FileExistsError:
        print("logs folder already exists")
    # Create log filename with timestamp and image name
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f'logs/{image_name}_{timestamp}_errors.log'
    
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()  # Also print to console
        ]
    )
    
    return logging.getLogger(__name__)

def parse_input_mode():
    """
    Ask the user what type of source to analyze.

    Returns:
        str: 'ewf', 'raw', or 'live'
    """
    print("\nSelect input source:")
    print("1. EWF image (.E01)")
    print("2. Raw image (.dd / .raw / .img)")
    print("3. Live system")

    choice = input("\nEnter your choice (1-3): ").strip()

    mode_map = {
        '1': 'ewf',
        'ewf': 'ewf',
        '2': 'raw',
        'raw': 'raw',
        'dd': 'raw',
        '3': 'live',
        'live': 'live',
    }

    mode = mode_map.get(choice.lower())
    if not mode:
        print("Invalid choice. Defaulting to EWF.")
        mode = 'ewf'

    return mode

def process_live_system(selected_browser, logger):
    """
    Extract browser history directly from the live running system.

    Returns:
        list: All collected browser history entries
    """
    all_history = []

    users_root = os.path.join(os.environ.get('SystemDrive', 'C:'), '\\Users')
    
    system_users = {"Default", "Default User", "All Users", "Public"}
    
    # Filter to selected browser if specified
    if selected_browser:
        selected_browser = selected_browser.capitalize()

    for username in os.listdir(users_root):
        user_path = os.path.join(users_root, username)
        if not os.path.isdir(user_path) or username in system_users:
            continue
        
        logger.info(f"Searching browser history for user: {username}")
        
        localappdata = os.path.join(user_path, 'AppData', 'Local')
        appdata      = os.path.join(user_path, 'AppData', 'Roaming')
        
        browser_paths = {
            'Chrome':  os.path.join(localappdata, 'Google', 'Chrome', 'User Data'),
            'Edge':    os.path.join(localappdata, 'Microsoft', 'Edge', 'User Data'),
            'Firefox': os.path.join(appdata, 'Mozilla', 'Firefox', 'Profiles'),
        }
        
        if selected_browser:
            browser_paths = {k: v for k, v in browser_paths.items() if k == selected_browser}

        for browser, base_path in browser_paths.items():
            if not os.path.exists(base_path):
                logger.debug(f"{browser} not found at {base_path}")
                continue

            logger.info(f"Found {browser} at {base_path}")

            try:
                for profile_name in os.listdir(base_path):
                    profile_path = os.path.join(base_path, profile_name)

                    # Only process actual profile directories
                    if not is_valid_profile(browser, profile_name):
                        continue

                    main_name = get_history_filename(browser)
                    db_path = os.path.join(profile_path, main_name)

                    if not os.path.exists(db_path):
                        continue

                    logger.info(f"Found {browser} history in profile {profile_name}")
                    history_entries = extract_and_analyze_history({'main': db_path}, browser, profile_name)
                    if history_entries:
                        logger.info(f"Successfully processed {browser} profile {profile_name}")
                        all_history.extend(history_entries)

            except Exception as e:
                logger.error(f"Error processing {browser}: {str(e)}")

    return all_history

def extract_ewf_hashes(filenames, logger):
    """Extract embedded MD5/SHA1 from EWF binary sections."""
    if not filenames:
        return None, None
    
    last_segment = sorted(filenames)[-1]
    try:
        with open(last_segment, 'rb') as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 20 * 1024 * 1024))
            data = f.read()
    except Exception as e:
        logger.error(f"Could not read last segment: {e}")
        return None, None

    md5 = None
    sha1 = None

    pos = data.find(b'digest\x00')
    if pos != -1:
        section_data = data[pos + 64:].lstrip(b'\x00')
        md5  = section_data[4:20].hex()
        sha1 = section_data[20:40].hex()
        logger.info(f"Embedded MD5:  {md5}")
        logger.info(f"Embedded SHA1: {sha1}")
    elif data.find(b'hash\x00') != -1:
        pos = data.find(b'hash\x00')
        section_data = data[pos + 64:].lstrip(b'\x00')
        md5 = section_data[4:20].hex()
        logger.info(f"Embedded MD5 (hash section only): {md5}")
    else:
        logger.warning("No embedded hashes found in image.")

    return md5, sha1

def compute_hash_by_algorithm(ewf_handle, algorithm, logger):
    """Compute hash of raw EWF data using the specified algorithm."""
    logger.info(f"Computing {algorithm.upper()} hash for verification...")
    h = hashlib.new(algorithm)
    chunk_size = 1024 * 1024
    offset = 0
    total_size = ewf_handle.get_media_size()
    ewf_handle.seek(0)

    while offset < total_size:
        data = ewf_handle.read(chunk_size)
        if not data:
            break
        h.update(data)
        offset += len(data)
        print(f"\r[HASHING] {(offset/total_size)*100:.1f}% complete", end="")

    result = h.hexdigest()
    print(f"\n[+] Computed {algorithm.upper()}: {result}")
    return result

def detect_algorithm(hash_string):
    """Detect hash algorithm from hex string length."""
    length_map = {32: 'md5', 40: 'sha1', 56: 'sha224', 64: 'sha256'}
    return length_map.get(len(hash_string.strip()), None)
    
class EwfImgInfo(pytsk3.Img_Info): 
    """
    pyewf reads Ewfs, but ptsk3 needs image that has read(), close(), get_size() method.

    """
    def __init__(self, ewf_handle):
        # Initialize the EWF image info object.
        self._ewf_handle = ewf_handle
        # With this type, pytsk3 will use our read, get_size, close
        super().__init__(url="", type=pytsk3.TSK_IMG_TYPE_EXTERNAL) # TSK_IMG_TYPE_EXTERNAL because it's a EWF file and not a traditional disk image (TSK_IMG_TYPE_RAW)

    def close(self):
        # Close the EWF handle.
        self._ewf_handle.close()

    def read(self, offset, size):
        # Read a specific amount of data from the EWF image.
        self._ewf_handle.seek(offset)
        return self._ewf_handle.read(size)

    def get_size(self):
        # Return the size of the EWF image.
        return self._ewf_handle.get_media_size()


class RawSegmentImgInfo(pytsk3.Img_Info):
    """
    Stitches multiple raw segments together so pytsk3 sees one continuous disk.
    Same pattern as EwfImgInfo but reads from ordered segment files.
    """
    def __init__(self, segments):
        self._segments = segments
        self._sizes = [os.path.getsize(s) for s in segments]
        self._total_size = sum(self._sizes)
        self._handles = [open(s, 'rb') for s in segments]
        super().__init__(url="", type=pytsk3.TSK_IMG_TYPE_EXTERNAL)

    def close(self):
        for f in self._handles:
            f.close()

    def get_size(self):
        return self._total_size

    def read(self, offset, size):
        result = b""
        remaining = size

        # Find which segment offset falls in
        seg_start = 0
        for i, seg_size in enumerate(self._sizes):
            if offset < seg_start + seg_size:
                # Read from this segment
                local_offset = offset - seg_start
                self._handles[i].seek(local_offset)
                can_read = min(remaining, seg_size - local_offset)
                result += self._handles[i].read(can_read)
                remaining -= can_read
                offset += can_read

                # Continue into next segments if needed
                for j in range(i + 1, len(self._segments)):
                    if remaining <= 0:
                        break
                    can_read = min(remaining, self._sizes[j])
                    self._handles[j].seek(0)
                    result += self._handles[j].read(can_read)
                    remaining -= can_read
                    offset += can_read
                break
            seg_start += seg_size

        return result
    

def get_partition_offset(img_info, logger):
    """
    Get partition offset either automatically for basic data partition where all the user files are or through user input.
    
    Args:
        img_info: The disk image info object
        logger: Logger object for error tracking
    
    Returns:
        Partition offset in bytes and volume info, or None, None if user quits
    """
    # Sometimes, a suspect might delete the partition to try and 
    # hide their data. The files are still there, but the "Sign Out Front"
    # is gone. In those cases, searching common starting points (like sector 2048) or manual carving
    # can find the lost files.
    def show_common_offsets():
        """Helper function to handle common offset selection"""
        while True:
            logger.info("\nCommon offsets:")
            logger.info("1. 0 bytes")
            logger.info("2. 1048576 bytes (512 * 2048)")
            logger.info("3. 65536 bytes (512 * 128)")
            logger.info("4. 122683392 bytes (512 * 239616)")
            logger.info("b. Back to main menu")
            logger.info("q. Quit")
            
            subchoice = input("\nEnter your choice: ").lower()
            if subchoice == 'q':
                return None
            elif subchoice == 'b':
                return 'back'
            elif subchoice in ['1', '2', '3', '4']:
                offsets = {
                    '1': 0,
                    '2': 512 * 2048,
                    '3': 512 * 128,
                    '4': 512 * 239616
                }
                offset = offsets[subchoice]
                logger.info(f"Using predefined offset: {offset}")
                return offset
            else:
                logger.error("Invalid offset choice. Try again")

    def get_manual_offset():
        """Helper function to handle manual offset input.
        In case user suspects there's data somewhere else """
        try:
            offset = int(input("Enter offset in bytes: "))
            logger.info(f"Using manual offset: {offset}")
            return offset
        except ValueError:
            logger.error("Invalid offset value entered")
            return 'retry'

    try:
        auto_offset, volume_info = find_windows_partition(img_info, logger)
        
        while True:
            logger.info("\nPartition offset options:")
            
            logger.info("1. Enter offset manually")
            logger.info("2. Try common offsets")
            
            if auto_offset:
                logger.info(f"3. Use detected offset ({auto_offset} bytes)")
            else:
                logger.info("Couldn't get the offset for basic data partition")
            
            logger.info("q. Quit")
            
            choice = str(input("\nEnter your choice: ")).lower()
            
            match choice:
                case 'q':
                    return None, None
                case '1':
                    result = get_manual_offset()
                    if result != 'retry':
                        return result, volume_info
                case '2':
                    result = show_common_offsets()
                    if result == 'back':
                        continue
                    if result is None:
                        return None, None # User hit 'q' inside the sub-menu
                    return result, volume_info # User picked a common offset
                case '3' if auto_offset:
                    logger.info(f"Using automatically detected offset: {auto_offset}")
                    return auto_offset, volume_info                   
                case _:
                    logger.error("Invalid choice")
                    
    except Exception as e:
        logger.error(f"Error in partition offset selection: {str(e)}")
        return None, None
    
def find_windows_partition(img_info, logger):
    """
    Find the offset of the NTFS partition in the disk image among other partitions in the partition table
    
    Args:
        img_info: The disk image info object
        logger: Logger object for error tracking
    
    Returns:
        int: Offset to the NTFS partition, or None if not found
    """
    try:
        volume_info = pytsk3.Volume_Info(img_info) # Partition table
        sector_size = 512
        found_partitions = [] # List to hold all basic data partitions/ntfs
        
        logger.info("\nDetected Partitions:")
        for partition in volume_info:
            desc = partition.desc.decode('utf-8').lower() # .desc -> description  of the parition by parition table (b'Basic Data Partition') and change it to English
            logger.info(f"Addr: {partition.addr}, Start: {partition.start}, Desc: {partition.desc.decode('utf-8')}")
            
            # Look for Windows partition indicators
            if any(x in desc for x in ['ntfs', 'basic data partition', 'windows']):
                offset = partition.start * sector_size
                logger.info(f"\nFound Windows partition at sector {partition.start}")
                logger.info(f"Using offset: {offset} bytes")
                found_partitions.append(offset)
        
        if not found_partitions:
            logger.warning("No Windows partitions found automatically.")
            return None, volume_info

        if len(found_partitions) == 1:
            # Only one found
            return found_partitions[0], volume_info
        else:
            # Multiple found! Let the user pick.
            logger.info(f"\n[!] Detected {len(found_partitions)} potential data partitions.")
            for i, off in enumerate(found_partitions):
                print(f"{i+1}. Offset: {off} bytes")
            
            choice = input("\nSelect partition number to analyze: ")
            try:
                idx = int(choice) - 1
                return found_partitions[idx], volume_info
            except (ValueError, IndexError):
                logger.error("Invalid selection. Returning first detected partition.")
                return found_partitions[0], volume_info
            
    except Exception as e:
        logger.error(f"Error detecting partitions: {e}")
        # Print all partition information for debugging
        try:
            volume_info = pytsk3.Volume_Info(img_info)
            logger.debug("\nDetailed Partition information:")
            for partition in volume_info:
                logger.debug(f"Partition {partition.addr}:")
                logger.debug(f"  Start: {partition.start}")
                logger.debug(f"  Length: {partition.len}")
                logger.debug(f"  Description: {partition.desc.decode('utf-8')}")
        except Exception as e2:
            logger.error(f"Error getting detailed partition info: {e2}")
        return None, None

def get_history_filename(browser_type):
    return "places.sqlite" if browser_type == 'Firefox' else "History"

def is_valid_profile(browser, profile_name):
    if browser == 'Firefox':
        return '.' in profile_name
    return profile_name == 'Default' or profile_name.startswith('Profile ')

def find_browser_files(fs_info, username, logger, selected_browser=None):
    """
    Search for browser history files for a specific user in a disk image.

    Returns:
        dict: {browser: {profile_name: {'main': file, 'wal': file}}}
    """
    found_files = {}
    
    browser_paths = {
        'Chrome': f"Users/{username}/AppData/Local/Google/Chrome/User Data",
        'Edge':   f"Users/{username}/AppData/Local/Microsoft/Edge/User Data",
        'Firefox': f"Users/{username}/AppData/Roaming/Mozilla/Firefox/Profiles"
    }

    installed_browsers = {}
    for browser, path in browser_paths.items():
        try:
            fs_info.open_dir(path)
            installed_browsers[browser] = path
            logger.info(f"Found {browser} installation for user {username}")
        except Exception as e:
            logger.debug(f"Browser {browser} not found: {e}")
    
    if not installed_browsers:
        logger.warning(f"No supported browsers found for user {username}")
        return found_files

    if selected_browser:
        selected_browser = selected_browser.capitalize()
        if selected_browser not in installed_browsers:
            logger.warning(f"{selected_browser} is not installed for user {username}")
            return found_files
        installed_browsers = {selected_browser: installed_browsers[selected_browser]}
    
    for browser, base_path in installed_browsers.items():
        found_files[browser] = {} 
        try:
            profiles_dir = fs_info.open_dir(base_path)
            for profile in profiles_dir:
                profile_name = profile.info.name.name.decode('utf-8')
                if profile_name in [".", ".."]:
                    continue

                # Only process actual browser profile directories
                if not is_valid_profile(browser, profile_name):
                    continue

                main_name = get_history_filename(browser)
                history_path = f"{base_path}/{profile_name}/{main_name}"
                wal_path = f"{history_path}-wal"
            
                try:
                    file = fs_info.open(history_path)
                    found_files[browser][profile_name] = {'main': file}
                    logger.info(f"Found {browser} history in profile {profile_name}")

                    try:
                        wal_file = fs_info.open(wal_path)
                        found_files[browser][profile_name]['wal'] = wal_file
                        logger.info(f"Found WAL for {browser} profile {profile_name}")
                    except Exception:
                        pass
                except Exception as e:
                    logger.debug(f"Error accessing history in profile {profile_name}: {e}")
            
        except Exception as e:
            logger.error(f"Error accessing {browser} profiles directory: {str(e)}")
            
    return found_files

def extract_and_analyze_history(files_dict, browser_type, profile_name):
    temp_dir = tempfile.mkdtemp()
    try:
        main_filename = get_history_filename(browser_type)
        temp_main_db = os.path.join(temp_dir, main_filename)

        # files_dict['main'] can be either a pytsk3 file or a live path string
        if isinstance(files_dict['main'], str):
            shutil.copy2(files_dict['main'], temp_main_db)
            wal_src = files_dict['main'] + "-wal"
            if os.path.exists(wal_src):
                shutil.copy2(wal_src, f"{temp_main_db}-wal")
        else:
            fs_main = files_dict['main']
            with open(temp_main_db, 'wb') as f:
                f.write(fs_main.read_random(0, fs_main.info.meta.size))
            if 'wal' in files_dict:
                fs_wal = files_dict['wal']
                with open(f"{temp_main_db}-wal", 'wb') as f:
                    f.write(fs_wal.read_random(0, fs_wal.info.meta.size))

        return parse_history_db(temp_main_db, browser_type, profile_name)
    except Exception as e:
        print(f"Error processing {browser_type} history: {str(e)}")
        return []
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def parse_history_db(db_path, browser_type, profile_name):
    """
    Parse a local SQLite history database and return formatted entries.
    Shared by both image and live modes.

    Returns:
        list: History entries
    """
    history_entries = []

    if browser_type in ['Chrome', 'Edge']:
        results = extract_chromium_history(db_path)
    else:
        results = extract_firefox_history(db_path)

    print(f"\n{browser_type} History from profile {profile_name}:")

    for url, title, timestamp in results:
        try:
            if browser_type in ['Chrome', 'Edge']:
                timestamp = datetime.fromtimestamp((timestamp / 1000000) - 11644473600)
            else:
                timestamp = datetime.fromtimestamp(timestamp / 1000000)
        except (OSError, ValueError, OverflowError):
            timestamp = datetime(1970, 1, 1)

        entry = {
            'browser': browser_type,
            'profile': profile_name,
            'url': url,
            'title': title,
            'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }
        history_entries.append(entry)

        print(f"URL: {url}")
        print(f"Title: {title}")
        print(f"Profile: {profile_name}")
        print(f"Visited: {timestamp}")
        print("-" * 50)

    return history_entries

def extract_chromium_history(db_path):
    """
    Extract URLs from Chrome/Edge history.

    Args:
        db_path: The path to the database file.

    Returns:
        list: A list of tuples containing URLs, titles, and last visit times.
    """
    try:
        conn = sqlite3.connect(db_path, timeout=10)  # Add timeout
        conn.execute("PRAGMA journal_mode=WAL")  # Use Write-Ahead Log mode
        cursor = conn.cursor()
        
        query = """
        SELECT url, title, last_visit_time 
        FROM urls 
        WHERE last_visit_time IS NOT NULL
        ORDER BY last_visit_time DESC
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()
        return results
    except sqlite3.OperationalError as e:
        if "locked" in str(e):
            print(f"Database is locked: {e}")
        else:
            print(f"SQLite error: {e}")
        return []

def extract_firefox_history(db_path):
    """
    Extract URLs from Firefox history.

    Args:
        db_path: The path to the database file.

    Returns:
        list: A list of tuples containing URLs, titles, and last visit dates.
    """
    try:
        conn = sqlite3.connect(db_path, timeout=10)  # Add timeout
        conn.execute("PRAGMA journal_mode=WAL")  # Use WAL mode
        cursor = conn.cursor()

        query = """
        SELECT url, title, last_visit_date
        FROM moz_places 
        WHERE last_visit_date IS NOT NULL
        ORDER BY last_visit_date DESC
        """

        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()
        return results
    except sqlite3.OperationalError as e:
        if "locked" in str(e):
            print(f"Database is locked: {e}")
        else:
            print(f"SQLite error: {e}")
        return []

def export_history(history_data, output_dir, selected_browser, image_name):
    """
    Export browser history to CSV and JSON formats.

    Args:
        history_data: The collected browser history data.
        output_dir: The directory where exports will be saved.
    """
    os.makedirs(output_dir, exist_ok=True) # Create the output directory
    
    filename_prefix = f"{image_name}_browser_history_{selected_browser}" if selected_browser else f"{image_name}_browser_history"
            
    # Export to CSV
    csv_path = os.path.join(output_dir, f'{filename_prefix}.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['browser', 'profile', 'timestamp', 'url', 'title']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for entry in history_data:
            writer.writerow(entry)
    print(f"\nExported CSV to: {csv_path}")
    
    # Export to JSON
    json_path = os.path.join(output_dir, f'{filename_prefix}.json')
    with open(json_path, 'w', encoding='utf-8') as jsonfile:
        json.dump(history_data, jsonfile, indent=4)
    print(f"Exported JSON to: {json_path}")

def parse_browser_selection():
    """
    Prompt user to select which browser(s) to analyze.

    Returns:
        str: Selected browser or None for all browsers
    """
    print("\nSelect browser to analyze (or press Enter for all):")
    print("1. Chrome")
    print("2. Firefox")
    print("3. Edge")
    print("4. All browsers")
    
    choice = input("\nEnter your choice (1-4 or browser name): ").strip().lower()
    
    browser_map = {
        '1': 'chrome',
        'chrome': 'chrome',
        '2': 'firefox',
        'firefox': 'firefox',
        '3': 'edge',
        'edge': 'edge',
        '4': None,
        'all': None,
        '': None
    }
    
    selected_browser = browser_map.get(choice)
    
    if selected_browser is None and choice not in browser_map:
        print("Invalid choice. Analyzing all browsers...")
        selected_browser = None
    
    return selected_browser

def get_ewf_segments(base_path, base_name, logger):
    """
    Find all segments belonging to a specific EWF image.
    
    Args:
        base_path: Directory containing the image
        base_name: Base name of the image (e.g., 'Laptop1Final' from 'Laptop1Final.E01')
        logger: Logger object
    
    Returns:
        list: Ordered list of segment paths belonging to this image
    """
    segments = []
    segment_num = 1
    
    while True:
        found = None
        # Look for next segment using exact naming
        for ext in [f".E{segment_num:02d}", f".e{segment_num:02d}"]:
            candidate = os.path.join(base_path, f"{base_name}{ext}")
            if os.path.exists(candidate):
                found = candidate
                break
        if found:
            segments.append(found)
            logger.info(f"Found segment: {os.path.basename(found)}")
            segment_num += 1
        else:
            break
    
    return segments

def get_raw_segments(base_path, base_name, logger):
    """Find all segments of a segmented raw image (.001, .002, etc.)"""
    segments = []
    segment_num = 1
    
    while True:
        candidate = os.path.join(base_path, f"{base_name}.{segment_num:03d}")
        if os.path.exists(candidate):
            segments.append(candidate)
            logger.info(f"Found segment: {os.path.basename(candidate)}")
            segment_num += 1
        else:
            break
    
    return segments

def open_ewf_image(image_path, logger):
    """
    Open the EWF disk image and handle split files (E01, E02, etc.).

    Args:
        image_path (str): Path to any segment of the EWF image
        logger: Logging object

    Returns:
        tuple: (ewf_handle, img_info, image_name, image_size, image_hash, filenames)
    """
    try:
        image_path = os.path.normpath(image_path)
        base_path = os.path.dirname(image_path)
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        
        # Verify this is an E01 file
        if not image_path.upper().endswith('.E01'):
            logger.error("Must specify the .E01 file of the image series")
            raise ValueError("Invalid file format - must be .E01")
        
        # Find all segments for this specific image
        filenames = get_ewf_segments(base_path, base_name, logger)
        
        if not filenames:
            logger.error(f"No valid EWF segments found for {base_name}")
            raise ValueError("No valid segments found")
        
        # Report what we found
        if len(filenames) > 1:
            logger.info(f"Found {len(filenames)} segments for {base_name}")
        else:
            logger.info(f"Single segment image: {base_name}")
        
        # Open the image with all its segments
        ewf_handle = pyewf.handle()
        ewf_handle.open(filenames)

        # Extract embedded hash from EWF binary sections
        embedded_md5, embedded_sha1 = extract_ewf_hashes(filenames, logger)
        if embedded_md5 or embedded_sha1:
            image_hash = embedded_md5 or embedded_sha1
        else:
            logger.warning("No embedded hash found. Computing SHA-256 as session baseline.")
            ewf_handle.seek(0)
            image_hash = compute_hash_by_algorithm(ewf_handle, 'sha256', logger)

        ewf_handle.seek(0)  # Reset before wrapping
        img_info = EwfImgInfo(ewf_handle)
        
        # Get total image size
        image_size = ewf_handle.get_media_size()
        size_gb = image_size / (1024**3)
        logger.info(f"Total image size: {image_size} bytes ({size_gb:.2f} GB)")
        
        return ewf_handle, img_info, base_name, image_size, image_hash, filenames
        
    except Exception as e:
        logger.error(f"Failed to open EWF image: {str(e)}")
        raise

def parse_hash_algorithm():
    """Prompt user to select hash algorithm for raw image verification."""
    print("\nSelect hash algorithm for integrity verification:")
    print("1. MD5 (fastest, forensic standard)")
    print("2. SHA-1 (forensic standard)")
    print("3. SHA-256 (most secure)")

    choice = input("\nEnter your choice (1-3, default: 1): ").strip()

    algo_map = {
        '1': 'md5',
        'md5': 'md5',
        '2': 'sha1',
        'sha1': 'sha1',
        '3': 'sha256',
        'sha256': 'sha256',
        '': 'md5',
    }

    algorithm = algo_map.get(choice.lower(), 'md5')
    print(f"Using {algorithm.upper()} for hashing.")
    return algorithm

def compute_hash_raw_segments(segments, algorithm, logger):
    """Compute hash across all segments of a raw image as if they were one file."""
    logger.info(f"Computing {algorithm.upper()} hash across {len(segments)} segments...")
    h = hashlib.new(algorithm)
    chunk_size = 1024 * 1024
    total_size = sum(os.path.getsize(s) for s in segments)
    processed = 0

    for segment in segments:
        with open(segment, 'rb') as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                h.update(data)
                processed += len(data)
                print(f"\r[HASHING] {(processed/total_size)*100:.1f}% complete", end="")

    result = h.hexdigest()
    print(f"\n[+] Computed {algorithm.upper()}: {result}")
    return result

def open_raw_image(image_path, algorithm, logger):
    """
    Open a raw DD image.

    Returns:
        tuple: (img_info, base_name, image_size, image_hash, segments)
    """
    image_path = os.path.normpath(image_path)
    base_path = os.path.dirname(image_path)
    base_name = os.path.splitext(os.path.basename(image_path))[0]

    # Check if this is a segmented raw image (.001, .002, ...)
    segments = get_raw_segments(base_path, base_name, logger)
    if segments:
        logger.info(f"Found {len(segments)} raw segments for {base_name}")
        img_info = RawSegmentImgInfo(segments)
    else:
        logger.info(f"Single raw image: {base_name}")
        img_info = pytsk3.Img_Info(image_path)
        segments = [image_path]

    image_size = img_info.get_size()
    logger.info(f"Image size: {image_size} bytes ({image_size/(1024**3):.2f} GB)")

    image_hash = compute_hash_raw_segments(segments, algorithm, logger)

    return img_info, base_name, image_size, image_hash, segments

def get_filesystem(img_info, image_size, logger):
    """
    Get the filesystem information from the disk image. If offset is random, carves raw data until it hits another partition or end

    Args:
        img_info: Disk image information object
        logger: Logging object
        image_size: Size of image
        volume_info: the volume we are in

    Returns:
        tuple: fs_info or None if failed
    """
    # Detect and select partition offset
    offset, volume_info = get_partition_offset(img_info, logger)
    if offset is None:
        logger.info("User quit partition selection")
        return None
    
    logger.info(f"Using partition offset: {offset}")
    
    try:
        # Open filesystem
        fs_info = pytsk3.FS_Info(img_info, offset=offset)
        return fs_info
    except Exception as e:
        logger.error(f"Failed to open filesystem at offset {offset}: {str(e)}")
        
        # Peek 100 bytes to show the user
        raw_data = img_info.read(offset, 100)
        print(f"Raw data preview at {offset}")
        hex_view = raw_data.hex(' ', 1).upper()
        # Text view (The decoded English/readable parts)
        text_view = "".join([chr(b) if 32 <= b <= 126 else "." for b in raw_data])
        
        print(f"HEX:  {hex_view[:50]}") 
        print(f"TEXT: {text_view}")
        print("------------------------------------------")

        # Ask the user if they want to carve data
        choice = input("\nUnrecognized filesystem. Carve from this offset to a file for analysis? (y/n, Default: 'n'): ")
        
        if choice.lower() == 'y':
            # Calculate the 'Maximum' possible carve size
            max_safe_size = calculate_carve_size(offset, image_size, volume_info, logger)
            
            print(f"\nMaximum suggested carve size: {max_safe_size} bytes ({max_safe_size // 1024**2} MB)")
            user_size = input("How many bytes to carve? (Type 'all' or press Enter for maximum): ").strip().lower()
            
            # Determine the actual size to carve
            if user_size == 'all' or user_size == '':
                carve_size = max_safe_size
            else:
                try:
                    carve_size = int(user_size)
                    if carve_size > (image_size - offset):
                        logger.warning("Requested size exceeds disk boundaries. Capping at disk end.")
                        carve_size = image_size - offset
                except ValueError:
                    logger.error("Invalid number entered. Defaulting to maximum safe size.")
                    carve_size = max_safe_size

            output_name = f"carved_offset_{offset}.bin"
            logger.info(f"Carving {carve_size} bytes starting at {offset}...")
            run_carver(img_info, offset, carve_size, output_name)
            
        return None

def calculate_carve_size(user_offset, total_image_size, volume_info, logger):
    """
    Calculate the maximum safe carve size based on partition boundaries.
    
    Args:
        user_offset: The offset where carving starts
        total_image_size: Total size of the disk image
        volume_info: Volume information object containing partition data
        logger: Logger object
    
    Returns:
        int: Maximum safe carve size in bytes
    """
    # Default to carving everything until the end of the disk
    end_point = total_image_size
    
    if volume_info:
        # Create a sorted list of all partition starting offsets
        # We use partition.start * 512 to get the byte address
        all_starts = sorted([p.start * 512 for p in volume_info])

        for p_start_bytes in all_starts:
            # Find the first partition that starts AFTER our manual offset
            if p_start_bytes > user_offset:
                end_point = p_start_bytes
                logger.info(f"Next partition detected at {end_point}. Limiting carve size.")
                break
                
    return end_point - user_offset

def run_carver(img_info, start_offset, carve_size, output_filename):
    """
    Carve raw data from disk image to a file.
    
    Args:
        img_info: Disk image information object
        start_offset: Starting byte offset for carving
        carve_size: Number of bytes to carve
        output_filename: Output filename for carved data
    """
    chunk_size = 1024 * 1024  # 1MB buffer (bucket to move bytes to file, loading all eg:50GB would crash RAM)
    bytes_carved = 0
    
    try:
        with open(output_filename, "wb") as f_out:
            while bytes_carved < carve_size:
                to_read = min(chunk_size, carve_size - bytes_carved) # 50.5 GB, then grab 1Mb until we have 50.5-49GB = 0.5GB, don't grab 1GB that's in the bucket, grab the min 0.5GB
                data = img_info.read(start_offset + bytes_carved, to_read)
                
                if not data:
                    break
                
                f_out.write(data)
                bytes_carved += len(data)
                
                # Progress bar
                percent = (bytes_carved / carve_size) * 100
                print(f"\r[CARVING] {percent:.1f}% ({bytes_carved // 1024**2} MB)", end="")
                
        print(f"\n[+] Success! Data saved to: {output_filename}")
    except Exception as e:
        print(f"\n[!] Error during carving: {e}")

def process_user_profiles(fs_info, selected_browser, logger):
    """
    Process browser history for all user profiles.

    Args:
        fs_info: Filesystem information object
        selected_browser (str or None): Specific browser to analyze
        logger: Logging object

    Returns:
        list: Collected browser history entries
    """
    all_history = []
    
    try:
        # Open Users directory
        users_dir = fs_info.open_dir("Users")
    except Exception as e:
        logger.error(f"Failed to open Users directory: {str(e)}")
        return all_history
    
    logger.info("\nFound user profiles:")
    for entry in users_dir:
        name = "unknown"  # Initialize name to handle errors
        try:
            # Decode username and filter out system directories
            name = entry.info.name.name.decode('utf-8')
            if name not in [".", "..", "Default", "Default User", "All Users", "Public"]:
                if entry.info.meta is None:
                    continue
                if entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR: # Check if pytsk3 recognizes it as a directory
                    logger.info(f"Searching browser history for user: {name}")
                    
                    # Find browser files for this user
                    found_files = find_browser_files(fs_info, name, logger, selected_browser)
                    
                    # Process found browser files
                    for browser, profiles in found_files.items():
                        for profile_name, fs_file in profiles.items():
                            try:
                                history_entries = extract_and_analyze_history(fs_file, browser, profile_name)
                                if history_entries:
                                    logger.info(f"Successfully processed {browser} history from profile {profile_name}")
                                    all_history.extend(history_entries)
                            except Exception as e:
                                logger.error(f"Error processing {browser} history from profile {profile_name}: {str(e)}")
        except Exception as e:
            logger.error(f"Error processing user {name}: {str(e)}")
            continue
    
    return all_history

def main():
    """
    Main function to execute the script.
    Handles command line input for the E01 image path and orchestrates the workflow.
    """
    # Mode selection
    mode = parse_input_mode()

    # Live system path
    if mode == 'live':
        image_name = 'live_system'
        logger = setup_logging(image_name)
        logger.info("Running in live system mode")

        try:
            selected_browser = parse_browser_selection()
            output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_history_exports")
            all_history = process_live_system(selected_browser, logger)

            if all_history:
                export_history(all_history, output_dir, selected_browser, image_name)
                logger.info("Successfully exported browser history")
            else:
                logger.warning("No browser history found.")
        except Exception as e:
            logger.error(f"Critical error: {str(e)}")
            sys.exit(1)
        return

    # Image path (EWF or RAW)
    try:
        if len(sys.argv) > 1:
            image_path = sys.argv[1]
        else:
            prompt = "Enter path to .E01 file: " if mode == 'ewf' else "Enter path to raw image (.dd/.raw/.img): "
            image_path = input(prompt).strip()
        
        if not os.path.exists(image_path):
            print(f"Error: Image file not found: {image_path}")
            sys.exit(1)
        
        # Extract image name — strip any known forensic extension
        image_name = os.path.basename(image_path)
        image_name = re.sub(r'\.[Ee]\d+$', '', image_name)           # .E01, .e01
        image_name = re.sub(r'\.(dd|raw|img)$', '', image_name, flags=re.IGNORECASE)
        image_name = re.sub(r'\.\d{3}$', '', image_name)  # .001, .002, etc.

        logger = setup_logging(image_name)
        logger.info(f"Processing image: {image_path} (mode: {mode})")
        
    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"Error initializing program: {e}")
        sys.exit(1)

    ewf_handle = None
    initial_hash = None
    filenames = None
    raw_segments = None
    raw_img_info = None 
    analysis_complete = False

    try:
        selected_browser = parse_browser_selection()
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_history_exports")

        # Open image
        if mode == 'ewf':
            ewf_handle, img_info, image_name, total_image_size, initial_hash, filenames = open_ewf_image(image_path, logger)
        else: #raw
            hash_algorithm = parse_hash_algorithm()
            img_info, image_name, total_image_size, initial_hash, raw_segments = open_raw_image(image_path, hash_algorithm, logger)
            raw_img_info = img_info

        # Filesystem & extraction 
        fs_info = get_filesystem(img_info, total_image_size, logger)
        if fs_info is None:
            initial_hash = None  # prevent validation on clean exit
            return

        all_history = process_user_profiles(fs_info, selected_browser, logger)

        if all_history:
            export_history(all_history, output_dir, selected_browser, image_name)
            logger.info("Successfully exported browser history")
        else:
            logger.warning("No browser history found to export.")

        analysis_complete = True
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
        sys.exit(1)

    finally:
        # Validate first, then close
        if initial_hash is not None and analysis_complete:
            logger.info("Performing final integrity validation...")
            if mode == 'ewf' and ewf_handle is not None:
                embedded_md5, embedded_sha1 = extract_ewf_hashes(filenames, logger)
                final_hash = embedded_md5 or embedded_sha1
                if final_hash is None:
                    ewf_handle.seek(0)
                    final_hash = compute_hash_by_algorithm(ewf_handle, detect_algorithm(initial_hash) or 'sha256', logger)
            elif mode == 'raw' and raw_segments is not None:
                final_hash = compute_hash_raw_segments(raw_segments, detect_algorithm(initial_hash) or 'sha256', logger)
            else:
                final_hash = None

            if final_hash is None:
                logger.warning("Could not perform final integrity check.")
            elif initial_hash == final_hash:
                logger.info("VALIDATION SUCCESS: Image unchanged during analysis.")
            else:
                logger.critical("VALIDATION FAILED: Hash mismatch! Image may have been modified.")

        # Always close handles
        if ewf_handle is not None:
            ewf_handle.close()
        if raw_img_info is not None:
            raw_img_info.close()

if __name__ == "__main__":
    main()

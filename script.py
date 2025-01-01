import pytsk3 
import pyewf
import os
import sqlite3
from datetime import datetime
import tempfile
import shutil
import sys
import csv
import json

def setup_logging(image_name):
    """
    Setup logging configuration for error tracking.
    
    Args:
        image_name: Name of the E01 image being processed
    
    Returns:
        logger: Configured logging object
    """
    import logging
    from datetime import datetime
    
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
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

class EwfImgInfo(pytsk3.Img_Info):
    def __init__(self, ewf_handle):
        # Initialize the EWF image info object.
        self._ewf_handle = ewf_handle
        super(EwfImgInfo, self).__init__(url="", type=pytsk3.TSK_IMG_TYPE_EXTERNAL) # TSK_IMG_TYPE_EXTERNAL because it's a EWF file and not a traditional disk image.

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

def get_partition_offset(img_info, logger):
    """
    Get partition offset either automatically or through user input.
    
    Args:
        img_info: The disk image info object
        logger: Logger object for error tracking
    
    Returns:
        int: Partition offset in bytes, or None if user quits
    """
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
                logger.error("Invalid offset choice")

    def get_manual_offset():
        """Helper function to handle manual offset input"""
        try:
            offset = int(input("Enter offset in bytes: "))
            logger.info(f"Using manual offset: {offset}")
            return offset
        except ValueError:
            logger.error("Invalid offset value entered")
            return 'retry'

    try:
        auto_offset = find_windows_partition(img_info, logger)
        
        while True:
            logger.info("\nPartition offset options:")
            if auto_offset:
                logger.info(f"1. Use detected offset ({auto_offset} bytes)")
                logger.info("2. Enter offset manually")
                logger.info("3. Try common offsets")
            else:
                logger.info("1. Enter offset manually")
                logger.info("2. Try common offsets")
            logger.info("q. Quit")
            
            choice = input("\nEnter your choice: ").lower()
            
            if choice == 'q':
                return None

            if auto_offset:
                if choice == '1':
                    logger.info(f"Using automatically detected offset: {auto_offset}")
                    return auto_offset
                elif choice == '2':
                    result = get_manual_offset()
                    if result != 'retry':
                        return result
                elif choice == '3':
                    result = show_common_offsets()
                    if result is None:
                        return None
                    elif result != 'back':
                        return result
                else:
                    logger.error("Invalid choice")
            else:
                if choice == '1':
                    result = get_manual_offset()
                    if result != 'retry':
                        return result
                elif choice == '2':
                    result = show_common_offsets()
                    if result is None:
                        return None
                    elif result != 'back':
                        return result
                else:
                    logger.error("Invalid choice")
                    
    except Exception as e:
        logger.error(f"Error in partition offset selection: {str(e)}")
        return None
    
def find_windows_partition(img_info, logger):
    """
    Find the offset of the NTFS partition in the disk image.
    
    Args:
        img_info: The disk image info object
    
    Returns:
        int: Offset to the NTFS partition, or None if not found
    """
    try:
        volume_info = pytsk3.Volume_Info(img_info)
        sector_size = 512
        
        logger.info("\nDetected Partitions:")
        for partition in volume_info:
            desc = partition.desc.decode('utf-8').lower()
            logger.info(f"Addr: {partition.addr}, Start: {partition.start}, Desc: {partition.desc.decode('utf-8')}")
            
            # Look for Windows partition indicators
            if any(x in desc for x in ['ntfs', 'basic data partition', 'windows']):
                offset = partition.start * sector_size
                logger.info(f"\nFound Windows partition at sector {partition.start}")
                logger.info(f"Using offset: {offset} bytes")
                return offset
        
        logger.warning("No Windows partition found in automatic detection")      
        return None
            
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
        return None

def find_browser_files(fs_info, username, logger, selected_browser=None):
    """
    Search for browser history files for a specific user.

    Args:
        fs_info: Filesystem information object.
        username: The username whose browser files are to be searched.

    Returns:
        dict: Found browser files with browser names as keys and file objects as values.
    """

    found_files = {}
    
    # Define paths for each browser's history file.
    browser_paths = {
        'Chrome': f"Users/{username}/AppData/Local/Google/Chrome/User Data",
        'Edge': f"Users/{username}/AppData/Local/Microsoft/Edge/User Data",
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

    # If a specific browser was selected, check if it's installed
    if selected_browser:
        selected_browser = selected_browser.capitalize()
        if selected_browser not in installed_browsers:
            logger.warning(f"{selected_browser} is not installed for user {username}")
            return found_files
        installed_browsers = {selected_browser: installed_browsers[selected_browser]}
    
    # List of known non-profile directories for Chromium browsers
    non_profile_dirs = {
        "crashpad", "grshaderCache", "local state", "safe browsing", 
        "shadercache", "swreporter", "webassistant", "firstrun",
        "crashpadmetrics", "browsermetrics", "module info cache",
        "sslerrorsassistant", "autofillstates", "avatars", 
        "certificaterevocation", "clientsidephishing", "commerceheuristics",
        "desktopsharinghub", "filetypepolicies", "optimizationhints",
        "origintrials", "pkimetadata", "pnacl", "recoveryimproved",
        "safetytips", "firstpartysetspreloaded", "hyphen-data",
        "mediafoundationwidevinecdm", "meipreload", "ondeviceheadsuggestmodel",
        "subresource filter", "thirdpartymodulelist64", "urlparamclassifications",
        "widevinecdm", "zxcvbndata"
    }
    
    # Iterate through each browser and search for its history file.
    for browser, base_path in installed_browsers.items():
        found_files[browser] = {} 
        try:
            if browser == 'Firefox':
                try:
                    profiles_dir = fs_info.open_dir(base_path)
                    for profile in profiles_dir:
                        profile_name = profile.info.name.name.decode('utf-8')
                        if profile_name in [".", ".."]:
                            continue
                            
                        # Look for places.sqlite in each profile directory
                        history_path = f"{base_path}/{profile_name}/places.sqlite"
                        try:
                            file = fs_info.open(history_path)
                            found_files[browser][profile_name] = file  # Store with profile name as key
                            logger.info(f"Found Firefox history in profile {profile_name}")
                        except Exception as e:
                            logger.debug(f"Error accessing Firefox history in profile {profile_name}: {e}")
                except Exception as e:
                    logger.error(f"Error accessing Firefox profiles directory: {e}")
                    
            else:  # Chrome and Edge
                try:
                    profiles_dir = fs_info.open_dir(base_path)
                    for profile in profiles_dir:
                        try:
                            profile_name = profile.info.name.name.decode('utf-8')
                            if profile_name in [".", ".."]:
                                continue
                                
                            # Skip non-profile directories
                            if profile_name.lower() in non_profile_dirs:
                                continue
                                
                            # Skip files (looking for directories only)
                            if not profile.info.meta or profile.info.meta.type != pytsk3.TSK_FS_META_TYPE_DIR:
                                continue
                                
                            # Look for History file in the profile directory
                            history_path = f"{base_path}/{profile_name}/History"
                            try:
                                file = fs_info.open(history_path)
                                found_files[browser][profile_name] = file  # Store with profile name as key
                                logger.info(f"Found {browser} history in profile {profile_name}")
                            except Exception as e:
                                logger.debug(f"Error accessing {browser} history in profile {profile_name}: {e}")
                                
                        except Exception as e:
                            if "NoneType" not in str(e):  # Suppress common NoneType errors
                                logger.debug(f"Error processing {browser} profile: {str(e)}")
                            
                except Exception as e:
                    logger.error(f"Error accessing {browser} profiles directory: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error accessing base path for {browser}: {str(e)}")
            
    return found_files

def extract_and_analyze_history(fs_file, browser_type, profile_name):
    """
    Extract and analyze browser history from a filesystem file.

    Args:
        fs_file: The filesystem file object for the browser history.
        browser_type: The type of browser (e.g., Chrome, Firefox).
        profile_name: The profile name where history was found

    Returns:
        list: A list of history entries containing URLs, titles, and timestamps.
    """
    
    temp_file = None
    try:
        temp_dir = tempfile.mkdtemp() # Create a temporary directory.
        temp_file = os.path.join(temp_dir, "temp_db")
        
        # Write the history file to a temporary location.
        with open(temp_file, 'wb') as outfile:
            outfile.write(fs_file.read_random(0, fs_file.info.meta.size))
        
        # Extract history based on browser type.
        if browser_type in ['Chrome', 'Edge']:
            results = extract_chromium_history(temp_file)
        else:
            results = extract_firefox_history(temp_file)
        
        history_entries = []
        print(f"\n{browser_type} History from profile {profile_name}:")
        
        # Process and format each history entry.
        for url, title, timestamp in results:
            if browser_type in ['Chrome', 'Edge']:
                timestamp = datetime.fromtimestamp((timestamp/1000000)-11644473600)
            else:
                timestamp = datetime.fromtimestamp(timestamp/1000000)
            
            entry = {
                'browser': browser_type,
                'profile': profile_name,
                'url': url,
                'title': title,
                'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S')
            }
            # Print the formatted history entry.
            history_entries.append(entry)
            
            print(f"URL: {url}")
            print(f"Title: {title}")
            print(f"Profile: {profile_name}")
            print(f"Visited: {timestamp}")
            print("-" * 50)
            
        return history_entries
            
    except Exception as e:
        print(f"Error processing {browser_type} history: {str(e)}")
        return []
    finally:
        # Clean up temporary files.
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)
            if os.path.exists(os.path.dirname(temp_file)):
                shutil.rmtree(os.path.dirname(temp_file))

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
        conn.execute("PRAGMA journal_mode=WAL")  # Use WAL mode
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
        SELECT url, title, last_visit_date/1000000 as visit_date
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
    
    if selected_browser is False:
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
        # Look for next segment using exact naming
        segment_path = os.path.join(base_path, f"{base_name}.E{segment_num:02d}")
        if os.path.exists(segment_path):
            segments.append(segment_path)
            logger.info(f"Found segment: {os.path.basename(segment_path)}")
            segment_num += 1
        else:
            break
    
    return segments

def open_disk_image(image_path, logger):
    """
    Open the EWF disk image and handle split files (E01, E02, etc.).

    Args:
        image_path (str): Path to any segment of the EWF image
        logger: Logging object

    Returns:
        tuple: (ewf_handle, img_info, image_name, image_size)
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
        img_info = EwfImgInfo(ewf_handle)
        
        # Get total image size
        image_size = ewf_handle.get_media_size()
        size_gb = image_size / (1024**3)
        logger.info(f"Total image size: {image_size} bytes ({size_gb:.2f} GB)")
        
        return ewf_handle, img_info, base_name, image_size
        
    except Exception as e:
        logger.error(f"Failed to open disk image: {str(e)}")
        raise

def get_filesystem(img_info, logger):
    """
    Get the filesystem information from the disk image.

    Args:
        img_info: Disk image information object
        logger: Logging object

    Returns:
        tuple: (fs_info, offset) or (None, None) if failed
    """
    # Detect and select partition offset
    offset = get_partition_offset(img_info, logger)
    if offset is None:
        logger.info("User quit partition selection")
        return None, None
    
    logger.info(f"Using partition offset: {offset}")
    
    try:
        # Open filesystem
        fs_info = pytsk3.FS_Info(img_info, offset=offset)
        return fs_info, offset
    except Exception as e:
        logger.error(f"Failed to open filesystem at offset {offset}: {str(e)}")
        return None, None

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
        try:
            # Decode username and filter out system directories
            name = entry.info.name.name.decode('utf-8')
            if name not in [".", "..", "Public", "Default", "Default User", "All Users"]:
                if entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
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
    # Get image path from command line or prompt user
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        print("Please enter the path to any segment of the EWF image file (E01, E02, etc.).")
        image_path = input("Image path: ")
    
    # Set up logging
    image_name = os.path.splitext(os.path.basename(image_path))[0]
    image_name = image_name.rstrip('0123456789')  # Remove segment number
    logger = setup_logging(image_name)
    
    try:
        # Parse browser selection
        selected_browser = parse_browser_selection()
    
        # Set output directory for exports
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_history_exports")
        
        # Open disk image
        ewf_handle, img_info, image_name, image_size = open_disk_image(image_path, logger)
        
        # Get filesystem information
        fs_info, offset = get_filesystem(img_info, logger)
        if fs_info is None:
            return
        
        # Process user profiles and collect browser history
        all_history = process_user_profiles(fs_info, selected_browser, logger)
        
        # Export the collected history
        if all_history:
            export_history(all_history, output_dir, selected_browser, image_name)
            logger.info("Successfully exported browser history")
        else:
            logger.warning("No browser history found to export.")
                
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
        sys.exit(1)
    finally:
        # Ensure EWF handle is closed
        if 'ewf_handle' in locals():
            ewf_handle.close()

if __name__ == "__main__":
    main()
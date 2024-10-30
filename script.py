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

class EwfImgInfo(pytsk3.Img_Info):
    def __init__(self, ewf_handle):
        self._ewf_handle = ewf_handle
        super(EwfImgInfo, self).__init__(url="", type=pytsk3.TSK_IMG_TYPE_EXTERNAL)

    def close(self):
        self._ewf_handle.close()

    def read(self, offset, size):
        self._ewf_handle.seek(offset)
        return self._ewf_handle.read(size)

    def get_size(self):
        return self._ewf_handle.get_media_size()

def find_browser_files(fs_info, username):
    """
    Search for browser history files for a specific user
    """
    found_files = {}
    browser_paths = {
        'Chrome': f"/Users/{username}/AppData/Local/Google/Chrome/User Data/Default/History",
        'Edge': f"/Users/{username}/AppData/Local/Microsoft/Edge/User Data/Default/History",
        'Firefox': f"/Users/{username}/AppData/Roaming/Mozilla/Firefox/Profiles"
    }
    
    for browser, base_path in browser_paths.items():
        try:
            if browser == 'Firefox':
                try:
                    profiles_dir = fs_info.open_dir(base_path)
                    for profile in profiles_dir:
                        profile_name = profile.info.name.name.decode('utf-8')
                        if 'default' in profile_name.lower() and profile_name not in [".", ".."]:
                            full_path = f"{base_path}/{profile_name}/places.sqlite"
                            try:
                                file = fs_info.open(full_path)
                                found_files['Firefox'] = file
                                print(f"Found Firefox history for {username}")
                                break
                            except:
                                continue
                except:
                    pass
            else:
                try:
                    file = fs_info.open(base_path)
                    found_files[browser] = file
                    print(f"Found {browser} history for {username}")
                except:
                    pass
                    
        except Exception as e:
            continue
            
    return found_files

def extract_and_analyze_history(fs_file, browser_type):
    """
    Extract and analyze browser history from a filesystem file
    """
    temp_file = None
    try:
        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, "temp_db")
        
        with open(temp_file, 'wb') as outfile:
            outfile.write(fs_file.read_random(0, fs_file.info.meta.size))
        
        if browser_type in ['Chrome', 'Edge']:
            results = extract_chrome_history(temp_file)
        else:
            results = extract_firefox_history(temp_file)
        
        history_entries = []
        print(f"\n{browser_type} History:")
        for url, title, timestamp in results[:10]:
            if browser_type in ['Chrome', 'Edge']:
                timestamp = datetime.fromtimestamp((timestamp/1000000)-11644473600)
            else:
                timestamp = datetime.fromtimestamp(timestamp/1000000)
            
            entry = {
                'browser': browser_type,
                'url': url,
                'title': title,
                'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S')
            }
            history_entries.append(entry)
            
            print(f"URL: {url}")
            print(f"Title: {title}")
            print(f"Visited: {timestamp}")
            print("-" * 50)
            
        return history_entries
            
    except Exception as e:
        print(f"Error processing {browser_type} history: {str(e)}")
        return []
    finally:
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)
            if os.path.exists(os.path.dirname(temp_file)):
                shutil.rmtree(os.path.dirname(temp_file))

def extract_chrome_history(db_path):
    """
    Extract URLs from Chrome/Edge history
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    query = """
    SELECT url, title, last_visit_time 
    FROM urls 
    ORDER BY last_visit_time DESC
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    conn.close()
    return results

def extract_firefox_history(db_path):
    """
    Extract URLs from Firefox history
    """
    conn = sqlite3.connect(db_path)
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

def export_history(history_data, output_dir):
    """
    Export browser history to CSV and JSON formats
    """
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Export to CSV
    csv_path = os.path.join(output_dir, f'browser_history_{timestamp}.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['browser', 'timestamp', 'url', 'title']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for entry in history_data:
            writer.writerow(entry)
    print(f"\nExported CSV to: {csv_path}")
    
    # Export to JSON
    json_path = os.path.join(output_dir, f'browser_history_{timestamp}.json')
    with open(json_path, 'w', encoding='utf-8') as jsonfile:
        json.dump(history_data, jsonfile, indent=4)
    print(f"Exported JSON to: {json_path}")

def main():
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        image_path = input("Please enter the path to your E01 image file: ")
    
    # Set output directory for exports
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_history_exports")
    
    try:
        # Open the disk image
        print(f"Opening disk image: {image_path}")
        ewf_handle = pyewf.handle()
        ewf_handle.open(pyewf.glob(image_path))
        img_info = EwfImgInfo(ewf_handle)
        
        # Get the filesystem
        fs_info = pytsk3.FS_Info(img_info, offset=239616*512)  # Basic Data Partition offset
        
        # Find Users directory
        all_history = []
        users_dir = fs_info.open_dir("/Users")
        
        print("\nFound user profiles:")
        for entry in users_dir:
            try:
                name = entry.info.name.name.decode('utf-8')
                if name not in [".", "..", "Public", "Default", "Default User", "All Users"]:
                    if entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
                        print(f"Searching browser history for user: {name}")
                        found_files = find_browser_files(fs_info, name)
                        
                        # Process found browser files
                        for browser, fs_file in found_files.items():
                            history_entries = extract_and_analyze_history(fs_file, browser)
                            all_history.extend(history_entries)
            except:
                continue
        
        # Export the collected history
        if all_history:
            export_history(all_history, output_dir)
        else:
            print("No browser history found to export.")
                
    except Exception as e:
        print(f"Critical error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
# Browser History Extractor

A Python-based forensic tool for extracting browser history from EWF (E01) disk images. Currently supports Chrome, Edge, and Firefox browsers.

## Features
- Automatic Windows partition detection
- Multiple partition offset handling options
- Support for multiple browsers:
  - Google Chrome
  - Microsoft Edge
  - Mozilla Firefox
- Multi-profile support per browser
- Export formats:
  - CSV (with timestamps, URLs, titles)
  - JSON (detailed browser history)
- Detailed error logging and debugging
- Support for handling large disk images
- Multiple user profile analysis

## Prerequisites
```bash
pip install pytsk3 pyewf
```

## Important Notes About EWF Files
This tool handles both single EWF files (.E01) and split EWF files (.E01, .E02, etc.):
- Single files: Standard E01 forensic images
- Split files: Large images split into multiple segments (E01-E0x)

When using split images:
- Always specify the .E01 file
- All segments must be in the same directory
- Segments must follow naming convention (basename.E01, basename.E02, etc.)

## Installation
```bash
git clone https://github.com/Deluxecoder12/Browser-history-extractor.git
```

## Usage
```bash
python script.py [path_to_E01_file]
```

If no path is provided, the script will prompt for one.

## Interactive Menu
The script provides an interactive menu to select which browser's history to extract:

### Browser Selection

1. Chrome
2. Firefox
3. Edge
4. All browsers (default)

### Partition Selection

1. Automatic Windows partition detection
2. Manual offset input option
3. Common preset offsets:
- 0 bytes
- 1048576 bytes (512 * 2048)
- 65536 bytes (512 * 128)
- 122683392 bytes (512 * 239616)

## Output
The script creates a browser_history_exports directory containing:

### browser_history_exports/:
##### Contains extracted history

[image_name]_browser_history.csv
[image_name]_browser_history.json

### logs/:
##### Contains detailed error logs

[image_name]_[timestamp]_errors.log

### History Entry Format
Each entry contains:

- Browser name
- Profile name
- Timestamp
- URL
- Page title

## Testing
Tested successfully with Python 3.6+ on:
1. Windows 10/11
2. E01 images from CTF challenges
3. Multiple user profiles
4. Different partition layouts

## Error Handling
- Comprehensive error logging
- Debug information for failed operations
- Detailed partition information logging
- Browser installation verification
- Profile access error tracking

## Future Improvements

- Add support for more browsers (Safari, Opera, Brave)
- Add timeline visualization
- Add support for browser cache and cookies
- Add multi-threading for faster processing
- Add support for more image formats (AFF)
- Add GUI interface

## License
This project is licensed under Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
You are free to:

Share — copy and redistribute the material in any medium or format
Adapt — remix, transform, and build upon the material

Under the following terms:

Attribution — You must give appropriate credit
NonCommercial — You may not use the material for commercial purposes

## Function Documentation

This document outlines the functions used in the Browser History Extraction script that analyzes browser history from EWF disk images.

## 1. setup_logging(image_name)
### Purpose: 
Configure logging for error tracking and debugging.

### Inputs:
image_name: Name of the E01 image being processed

### Process:
- Creates a logs directory
- Generates a log filename with timestamp
- Configures logging to write to both file and console

### Returns:
Configured logging object

--- 

## 2. EwfImgInfo Class
### Purpose
Handles the interaction with the EWF image, providing methods to read data and retrieve size information.

### Inputs
- `ewf_handle`: An instance of `pyewf.handle` used to manage the EWF image.

### Process
- Inherits from `pytsk3.Img_Info`.
- Implements methods to read data and get the image size.

### Results
- Provides an interface to work with EWF images, allowing data extraction.

---

## 3. get_partition_offset(img_info, logger)
### Purpose: 
Determine the correct partition offset for filesystem analysis.

### Inputs:
- img_info: Disk image information object
- logger: Logging object for tracking operations

### Features:
- Automatic Windows partition detection
- Interactive menu for offset selection
- Support for predefined and manual offset inputs

### Returns: Selected partition offset

---

## 4. find_windows_partition(img_info, logger)
### Purpose: 
Automatically detect the Windows NTFS partition in a disk image.

### Inputs:
- img_info: Disk image information object
- logger: Logging object for tracking operations

### Process:
- Enumerate disk partitions
- Identify Windows-related partitions
- Log partition details

---

## 5. find_browser_files
### Purpose
Search for browser history files for a specific user in the filesystem.

### Inputs
- `fs_info`: The filesystem information object.
- `username`: The username whose browser files are to be searched.
- `logger`: Logging object
- `selected_browser`: Optional specific browser to search

### Process
- Defines paths for common browsers (Chrome, Edge, Firefox).
- Searches for the browser history files based on the defined paths.
- Detect installed browsers
- Find history files for multiple profiles

### Results
- Returns a dictionary of found browser files with browser names as keys and file objects as values.

---

## 6. extract_and_analyze_history
### Purpose
Extract and analyze browser history from a filesystem file.

### Inputs
- `fs_file`: The filesystem file object for the browser history.
- `browser_type`: The type of browser (e.g., Chrome, Firefox).

### Process
- Writes the history file to a temporary location.
- Calls the appropriate extraction function based on the browser type.
- Formats and prints the extracted history entries.

### Results
- Returns a list of history entries containing URLs, titles, and timestamps.

---

## 7. extract_chrome_history
### Purpose
Extract URLs from Chrome or Edge history databases.

### Inputs
- `db_path`: The path to the Chrome or Edge database file.

### Process
- Connects to the SQLite database and executes a query to fetch URLs and titles.

### Results
- Returns a list of tuples containing URLs, titles, and last visit times.

---

## 8. extract_firefox_history
### Purpose
Extract URLs from Firefox history databases.

### Inputs
- `db_path`: The path to the Firefox database file.

### Process
- Connects to the SQLite database and executes a query to fetch URLs and titles.

### Results
- Returns a list of tuples containing URLs, titles, and last visit dates.

---

## 9. export_history
### Purpose
Export collected browser history to CSV and JSON formats.

### Inputs
- `history_data`: The collected browser history data.
- `output_dir`: The directory where the exports will be saved.

### Process
- Creates an output directory if it does not exist.
- Writes the history data to a CSV file and a JSON file.

### Results
- Saves the exported history to specified files and prints the paths.

---

## 10. parse_browser_selection():
### Purpose:
- Handles user input for browser selection
- Provides a flexible mapping for browser choices


## 11. get_ewf_segments(base_path, base_name, logger)
### Purpose
Find all segments belonging to a specific EWF image series.

### Inputs
- `base_path`: Directory containing the image files
- `base_name`: Base name of the image (e.g., 'Laptop1Final' from 'Laptop1Final.E01')
- `logger`: Logging object

### Process
- Searches for sequential segments (E01, E02, etc.)
- Validates segment naming and sequence
- Logs found segments

### Returns
Ordered list of segment paths belonging to this image

## 12. open_disk_image(image_path, logger)
### Purpose
Open EWF disk image, handling both single and split files.

### Inputs
- `image_path`: Path to the E01 file
- `logger`: Logging object

### Process
- Normalizes path and extracts base name
- Finds all related segments if split
- Opens image with all segments
- Calculates total image size

### Returns
Tuple containing:
- ewf_handle: Handle to the opened image
- img_info: Image information object
- base_name: Image name without extension
- image_size: Total size in bytes

## 13. get_filesystem():
### Purpose:
- Manages partition offset detection and filesystem opening
- Provides clearer error handling

## 14. process_user_profiles():
### Purpose:
- Centralizes the logic of searching and processing browser history for all users
- Maintains the existing error handling and logging

## 15. main
### Purpose
Main function to execute the script and orchestrate the workflow.

### Inputs
- Accepts the path to an E01 image file as a command-line argument or prompts for input.

### Process
- Calls other functions to find browser files, extract history, and export results.

### Results
- Exports browser history data to specified formats or prints an error message if no history is found.

---

## Troubleshooting
### Common issues and solutions:

- Path not found: Check case sensitivity
- Partition detection fails: Try manual offset options
- Database locked: Check file permissions
- Memory errors: Consider image size and available RAM

### EWF-Specific Issues
- Split image errors: Ensure all segments are present and in sequence
- Wrong segment specified: Must use .E01 file for split images
- Multiple image series: Keep different image series in separate directories
- Segment naming: Follow standard EWF naming convention (basename.E0x)

## Contributing
1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
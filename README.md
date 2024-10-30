# history-extractor

## Function Documentation

This document outlines the functions used in the Browser History Extraction script that analyzes browser history from EWF disk images.

## 1. EwfImgInfo Class

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

## 2. find_browser_files

### Purpose
Search for browser history files for a specific user in the filesystem.

### Inputs
- `fs_info`: The filesystem information object.
- `username`: The username whose browser files are to be searched.

### Process
- Defines paths for common browsers (Chrome, Edge, Firefox).
- Searches for the browser history files based on the defined paths.

### Results
- Returns a dictionary of found browser files with browser names as keys and file objects as values.

---

## 3. extract_and_analyze_history

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

## 4. extract_chrome_history

### Purpose
Extract URLs from Chrome or Edge history databases.

### Inputs
- `db_path`: The path to the Chrome or Edge database file.

### Process
- Connects to the SQLite database and executes a query to fetch URLs and titles.

### Results
- Returns a list of tuples containing URLs, titles, and last visit times.

---

## 5. extract_firefox_history

### Purpose
Extract URLs from Firefox history databases.

### Inputs
- `db_path`: The path to the Firefox database file.

### Process
- Connects to the SQLite database and executes a query to fetch URLs and titles.

### Results
- Returns a list of tuples containing URLs, titles, and last visit dates.

---

## 6. export_history

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

## 7. main

### Purpose
Main function to execute the script and orchestrate the workflow.

### Inputs
- Accepts the path to an E01 image file as a command-line argument or prompts for input.

### Process
- Opens the disk image, retrieves the filesystem, and searches for user profiles.
- Calls other functions to find browser files, extract history, and export results.

### Results
- Exports browser history data to specified formats or prints an error message if no history is found.

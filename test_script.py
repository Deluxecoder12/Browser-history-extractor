import pytest
import ctypes
import os
from script import open_disk_image  #script.py

def test_open_non_image_file():
    non_image_file = 'D:/example.txt'  # Path to a non-image file
    result = open_disk_image(non_image_file)
    assert result is None, "Function should not open non-image files."

def test_open_e01_image(): # Ensure it opens successfully
    test_e01_image_path = 'D:/PC-MUS-001.E01' 
    result = open_disk_image(test_e01_image_path)
    assert result is not None, "Function should open image files." 

def test_open_empty_path():
    empty_path = ''
    result = open_disk_image(empty_path)
    assert result is None, "Function should return None for empty path."

def test_open_directory_instead_of_file():
    directory_path = 'D:/example_directory/'  # Path to a directory
    result = open_disk_image(directory_path)
    assert result is None, "Function should not open directories."

def test_open_invalid_image():
    # Test with an invalid image path
    invalid_image_path = 'not-a-image-file.E01'
    result = open_disk_image(invalid_image_path)
    assert result is None, "Function should not open invalid images"  # Ensure it fails to open

def test_open_file_with_no_permission():
    restricted_path = 'C:/Windows/System32/config/SAM'  # Random example of a path that requires admin rights
    result = open_disk_image(restricted_path)
    assert result is None, "Function should fail when access is restricted."

def test_open_raw_external_drive():
    external_drive_path = r'\\.\E:' # Testing with a random drive path
    # Check if the file opens succesfully
    if os.path.exists(external_drive_path):  # Check if the drive exists
        result = open_disk_image(external_drive_path)
        assert result is not None, f"Failed to open external drive at {external_drive_path}."
    else:
        print(f"External drive {external_drive_path} is not accessible.")
        assert True  # Test passes if the drive is not accessible

if __name__ == "__main__":
    pytest.main()

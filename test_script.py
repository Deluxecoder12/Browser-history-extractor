import pytest
import ctypes
import os
from script import open_disk_image  #script.py

def test_open_e01_image():
    test_e01_image_path = 'D:/PC-MUS-001.E01' 
    result = open_disk_image(test_e01_image_path)
    assert result is not None  # Ensure it opens successfully

def test_open_invalid_image():
    # Test with an invalid image path
    invalid_image_path = 'not-a-image-file.E01'
    result = open_disk_image(invalid_image_path)
    assert result is None  # Ensure it fails to open

if __name__ == "__main__":
    pytest.main()

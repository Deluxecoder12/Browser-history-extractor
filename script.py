import pytsk3

# Function to open and inspect disk image (Windows)
def open_disk_image(image_path):
    if not image_path:
        print("Image Path is empty")
        return None

    try:
        # For raw drives like \\.\E:
        if image_path.startswith(r'\\.\\'):  
            print(f"Opening raw external drive: {image_path}")
            img = pytsk3.Img_Info(image_path)
        # For disk images (.E01, .dd)
        else: 
            print(f"Opening disk image file: {image_path}")
            img = pytsk3.Img_Info(image_path)
        
        print(f"Successfully opened: {image_path}")
        return img
    except Exception as e:
        print(f"Error opening disk image or drive: {e}")
        return None

if __name__ == "__main__":
    disk_image_path = "D:/PC-MUS-001.E01"   # Dummy path for a .E01 file
    # disk_image_path = r'\\.\E:'   # Dummy path for a E:/ drive
    disk_image = open_disk_image(disk_image_path)

    if disk_image:
        print("Disk loaded and ready for further processing.")
    else:
        print("Failed to load the disk image. Please ensure the path is correct.")



import pytsk3

# Function to open and inspect disk image
def open_disk_image(image_path):
    try:
        img = pytsk3.Img_Info(image_path)
        print(f"Successfully opened disk image: {image_path}")
        return img
    except Exception as e:
        print(f"Error opening disk image: {e}")
        return None

if __name__ == "__main__":
    disk_image_path = "D:/PC-MUS-001.E01"   # Dummy path for a .E01 file
    disk_image = open_disk_image(disk_image_path)

    if disk_image:
        print("Disk image loaded and ready for further processing.")

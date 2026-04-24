import urllib.request
import os

os.makedirs('models/yolo', exist_ok=True)

urls = {
    'yolov3-tiny.weights': 'https://pjreddie.com/media/files/yolov3-tiny.weights',
    'yolov3-tiny.cfg': 'https://raw.githubusercontent.com/pjreddie/darknet/master/cfg/yolov3-tiny.cfg',
    'coco.names': 'https://raw.githubusercontent.com/pjreddie/darknet/master/data/coco.names'
}

for name, url in urls.items():
    path = os.path.join('models/yolo', name)
    if not os.path.exists(path):
        print(f"Downloading {name}...")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response, open(path, 'wb') as out_file:
            out_file.write(response.read())
        print(f"{name} downloaded.")

print("All files downloaded.")

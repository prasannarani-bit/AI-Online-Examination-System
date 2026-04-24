import cv2
import numpy as np
import base64
import os

class ProctorAgent:
    def __init__(self):
        # Load pre-trained Haar cascades for face detection
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
        # Load YOLO for phone detection
        yolo_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models', 'yolo')
        weights_path = os.path.join(yolo_dir, 'yolov3-tiny.weights')
        cfg_path = os.path.join(yolo_dir, 'yolov3-tiny.cfg')
        names_path = os.path.join(yolo_dir, 'coco.names')

        try:
            self.net = cv2.dnn.readNet(weights_path, cfg_path)
            with open(names_path, 'r') as f:
                self.classes = [line.strip() for line in f.readlines()]
            self.output_layers = self.net.getUnconnectedOutLayersNames()
            self.yolo_loaded = True
        except Exception as e:
            print(f"Error loading YOLO: {e}")
            self.yolo_loaded = False

        # --- Consecutive-frame counters ---
        # A violation is only confirmed after CONFIRM_THRESHOLD consecutive bad frames.
        # 2 frames = ~10s of sustained bad behaviour at 5s capture interval.
        # This filters out single-frame jitter without missing real cheating.
        self.CONFIRM_THRESHOLD = 1
        self._no_face_streak = 0
        self._multi_face_streak = 0
        self._phone_streak = 0

    def analyze_frame(self, base64_image):
        """
        Receives base64 image from frontend, analyzes for faces and phones.
        Returns multiple_faces, no_face, phone_detected flags.
        """
        try:
            # Decode base64
            img_data = base64.b64decode(base64_image.split(',')[1])
            np_arr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if img is None:
                return False, False, False

            # Convert to grayscale for Haar face detection
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=6,
                minSize=(40, 40)
            )

            num_faces = len(faces)
            raw_no_face = (num_faces == 0)
            
            # Start multiple face check with Haar results
            raw_multiple_faces = (num_faces > 1)
            raw_phone = False
            num_persons_yolo = 0

            # Detect with YOLO (more reliable for phones and body detection)
            if self.yolo_loaded:
                blob = cv2.dnn.blobFromImage(img, 0.00392, (320, 320), (0, 0, 0), True, crop=False)
                self.net.setInput(blob)
                outs = self.net.forward(self.output_layers)

                for out in outs:
                    for detection in out:
                        scores = detection[5:]
                        class_id = np.argmax(scores)
                        confidence = scores[class_id]
                        
                        # Detect People and Phones
                        if confidence > 0.45:
                            class_name = self.classes[class_id]
                            if class_name == 'person':
                                num_persons_yolo += 1
                            elif class_name == 'cell phone':
                                raw_phone = True

            # If YOLO detects more than 1 person, it's a multi-face violation even if Haar misses them
            if num_persons_yolo > 1:
                raw_multiple_faces = True
            
            # If Haar detects 0 faces AND YOLO detects 0 persons, it's definitely a "No Face" violation
            if raw_no_face and num_persons_yolo > 0:
                # Student is there but face-detector missed them (maybe looking down)
                # In strict mode, we might still want to warn, but let's be fair
                raw_no_face = False

            # --- Consecutive-frame streak logic ---
            if raw_no_face:
                self._no_face_streak += 1
            else:
                self._no_face_streak = 0

            if raw_multiple_faces:
                self._multi_face_streak += 1
            else:
                self._multi_face_streak = 0

            if raw_phone:
                self._phone_streak += 1
            else:
                self._phone_streak = 0

            confirmed_no_face      = self._no_face_streak   >= self.CONFIRM_THRESHOLD
            confirmed_multi_faces  = self._multi_face_streak >= self.CONFIRM_THRESHOLD
            confirmed_phone        = self._phone_streak      >= self.CONFIRM_THRESHOLD

            # Reset streak after confirming so we don't log repeatedly for the same event
            if confirmed_no_face:
                self._no_face_streak = 0
            if confirmed_multi_faces:
                self._multi_face_streak = 0
            if confirmed_phone:
                self._phone_streak = 0

            return confirmed_multi_faces, confirmed_no_face, confirmed_phone

        except Exception as e:
            # On any processing error, do NOT flag anything — the student should not
            # be penalised for a transient decoding/hardware error.
            print(f"Proctoring error: {e}")
            return False, False, False

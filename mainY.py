from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS
import cv2
import os
from datetime import datetime
import time
import base64
import threading
import psycopg2
from ultralytics import YOLO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
CORS(app)

# Folder configurations
UPLOAD_FOLDER = 'uploads'
VIOLATION_FOLDER = 'violations'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(VIOLATION_FOLDER, exist_ok=True)

# Load YOLOv8 model
model = YOLO('best.pt')  # Replace with your model
# Konfigurasi tracker (opsional, tergantung kebutuhan)
model.tracker = 'botsort.yaml'  # Pastikan model mendukung pelacakan, bisa ganti ke 'bytetrack.yaml'

# Custom class names
custom_classes = ["eating", "sleep", "playing game phone"]

# Database configuration
DB_HOST = 'localhost'
DB_NAME = 'yolov8'
DB_USER = 'postgres'
DB_PASSWORD = 'rajawalilmg'

def connect_db():
    return psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD)

def create_table_if_not_exists():
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id SERIAL PRIMARY KEY,
            frame_time TIMESTAMP,
            frame_number INT,
            object_name TEXT,
            confidence FLOAT,
            tracking_id INT,  -- Tambah kolom untuk tracking_id
            timestamp TIMESTAMP,
            image_path TEXT 
        )
        """)
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error creating table: {e}")

def save_detection_to_db(frame_time, frame_number, confidence, detected_objects, frame):
    try:
        conn = connect_db()
        cursor = conn.cursor()

        for obj in detected_objects:
            # Simpan gambar ke folder
            image_filename = f"violation_{frame_number}_{obj.get('tracking_id', 0)}_{int(time.time())}.jpg"
            image_path = os.path.join(VIOLATION_FOLDER, image_filename)
            cv2.imwrite(image_path, frame)  # Simpan gambar

            query = """
            INSERT INTO detections (frame_time, frame_number, object_name, confidence, tracking_id, timestamp, image_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (
                frame_time,
                frame_number,
                obj['name'],
                obj['confidence'],
                obj.get('tracking_id', None),  # Simpan tracking_id
                datetime.now(),
                image_path
            ))

        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error saving to database: {e}")

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/url')
def url_page():
    return send_from_directory('templates', 'url.html')

violators_logged = set()  # Menyimpan tracking_id yang sudah pernah disimpan
last_detection_time = {}  # Menyimpan waktu terakhir deteksi per tracking_id

def process_video(video_path):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)  # Ambil nilai FPS dari video
    frame_number = 0
    active_ids = set()

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret or frame is None or frame.size == 0:
            print("[DEBUG] Frame kosong atau akhir video tercapai. Menghentikan proses.")
            break


        frame_number += 1

        # Hanya proses 1 frame per detik
        if frame_number % int(fps) != 0:
            continue

        frame_time = datetime.now().strftime("%H:%M:%S")
        current_time = time.time()
        current_ids = set()

        results = model.track(frame, persist=True)

        for box in results[0].boxes:
            x1, y1, x2, y2, confidence, class_id = box.xyxy[0].tolist() + [box.conf[0].item(), box.cls[0].item()]
            tracking_id = int(box.id[0]) if box.id is not None else -1
            object_name = model.names[int(class_id)]

            if confidence < 0.5:
                print(f"[DEBUG] Confidence rendah ({confidence:.2f}), skip.")
                continue


            print(f"Detected: {object_name}, Tracking ID: {tracking_id}, Confidence: {confidence:.2f}")

            if object_name not in custom_classes:
                continue

            if tracking_id in last_detection_time:
                if current_time - last_detection_time[tracking_id] < 5:
                    print(f"[DEBUG] Skipping redundant detection for Tracking ID: {tracking_id}")
                    continue

            if tracking_id in violators_logged:
                print(f"[DEBUG] Tracking ID {tracking_id} sudah tersimpan sebelumnya. Lewati.")
                continue

            last_detection_time[tracking_id] = current_time
            current_ids.add(tracking_id)

            # Buat copy frame khusus untuk log (hanya kotak objek ini)
            log_frame = frame.copy()
            cv2.rectangle(log_frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            label = f"{object_name} ID:{tracking_id} {confidence:.2f}"
            cv2.putText(log_frame, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # Gambar juga di frame utama untuk Live Preview
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            cv2.putText(frame, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # Simpan ke database
            save_detection_to_db(
                frame_time=frame_time,
                frame_number=frame_number,
                confidence=confidence,
                detected_objects=[{
                    'name': object_name,
                    'confidence': confidence,
                    'tracking_id': tracking_id
                }],
                frame=log_frame
            )

            # Tambahkan ke list pelanggar yang sudah disimpan
            violators_logged.add(tracking_id)

            # Simpan gambar & kirim ke frontend
            image_path = os.path.join(VIOLATION_FOLDER, f"violation_{frame_number}_{tracking_id}_{int(time.time())}.jpg")
            cv2.imwrite(image_path, log_frame)

            socketio.emit('violation_alert', {
                'message': 'Pelanggaran terdeteksi! Harap perhatikan!',
                'frame_time': frame_time,
                'frame_number': frame_number,
                'object_name': object_name,
                'tracking_id': tracking_id,
                'confidence': confidence,
                'image_path': f"/violations/{os.path.basename(image_path)}"
            })

        # Cek ID yang hilang
        missing_ids = active_ids - current_ids
        for tracking_id in missing_ids:
            print(f"[DEBUG] Tracking ID {tracking_id} no longer detected.")
            socketio.emit('object_lost', {
                'message': f'Objek dengan ID {tracking_id} tidak lagi terdeteksi.',
                'frame_time': frame_time,
                'frame_number': frame_number,
                'tracking_id': tracking_id
            })
            save_detection_to_db(
                frame_time=frame_time,
                frame_number=frame_number,
                confidence=0.0,
                detected_objects=[{
                    'name': 'lost_object',
                    'confidence': 0.0,
                    'tracking_id': tracking_id
                }],
                frame=frame
            )

        active_ids = current_ids

        # Hapus tracking_id yang expired
        expired_ids = [tid for tid, t in last_detection_time.items() if current_time - t > 10]
        for tid in expired_ids:
            print(f"[DEBUG] Removing expired Tracking ID: {tid}")
            del last_detection_time[tid]

        # Kirim frame ke frontend
        _, buffer = cv2.imencode('.jpg', frame)
        frame_data = base64.b64encode(buffer).decode('utf-8')
        socketio.emit('video_frame', {'frame': frame_data, 'frame_number': frame_number})

        cv2.waitKey(1)

    print("[INFO] Video processing selesai. Melepaskan video capture.")
    cap.release()


    socketio.emit('video_done', {
        'message': 'Proses deteksi dan pelacakan video selesai.',
        'frame_time': frame_time,
        'frame_number': frame_number
    })


@app.route('/upload_video', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['video']
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    thread = threading.Thread(target=process_video, args=(file_path,))
    thread.start()

    return jsonify({"message": "Video uploaded successfully with object tracking", "filename": file.filename})


# Konstanta
VIOLATION_FOLDER = "violations"
custom_classes = {"eating", "sleep", "playing game phone"}  # Sesuaikan dengan kelas yang ingin dideteksi

# Pastikan folder pelanggaran ada
os.makedirs(VIOLATION_FOLDER, exist_ok=True)

def open_stream(url, retries=5, delay=5):
    for i in range(retries):
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if cap.isOpened():
            print("Stream berhasil dibuka.")
            return cap
        print(f"Retry {i+1}/{retries}: Stream gagal, mencoba lagi dalam {delay} detik...")
        time.sleep(delay)
    print("Stream gagal dibuka setelah beberapa kali percobaan.")
    return None

def process_stream(stream_url, max_duration=600):  # 600 detik = 10 menit
    start_time = time.time()
    frame_number = 0
    active_ids = set()

    while True:
        if time.time() - start_time > max_duration:
            print("Durasi maksimal tercapai. Menghentikan proses.")
            break

        cap = open_stream(stream_url)  # <--- tambahkan baris ini!
        if not cap:
            print("Gagal membuka stream, menunggu 10 detik sebelum mencoba lagi...")
            time.sleep(10)
            continue

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print("Stream berakhir atau gagal dibaca. Mencoba reconnect...")
                cap.release()
                time.sleep(5)  # Delay sebelum reconnect
                break  # keluar loop dalam untuk reconnect ulang stream

            frame_number += 1
            frame_time = datetime.now().strftime("%H:%M:%S")
            current_time = time.time()
            current_ids = set()

            results = model.track(frame, persist=True)

            for box in results[0].boxes:
                x1, y1, x2, y2, confidence, class_id = box.xyxy[0].tolist() + [box.conf[0].item(), box.cls[0].item()]
                tracking_id = int(box.id[0]) if box.id is not None else -1
                object_name = model.names[int(class_id)]

                if confidence < 0.5:
                    print(f"[DEBUG] Confidence rendah ({confidence:.2f}), skip.")
                    continue

                print(f"Detected: {object_name}, Tracking ID: {tracking_id}, Confidence: {confidence:.2f}")

                if object_name not in custom_classes:
                    continue

                if tracking_id in last_detection_time:
                    if current_time - last_detection_time[tracking_id] < 5:
                        print(f"[DEBUG] Skipping redundant detection for Tracking ID: {tracking_id}")
                        continue

                if tracking_id in violators_logged:
                    print(f"[DEBUG] Tracking ID {tracking_id} sudah tersimpan sebelumnya. Lewati.")
                    continue

                last_detection_time[tracking_id] = current_time
                current_ids.add(tracking_id)

                # Buat copy frame khusus untuk log (hanya kotak objek ini)
                log_frame = frame.copy()
                cv2.rectangle(log_frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                label = f"{object_name} ID:{tracking_id} {confidence:.2f}"
                cv2.putText(log_frame, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                # Gambar juga di frame utama untuk Live Preview
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                cv2.putText(frame, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                # Simpan ke DB
                save_detection_to_db(
                    frame_time=frame_time,
                    frame_number=frame_number,
                    confidence=confidence,
                    detected_objects=[{
                        'name': object_name,
                        'confidence': confidence,
                        'tracking_id': tracking_id
                    }],
                    frame=log_frame
                )

                violators_logged.add(tracking_id)

                image_path = os.path.join(VIOLATION_FOLDER, f"violation_{frame_number}_{tracking_id}_{int(time.time())}.jpg")
                cv2.imwrite(image_path, log_frame)

                socketio.emit('violation_alert', {
                    'message': 'Pelanggaran terdeteksi! Harap perhatikan!',
                    'frame_time': frame_time,
                    'frame_number': frame_number,
                    'object_name': object_name,
                    'tracking_id': tracking_id,
                    'confidence': confidence,
                    'image_path': f"/violations/{os.path.basename(image_path)}"
                })

            # Cek ID yang hilang
            missing_ids = active_ids - current_ids
            for tracking_id in missing_ids:
                socketio.emit('object_lost', {
                    'message': f'Objek dengan ID {tracking_id} tidak lagi terdeteksi.',
                    'frame_time': frame_time,
                    'frame_number': frame_number,
                    'tracking_id': tracking_id
                })
                save_detection_to_db(
                    frame_time=frame_time,
                    frame_number=frame_number,
                    confidence=0.0,
                    detected_objects=[{
                        'name': 'lost_object',
                        'confidence': 0.0,
                        'tracking_id': tracking_id
                    }],
                    frame=frame
                )

            active_ids = current_ids

            # Bersihkan tracking ID yang tidak aktif
            expired_ids = [tid for tid, t in last_detection_time.items() if current_time - t > 10]
            for tid in expired_ids:
                del last_detection_time[tid]

            # Kirim frame ke frontend
            _, buffer = cv2.imencode('.jpg', frame)
            frame_data = base64.b64encode(buffer).decode('utf-8')
            socketio.emit('video_frame', {'frame': frame_data, 'frame_number': frame_number})

            time.sleep(0.05)

@app.route("/detect_from_stream", methods=["POST"])
def detect_from_stream():
    data = request.get_json()
    stream_url = data.get("stream_url")

    if not stream_url:
        return jsonify({"error": "No stream URL provided"}), 400

    thread = threading.Thread(target=process_stream, args=(stream_url,))
    thread.start()

    return jsonify({"message": "Processing live stream", "stream_url": stream_url})

@app.route('/violations/<filename>')
def get_violation_image(filename):
    return send_from_directory(VIOLATION_FOLDER, filename)


if __name__ == '__main__':
    create_table_if_not_exists()
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)

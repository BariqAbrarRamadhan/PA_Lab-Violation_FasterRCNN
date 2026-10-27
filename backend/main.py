from flask import Flask, request, jsonify, send_from_directory, Response
from flask_socketio import SocketIO
from flask_cors import CORS
import cv2
import os
from datetime import datetime
from pathlib import Path
import time
import base64
import threading
import torch
import torchvision
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision import transforms
from deep_sort_realtime.deepsort_tracker import DeepSort
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from db_adapter import get_db_adapter
from stream_manager import StreamManager
from perf_logger import PerfLogger

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables dari file .env di root proyek
load_dotenv(BASE_DIR / '.env')

# pip install deep-sort-realtime supabase python-dotenv

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
CORS(app)

# Allowed video extensions & max file size (100MB)
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv'}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Folder configurations
UPLOAD_FOLDER = str(BASE_DIR / 'uploads')
VIOLATION_FOLDER = str(BASE_DIR / 'violations')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(VIOLATION_FOLDER, exist_ok=True)

# ==========================================
# KONFIGURASI MODEL FASTER R-CNN
# ==========================================
device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')
print(f"Using device: {device}")

# Kelas Custom — HARUS SAMA PERSIS dengan urutan class_map di notebook training!
# Notebook: {'background': 0, 'playing game phone': 1, 'sleep': 2, 'eating': 3}
custom_classes = ["background", "playing game phone", "sleep", "eating"]

# Load Model
def get_model(num_classes):
    # model = torchvision.models.detection.fasterrcnn_resnet50_fpn(weights='DEFAULT')
    model = torchvision.models.detection.fasterrcnn_resnet50_fpn_v2(weights=None)
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
    return model

# Model lama tersedia di models/legacy/best_model_16.pth
MODEL_PATH = str(BASE_DIR / 'models' / 'best_model-gabungan6.pth')
num_classes = len(custom_classes) 
model = get_model(num_classes)

if os.path.exists(MODEL_PATH):
    model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
    print("Model weights loaded successfully.")
else:
    print("WARNING: Model path not found. Please train first.")

model.to(device)
model.eval()

# Tracker diinisialisasi di dalam fungsi proses video agar ter-reset tiap video

# ==========================================
# DATABASE CONFIG (FLEXIBLE: SUPABASE / POSTGRESQL)
# ==========================================
# Pemilihan database dikontrol oleh variabel DB_PROVIDER di file .env:
#   DB_PROVIDER=supabase    -> menggunakan Supabase (default)
#   DB_PROVIDER=postgresql  -> menggunakan PostgreSQL self-hosted
try:
    db = get_db_adapter()
except Exception as e:
    print(f"[DB] FATAL: Gagal menginisialisasi database adapter — {e}")
    db = None

def save_detection_to_db(frame_time, frame_number, confidence, detected_objects, frame, image_filename):
    # Simpan gambar sementara ke lokal (selalu, sebagai fallback)
    local_image_path = os.path.join(VIOLATION_FOLDER, image_filename)
    cv2.imwrite(local_image_path, frame)

    # Default ke URL lokal
    used_image_url = f"/violations/{image_filename}"

    if db is None:
        print("[DB] WARNING: Database adapter tidak tersedia. Data tidak disimpan ke DB.")
        return used_image_url

    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        full_timestamp_str = f"{today_str} {frame_time}"

        # Upload gambar via adapter (Supabase Storage atau lokal, tergantung provider)
        print(f"[DB] Menyimpan gambar: {image_filename}")
        used_image_url = db.upload_image(image_filename, local_image_path)

        for obj in detected_objects:
            data = {
                "frame_time": full_timestamp_str,
                "frame_number": frame_number,
                "object_name": obj['name'],
                "confidence": obj['confidence'],
                "tracking_id": obj.get('tracking_id', None),
                "timestamp": datetime.now().isoformat(),
                "image_path": used_image_url
            }
            db.insert_detection(data)

    except Exception as e:
        print(f"[DB] Error menyimpan ke database: {e}. Menggunakan penyimpanan lokal untuk frontend.")
        used_image_url = f"/violations/{image_filename}"

    return used_image_url

@app.route('/')
def index():
    return send_from_directory(str(BASE_DIR / 'templates'), 'index.html')

@app.route('/url')
def url_page():
    return send_from_directory(str(BASE_DIR / 'templates'), 'url.html')

@app.route('/history')
def history_page():
    return send_from_directory(str(BASE_DIR / 'templates'), 'history.html')

# State Global (untuk upload video)
violators_logged = set()
last_detection_time = {}
state_lock = threading.Lock()
stop_event = threading.Event()  # Untuk menghentikan proses deteksi video upload
current_thread = None  # Referensi ke thread deteksi upload video aktif

# ==========================================
# STREAM MANAGER (untuk live stream RTSP/HTTP)
# ==========================================
stream_manager = StreamManager(
    model=model,
    device=device,
    custom_classes=custom_classes,
    socketio=socketio,
    save_detection_cb=save_detection_to_db
)
perf_logger = PerfLogger(interval_seconds=1.0)

def process_video_logic(cap, source_name="video"):
    global violators_logged, last_detection_time
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0 or fps is None: fps = 30
    
    frame_number = 0
    active_ids = set()
    
    # Inisialisasi tracker baru untuk setiap video/stream agar deteksi lama tidak terbawa
    tracker = DeepSort(max_age=30, n_init=3)

    # Transform pipeline HARUS sama dengan get_val_transform() di notebook training:
    # Notebook: ToTensorV2() -> .to(float32) / 255.0  ≡  transforms.ToTensor() (range [0,1])
    # Input: numpy RGB uint8  ->  float32 tensor [0,1]
    transform = transforms.Compose([
        transforms.ToTensor()  # Handles uint8 HWC RGB -> float32 CHW [0,1]
    ])

    print(f"[INFO] Processing started. FPS Asli: {fps}")

    while cap.isOpened():
        # Cek apakah ada permintaan stop
        if stop_event.is_set():
            print("[INFO] Deteksi dihentikan oleh user.")
            break

        ret, frame = cap.read()
        if not ret:
            print("[INFO] Video ended (Selesai).")
            break

        frame_number += 1
        
        # --- OPTIMASI 2: SKIP FRAME EKSTREM ---
        # Hanya proses 1 frame setiap 30 frame (kira-kira 1 detik sekali)
        # Jika masih lambat, ganti 30 menjadi 60 atau 90
        skip_rate = int(fps) * 5  # Proses setiap 5 detik sekali video
        if frame_number % skip_rate != 0: 
             continue

        frame_time_str = datetime.now().strftime("%H:%M:%S")
        current_time = time.time()
        
        # 1. Preprocess — SAMA dengan pipeline notebook (val_transform: ToTensorV2 / 255.0)
        # OpenCV baca dalam BGR, model dilatih dengan RGB → wajib konversi
        start_preprocess = time.time()
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # uint8 HWC RGB
        img_tensor = transform(frame_rgb).to(device)        # float32 CHW [0,1]
        end_preprocess = time.time()

        # 2. Inference
        start_infer = time.time()
        with torch.no_grad():
            prediction = model([img_tensor])[0]
        end_infer = time.time()
        
        infer_ms = (end_infer - start_infer) * 1000
        
        # 3. Filter deteksi (koordinat langsung dari frame asli, tanpa perlu scale balik)
        detections_for_tracker = []
        
        boxes = prediction['boxes'].cpu().numpy()
        scores = prediction['scores'].cpu().numpy()
        labels = prediction['labels'].cpu().numpy()
        
        class_counts = {} 
        
        for i in range(len(boxes)):
            score = scores[i]
            label_id = labels[i]
            
            if score < 0.6: continue 

            if label_id >= len(custom_classes): continue
            class_name = custom_classes[label_id]
            if class_name == "background": continue 

            class_counts[class_name] = class_counts.get(class_name, 0) + 1

            # Koordinat sudah dalam skala frame asli (tidak ada resize)
            x1, y1, x2, y2 = boxes[i]
            w_box = x2 - x1
            h_box = y2 - y1
            
            detections_for_tracker.append(([int(x1), int(y1), int(w_box), int(h_box)], score, class_name))

        count_str = ", ".join([f"{v} {k}" for k, v in class_counts.items()])
        if not count_str: count_str = "no detections"
        print(f"Frame {frame_number}: {count_str}, Waktu Proses: {infer_ms:.1f}ms")

        # 4. Update Tracker (Pakai frame asli untuk visualisasi kualitas tinggi)
        tracks = tracker.update_tracks(detections_for_tracker, frame=frame)
        current_ids = set()

        # --- PASS 1: Gambar SEMUA bbox ke frame utama (live preview) ---
        confirmed_tracks = [t for t in tracks if t.is_confirmed()]
        for track in confirmed_tracks:
            tracking_id = track.track_id
            ltrb = track.to_ltrb()
            x1, y1, x2, y2 = map(int, ltrb)
            object_name = track.get_det_class()
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"{object_name} ID:{tracking_id}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # --- PASS 2: Kumpulkan pelanggaran baru dalam frame ini ---
        # Buat satu frame gabungan dengan SEMUA bbox untuk disimpan ke DB
        new_violations = []   # list of (tracking_id, object_name, confidence)
        for track in confirmed_tracks:
            tracking_id = track.track_id
            object_name = track.get_det_class()
            confidence  = track.get_det_conf()
            if confidence is None: confidence = 0.0

            current_ids.add(tracking_id)

            # Cek cooldown (5 detik)
            if tracking_id in last_detection_time:
                if current_time - last_detection_time[tracking_id] < 5:
                    continue

            # Cek apakah sudah pernah dilog
            if tracking_id in violators_logged:
                print(f"[DEBUG] Tracking ID {tracking_id} sudah dilog. Skip DB.")
                last_detection_time[tracking_id] = current_time
                continue

            new_violations.append((tracking_id, object_name, float(confidence)))
            last_detection_time[tracking_id] = current_time

        # --- PASS 3: Simpan SATU gambar gabungan jika ada pelanggaran baru ---
        if new_violations:
            # Frame ini sudah berisi SEMUA bbox dari Pass 1
            combined_filename = f"violation_{frame_number}_{int(time.time())}.jpg"
            detected_objects = [
                {'name': name, 'confidence': conf, 'tracking_id': tid}
                for tid, name, conf in new_violations
            ]
            used_image_url = save_detection_to_db(
                frame_time=frame_time_str,
                frame_number=frame_number,
                confidence=max(conf for _, _, conf in new_violations),
                detected_objects=detected_objects,
                frame=frame,  # <--- Satu frame berisi SEMUA bbox
                image_filename=combined_filename
            )
            for tid, name, conf in new_violations:
                violators_logged.add(tid)
                socketio.emit('violation_alert', {
                    'message': 'Pelanggaran terdeteksi!',
                    'frame_time': frame_time_str,
                    'frame_number': frame_number,
                    'object_name': name,
                    'tracking_id': tid,
                    'confidence': conf,
                    'image_path': used_image_url
                })

        # Handle Lost Objects (Objek yang keluar dari kamera)
        missing_ids = active_ids - current_ids
        for tracking_id in missing_ids:
            print(f"[DEBUG] Tracking ID {tracking_id} no longer detected (hilang).")
            
            # Beritahu Frontend (Web) kalau objek hilang
            socketio.emit('object_lost', {
                'message': f'Objek ID {tracking_id} hilang.',
                'tracking_id': tracking_id
            })
            
            # (Opsional) Simpan ke DB kalau objek hilang
            # lost_filename = f"lost_{frame_number}_{tracking_id}_{int(time.time())}.jpg"
            # save_detection_to_db(
            #     frame_time=frame_time_str,
            #     frame_number=frame_number,
            #     confidence=0.0,
            #     detected_objects=[{
            #         'name': 'lost_object',
            #         'confidence': 0.0,
            #         'tracking_id': tracking_id
            #     }],
            #     frame=frame,
            #     image_filename=lost_filename
            # )
        
        active_ids = current_ids

        # Cleanup expired IDs
        expired_ids = [tid for tid, t in last_detection_time.items() if current_time - t > 10]
        for tid in expired_ids:
            del last_detection_time[tid]

        # Kirim Frame ke Frontend
        _, buffer = cv2.imencode('.jpg', frame)
        frame_data = base64.b64encode(buffer).decode('utf-8')
        socketio.emit('video_frame', {'frame': frame_data, 'frame_number': frame_number})

        # cv2.waitKey(1)

    cap.release()
    socketio.emit('video_done', {'message': 'Proses selesai.'})


def process_video_thread(video_path):
    cap = cv2.VideoCapture(video_path)
    process_video_logic(cap)

@app.route('/upload_video', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['video']
    
    # Validasi nama file
    if file.filename == '' or file.filename is None:
        return jsonify({"error": "No file selected"}), 400
    
    # Validasi tipe file
    if not allowed_file(file.filename):
        return jsonify({"error": "Tipe file tidak didukung. Gunakan: MP4, AVI, MOV, MKV, WMV, FLV"}), 400
    
    # Sanitasi nama file untuk keamanan
    safe_filename = secure_filename(file.filename)
    file_path = os.path.join(UPLOAD_FOLDER, safe_filename)
    file.save(file_path)
    
    # Validasi ukuran file setelah disimpan
    if os.path.getsize(file_path) > MAX_FILE_SIZE:
        os.remove(file_path)
        return jsonify({"error": "Ukuran file melebihi batas 100MB"}), 400

    # Hentikan proses deteksi sebelumnya jika ada
    global current_thread
    stop_event.set()
    if current_thread and current_thread.is_alive():
        current_thread.join(timeout=5)
    stop_event.clear()

    global violators_logged, last_detection_time
    with state_lock:
        violators_logged = set()
        last_detection_time = {}

    thread = threading.Thread(target=process_video_thread, args=(file_path,))
    thread.start()
    current_thread = thread

    return jsonify({"message": "Video uploaded, processing with Faster R-CNN", "filename": safe_filename})


# ==========================================
# STREAM URL DETECTION (via StreamManager)
# ==========================================

@app.route('/detect_from_stream', methods=['POST'])
def detect_from_stream():
    """Mulai deteksi dari live stream RTSP/HTTP menggunakan StreamManager."""
    data = request.get_json()
    stream_url = data.get("stream_url") if data else None

    if not stream_url:
        return jsonify({"error": "No stream URL provided"}), 400

    # Hentikan stream sebelumnya jika ada
    if stream_manager.is_running():
        perf_logger.stop()
        stream_manager.stop()

    # Mulai stream baru + performance logging
    stream_manager.start(stream_url)
    perf_logger.start(metrics_fn=stream_manager.get_metrics)

    return jsonify({
        "message": "Live stream dimulai dengan Faster R-CNN",
        "stream_url": stream_url
    })


@app.route('/stop_stream', methods=['POST'])
def stop_stream():
    """Hentikan live stream yang sedang berjalan."""
    if stream_manager.is_running():
        perf_logger.stop()
        stream_manager.stop()
        socketio.emit('video_done', {'message': 'Stream dihentikan oleh user.'})
        return jsonify({"message": "Stream berhasil dihentikan."})
    return jsonify({"message": "Tidak ada stream aktif."})


@app.route('/stream_status', methods=['GET'])
def stream_status():
    """Return status dan metrik stream yang sedang aktif."""
    metrics = stream_manager.get_metrics()
    metrics["is_running"] = stream_manager.is_running()
    log_path = perf_logger.get_log_path()
    metrics["log_file"] = log_path.name if log_path else None
    return jsonify(metrics)


@app.route('/video_feed')
def video_feed():
    """
    MJPEG stream endpoint.
    Lebih efisien dari base64 via SocketIO untuk live preview.
    Frontend: <img src="/video_feed">
    """
    def generate():
        while True:
            frame_bytes = stream_manager.get_latest_frame_bytes()
            if frame_bytes is None:
                # Kirim placeholder kecil jika belum ada frame
                time.sleep(0.1)
                continue
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n'
                + frame_bytes +
                b'\r\n'
            )
            time.sleep(0.033)  # ~30 fps max untuk MJPEG feed

    return Response(
        generate(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/stop_detection', methods=['POST'])
def stop_detection():
    """Hentikan deteksi video upload yang sedang berjalan."""
    stop_event.set()
    return jsonify({"message": "Proses deteksi video dihentikan."})


# ==========================================
# API: PERFORMANCE LOG (untuk riset)
# ==========================================
@app.route('/api/stream_metrics/logs', methods=['GET'])
def list_perf_logs():
    """Daftar semua file log performa CSV yang tersedia."""
    logs = perf_logger.list_logs()
    return jsonify({"logs": logs, "count": len(logs)})


@app.route('/api/stream_metrics/export', methods=['GET'])
def export_perf_log():
    """Download file log CSV performa stream (file terbaru / berdasarkan filename)."""
    filename = request.args.get('filename')
    if filename:
        # Sanitasi: pastikan hanya ambil file dari folder logs/
        safe_name = os.path.basename(filename)
        log_path = os.path.join(str(BASE_DIR / 'logs'), safe_name)
    else:
        # Default: file terbaru
        current_log = perf_logger.get_log_path()
        if current_log is None:
            # Cari file terbaru dari folder
            logs = perf_logger.list_logs()
            if not logs:
                return jsonify({"error": "Belum ada file log performa."}), 404
            log_path = logs[0]['path']
        else:
            log_path = str(current_log)

    if not os.path.exists(log_path):
        return jsonify({"error": f"File log tidak ditemukan: {log_path}"}), 404

    return send_from_directory(
        directory=os.path.dirname(os.path.abspath(log_path)),
        path=os.path.basename(log_path),
        as_attachment=True,
        mimetype='text/csv'
    )


# ==========================================
# API: RIWAYAT DETEKSI (untuk halaman History)
# ==========================================
@app.route('/api/detections', methods=['GET'])
def get_detections():
    """Ambil riwayat deteksi dari database (Supabase atau PostgreSQL) dengan pagination."""
    if db is None:
        return jsonify({"error": "Database adapter tidak tersedia."}), 503
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        object_filter = request.args.get('object_name', None)
        date_filter = request.args.get('date', None)

        data, count = db.get_detections(
            page=page,
            per_page=per_page,
            object_filter=object_filter,
            date_filter=date_filter,
        )

        return jsonify({
            "data": data,
            "count": count,
            "page": page,
            "per_page": per_page
        })
    except Exception as e:
        print(f"Error fetching detections: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/detections/stats', methods=['GET'])
def get_detection_stats():
    """Ambil statistik deteksi untuk dashboard (Supabase atau PostgreSQL)."""
    if db is None:
        return jsonify({"error": "Database adapter tidak tersedia."}), 503
    try:
        detections = db.get_all_detections_stats()

        # Hitung per jenis pelanggaran
        stats = {}
        for det in detections:
            name = det.get("object_name", "unknown")
            stats[name] = stats.get(name, 0) + 1

        return jsonify({
            "total": len(detections),
            "by_type": stats,
            "data": detections
        })
    except Exception as e:
        print(f"Error fetching stats: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/violations/<filename>')
def get_violation_image(filename):
    return send_from_directory(VIOLATION_FOLDER, filename)


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
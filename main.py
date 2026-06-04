from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS
import cv2
import os
from datetime import datetime
import time
import base64
import threading
import torch
import torchvision
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision import transforms
from deep_sort_realtime.deepsort_tracker import DeepSort
from supabase import create_client, Client
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# Load environment variables dari file .env
load_dotenv()

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
UPLOAD_FOLDER = 'uploads'
VIOLATION_FOLDER = 'violations'
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

MODEL_PATH = 'best_model (16).pth'
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
# DATABASE CONFIG (SUPABASE)
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
if not SUPABASE_URL or not SUPABASE_KEY:
    print("WARNING: SUPABASE_URL atau SUPABASE_KEY belum diset di .env!")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def save_detection_to_db(frame_time, frame_number, confidence, detected_objects, frame, image_filename):
    # Simpan gambar sementara ke lokal
    local_image_path = os.path.join(VIOLATION_FOLDER, image_filename)
    cv2.imwrite(local_image_path, frame)
    
    # Default to local URL
    used_image_url = f"/violations/{image_filename}"

    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        full_timestamp_str = f"{today_str} {frame_time}" 
        
        # Upload ke Supabase Storage (bucket "violations")
        print(f"Uploading image to Supabase Storage: {image_filename}")
        with open(local_image_path, "rb") as f:
            supabase.storage.from_("violations").upload(image_filename, f, {"content-type": "image/jpeg"})
        
        # Dapatkan URL publik dari gambar tersebut
        public_image_url = supabase.storage.from_("violations").get_public_url(image_filename)

        for obj in detected_objects:
            # Simpan log ke Supabase Tabel "detections"
            data = {
                "frame_time": full_timestamp_str,
                "frame_number": frame_number,
                "object_name": obj['name'],
                "confidence": obj['confidence'],
                "tracking_id": obj.get('tracking_id', None),
                "timestamp": datetime.now().isoformat(),
                "image_path": public_image_url
            }
            supabase.table("detections").insert(data).execute()
        
        # Jika berhasil, gunakan public URL
        used_image_url = public_image_url

    except Exception as e:
        print(f"Offline / Error saving to Supabase: {e}. Menggunakan penyimpanan lokal untuk frontend.")
        
    return used_image_url

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/url')
def url_page():
    return send_from_directory('templates', 'url.html')

# State Global
violators_logged = set()
last_detection_time = {}
state_lock = threading.Lock()
stop_event = threading.Event()  # Untuk menghentikan proses deteksi
current_thread = None  # Referensi ke thread deteksi aktif

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
            
            if score < 0.5: continue 

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

        for track in tracks:
            if not track.is_confirmed():
                continue
            
            tracking_id = track.track_id
            ltrb = track.to_ltrb()
            x1, y1, x2, y2 = map(int, ltrb)
            object_name = track.get_det_class()
            confidence = track.get_det_conf() 
            if confidence is None: confidence = 0.0

            # 1. Buat copy frame khusus untuk log (agar hanya berisi kotak untuk objek ini saja)
            log_frame = frame.copy()
            cv2.rectangle(log_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(log_frame, f"{object_name} ID:{tracking_id}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # Gambar juga di frame utama untuk keperluan Live Preview
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"{object_name} ID:{tracking_id}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # Cek duplikat waktu (agar tidak spam)
            if tracking_id in last_detection_time:
                 if current_time - last_detection_time[tracking_id] < 5:
                     # Karena sudah digambar di atas, kita tinggal continue
                     continue
            
            # Cek apakah ID ini sudah disimpan ke database?
            if tracking_id in violators_logged:
                print(f"[DEBUG] Tracking ID {tracking_id} sudah dilog. Skip DB.")
            else:
                # 2. SIMPAN KE DB SETELAH DIGAMBAR
                # Gunakan 'log_frame' yang hanya ada 1 kotak hijau untuk disimpan
                tracking_id_str = str(tracking_id)
                generated_filename = f"violation_{frame_number}_{tracking_id_str}_{int(time.time())}.jpg"
                
                used_image_url = save_detection_to_db(
                    frame_time=frame_time_str,
                    frame_number=frame_number,
                    confidence=float(confidence),
                    detected_objects=[{
                        'name': object_name,
                        'confidence': float(confidence),
                        'tracking_id': tracking_id
                    }],
                    frame=log_frame,  # <--- Frame ini HANYA ada kotak untuk objek ini
                    image_filename=generated_filename 
                )
                violators_logged.add(tracking_id)
                
                # Kirim notifikasi ke Web (dengan public URL Supabase atau fallback lokal)
                socketio.emit('violation_alert', {
                    'message': 'Pelanggaran terdeteksi!',
                    'frame_time': frame_time_str,
                    'frame_number': frame_number,
                    'object_name': object_name,
                    'tracking_id': tracking_id,
                    'confidence': float(confidence),
                    'image_path': used_image_url
                })

            last_detection_time[tracking_id] = current_time
            current_ids.add(tracking_id)

            # cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            # cv2.putText(frame, f"{object_name} ID:{tracking_id}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

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
            lost_filename = f"lost_{frame_number}_{tracking_id}_{int(time.time())}.jpg"
            save_detection_to_db(
                frame_time=frame_time_str,
                frame_number=frame_number,
                confidence=0.0,
                detected_objects=[{
                    'name': 'lost_object',
                    'confidence': 0.0,
                    'tracking_id': tracking_id
                }],
                frame=frame,
                image_filename=lost_filename
            )
        
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
# STREAM URL DETECTION (Faster R-CNN)
# ==========================================
def open_stream(url, retries=5, delay=5):
    """Mencoba membuka stream URL dengan retry mechanism."""
    for i in range(retries):
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if cap.isOpened():
            print("[INFO] Stream berhasil dibuka.")
            return cap
        print(f"[INFO] Retry {i+1}/{retries}: Stream gagal, mencoba lagi dalam {delay} detik...")
        time.sleep(delay)
    print("[ERROR] Stream gagal dibuka setelah beberapa kali percobaan.")
    return None

def process_stream_thread(stream_url, max_duration=600):
    """Proses stream URL menggunakan Faster R-CNN. max_duration default = 10 menit."""
    start_time = time.time()

    while not stop_event.is_set():
        if time.time() - start_time > max_duration:
            print("[INFO] Durasi maksimal stream tercapai. Menghentikan proses.")
            break

        cap = open_stream(stream_url)
        if not cap:
            print("[INFO] Gagal membuka stream, menunggu 10 detik sebelum mencoba lagi...")
            time.sleep(10)
            continue

        # Gunakan logic yang sama dengan process_video_logic
        process_video_logic(cap, source_name="stream")

        if not stop_event.is_set():
            print("[INFO] Stream terputus, mencoba reconnect...")
            time.sleep(5)

    socketio.emit('video_done', {'message': 'Proses stream selesai.'})


@app.route('/detect_from_stream', methods=['POST'])
def detect_from_stream():
    data = request.get_json()
    stream_url = data.get("stream_url") if data else None

    if not stream_url:
        return jsonify({"error": "No stream URL provided"}), 400

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

    thread = threading.Thread(target=process_stream_thread, args=(stream_url,))
    thread.start()
    current_thread = thread

    return jsonify({"message": "Processing live stream with Faster R-CNN", "stream_url": stream_url})


@app.route('/stop_detection', methods=['POST'])
def stop_detection():
    """Endpoint untuk menghentikan proses deteksi yang sedang berjalan."""
    stop_event.set()
    return jsonify({"message": "Proses deteksi dihentikan."})


# ==========================================
# API: RIWAYAT DETEKSI (untuk halaman History)
# ==========================================
@app.route('/api/detections', methods=['GET'])
def get_detections():
    """Ambil riwayat deteksi dari Supabase dengan pagination."""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        object_filter = request.args.get('object_name', None)
        date_filter = request.args.get('date', None)

        offset = (page - 1) * per_page

        query = supabase.table("detections").select("*", count="exact").order("timestamp", desc=True)

        if object_filter:
            query = query.eq("object_name", object_filter)
        if date_filter:
            query = query.gte("timestamp", f"{date_filter}T00:00:00").lte("timestamp", f"{date_filter}T23:59:59")

        query = query.range(offset, offset + per_page - 1)
        result = query.execute()

        return jsonify({
            "data": result.data,
            "count": result.count,
            "page": page,
            "per_page": per_page
        })
    except Exception as e:
        print(f"Error fetching detections: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/detections/stats', methods=['GET'])
def get_detection_stats():
    """Ambil statistik deteksi untuk dashboard."""
    try:
        result = supabase.table("detections").select("*").neq("object_name", "lost_object").execute()
        detections = result.data

        # Hitung per jenis
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
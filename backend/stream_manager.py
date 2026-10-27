"""
stream_manager.py — Live Stream Manager
Mengelola proses live stream RTSP dengan arsitektur multi-thread:
  - Thread Reader   : membaca frame dari source (RTSP/HTTP) tanpa blocking
  - Thread Detector : mengambil frame dari queue, jalankan inferensi Faster R-CNN
  - Frame Buffer    : menyimpan frame hasil untuk MJPEG endpoint
Pemisahan thread ini mencegah cap.read() blocking yang menyebabkan frame drop
dan lag saat stream RTSP aktif.
Mendukung sumber:
  - RTSP (kamera CCTV, ZoneMinder)
  - HTTP/HTTPS video stream
  - Simulasi lokal (FFmpeg RTSP)
"""
import cv2
import time
import threading
import queue
import base64
from datetime import datetime
import torch
from torchvision import transforms
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("[StreamManager] WARNING: psutil tidak tersedia. Monitoring CPU/RAM dinonaktifkan.")
try:
    import pynvml
    pynvml.nvmlInit()
    GPU_AVAILABLE = True
    print("[StreamManager] GPU monitoring aktif (pynvml tersedia).")
except Exception:
    GPU_AVAILABLE = False
    print("[StreamManager] GPU monitoring tidak aktif (pynvml tidak tersedia atau tidak ada GPU NVIDIA).")
class StreamMetrics:
    """Menyimpan metrik performa stream secara thread-safe."""
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {
            "fps_actual": 0.0,
            "inference_ms": 0.0,
            "preprocess_ms": 0.0,
            "frame_number": 0,
            "cpu_percent": 0.0,
            "ram_mb": 0.0,
            "gpu_percent": 0.0,
            "gpu_mem_mb": 0.0,
            "uptime_seconds": 0,
            "detections_count": 0,
            "source_url": "",
            "status": "idle",  # idle | connecting | active | reconnecting | stopped
        }
    def update(self, **kwargs):
        with self._lock:
            self._data.update(kwargs)
    def get(self) -> dict:
        with self._lock:
            return dict(self._data)
class StreamManager:
    """
    Manajemen live stream RTSP/HTTP dengan arsitektur multi-thread.
    Cara pakai:
        sm = StreamManager(model, device, custom_classes, socketio, save_cb)
        sm.start("rtsp://camera-ip/stream")
        # ...
        sm.stop()
    """
    FRAME_QUEUE_SIZE = 2    # Kecil agar selalu ambil frame terbaru
    MAX_RECONNECT   = 10    # Jumlah maksimal percobaan reconnect
    RECONNECT_DELAY = 5     # Detik jeda antar reconnect
    FRAME_QUEUE_SIZE  = 2    # Kecil agar selalu ambil frame terbaru
    MAX_RECONNECT    = 10   # Jumlah maksimal percobaan reconnect
    RECONNECT_DELAY  = 5    # Detik jeda antar reconnect
    # ---- Optimisasi performa CPU (tanpa GPU) ----
    # Resize lebar frame sebelum inferensi. Semakin kecil = semakin cepat.
    # 640 = keseimbangan kecepatan vs akurasi. Ubah ke 480 jika masih lambat.
    INFERENCE_WIDTH  = 640
    # Jalankan inferensi hanya setiap N frame.
    # 1 = setiap frame (paling akurat, paling berat)
    # 3 = setiap 3 frame (lebih ringan, cocok untuk CPU)
    # 5 = setiap 5 frame (ringan, untuk CPU sangat terbatas)
    DETECT_EVERY_N   = 3
    def __init__(self, model, device, custom_classes, socketio, save_detection_cb):
        """
        Args:
            model            : Model Faster R-CNN yang sudah di-load
            device           : torch.device (cpu / cuda)
            custom_classes   : list label kelas
            socketio         : instance Flask-SocketIO
            save_detection_cb: callback fn(frame_time, frame_number, confidence,
                                           detected_objects, frame, image_filename) → image_url
        """
        self.model = model
        self.device = device
        self.custom_classes = custom_classes
        self.socketio = socketio
        self.save_detection_cb = save_detection_cb
        self._stop_event = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._detector_thread: threading.Thread | None = None
        # Queue antara reader dan detector
        self._frame_queue: queue.Queue = queue.Queue(maxsize=self.FRAME_QUEUE_SIZE)
        # Frame buffer untuk MJPEG endpoint (bytes JPEG terbaru)
        self._latest_frame_lock = threading.Lock()
        self._latest_frame_bytes: bytes | None = None
        # State tracking (thread-safe via lock)
        self._state_lock = threading.Lock()
        self._violators_logged: set = set()
        self._last_detection_time: dict = {}
        self.metrics = StreamMetrics()
        # Transform sama persis dengan training pipeline
        self._transform = transforms.Compose([
            transforms.ToTensor()
        ])
        self._start_time: float = 0.0
        self._current_url: str = ""
        # Buffer frame preview terpisah (untuk MJPEG, diupdate oleh reader)
        # Ini memisahkan preview dari siklus inferensi yang lambat
        self._preview_frame_lock = threading.Lock()
        self._preview_frame_bytes: bytes | None = None
    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------
    def start(self, stream_url: str) -> None:
        """Mulai proses stream dari URL yang diberikan."""
        if self.is_running():
            self.stop()
        self._stop_event.clear()
        with self._state_lock:
            self._violators_logged = set()
            self._last_detection_time = {}
        self._current_url = stream_url
        self._start_time = time.time()
        self.metrics.update(source_url=stream_url, status="connecting",
                            frame_number=0, detections_count=0)
        self._reader_thread = threading.Thread(
            target=self._reader_loop, args=(stream_url,), daemon=True, name="StreamReader"
        )
        self._detector_thread = threading.Thread(
            target=self._detector_loop, daemon=True, name="StreamDetector"
        )
        self._reader_thread.start()
        self._detector_thread.start()
        print(f"[StreamManager] Stream dimulai: {stream_url}")
    def stop(self, timeout: float = 8.0) -> None:
        """Hentikan semua thread stream dengan graceful shutdown."""
        print("[StreamManager] Menghentikan stream...")
        self._stop_event.set()
        self.metrics.update(status="stopped")
        for t in [self._reader_thread, self._detector_thread]:
            if t and t.is_alive():
                t.join(timeout=timeout)
        # Bersihkan queue
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break
        print("[StreamManager] Stream dihentikan.")
    def is_running(self) -> bool:
        return (
            self._reader_thread is not None and self._reader_thread.is_alive()
        ) or (
            self._detector_thread is not None and self._detector_thread.is_alive()
        )
    def get_latest_frame_bytes(self) -> bytes | None:
        """Return bytes JPEG frame terbaru untuk MJPEG endpoint."""
        """Return bytes JPEG frame terbaru untuk MJPEG endpoint.
        Prioritaskan preview buffer (langsung dari reader) yang lebih real-time.
        Fallback ke frame hasil deteksi jika preview belum tersedia.
        """
        with self._preview_frame_lock:
            if self._preview_frame_bytes is not None:
                return self._preview_frame_bytes
        with self._latest_frame_lock:
            return self._latest_frame_bytes
    def get_metrics(self) -> dict:
        m = self.metrics.get()
        m["uptime_seconds"] = int(time.time() - self._start_time) if self.is_running() else 0
        return m
    # ------------------------------------------------------------------
    # PRIVATE: READER THREAD
    # ------------------------------------------------------------------
    def _reader_loop(self, stream_url: str) -> None:
        """
        Thread ini HANYA membaca frame dari sumber stream.
        Meletakkan frame ke _frame_queue agar detector bisa mengambilnya.
        Ketika queue penuh (detector lambat), frame lama didrop — ini disengaja
        agar stream selalu menampilkan frame terbaru, bukan frame tertinggal.
        """
        reconnect_count = 0
        while not self._stop_event.is_set():
            cap = self._open_stream(stream_url)
            if cap is None:
                reconnect_count += 1
                if reconnect_count > self.MAX_RECONNECT:
                    print("[StreamManager][Reader] Batas reconnect tercapai. Berhenti.")
                    self.metrics.update(status="stopped")
                    self.socketio.emit("stream_error", {
                        "message": f"Gagal membuka stream setelah {self.MAX_RECONNECT} percobaan."
                    })
                    break
                self.metrics.update(status="reconnecting")
                time.sleep(self.RECONNECT_DELAY)
                continue
            self.metrics.update(status="active")
            reconnect_count = 0
            print("[StreamManager][Reader] Stream terbuka. Membaca frame...")
            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    print("[StreamManager][Reader] Frame gagal dibaca. Reconnecting...")
                    break
                # Update preview buffer langsung dari reader (untuk MJPEG yang smooth)
                _, jpeg_preview = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                with self._preview_frame_lock:
                    self._preview_frame_bytes = jpeg_preview.tobytes()
                # Jika queue penuh, buang frame lama (selalu ambil terbaru)
                if self._frame_queue.full():
                    try:
                        self._frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                try:
                    self._frame_queue.put_nowait(frame)
                except queue.Full:
                    pass
            cap.release()
            if not self._stop_event.is_set():
                self.metrics.update(status="reconnecting")
                print(f"[StreamManager][Reader] Reconnect dalam {self.RECONNECT_DELAY}s...")
                time.sleep(self.RECONNECT_DELAY)
        self.socketio.emit("video_done", {"message": "Stream selesai."})
        print("[StreamManager][Reader] Thread selesai.")
    def _open_stream(self, url: str, timeout_s: int = 10) -> cv2.VideoCapture | None:
        """Coba buka stream dengan timeout. Return cap atau None."""
        import os
        # Paksa OpenCV untuk menggunakan TCP daripada UDP yang sering drop packet (penyebab utama missing reference picture)
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        
        print(f"[StreamManager] Membuka stream: {url} (TCP Mode)")
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        # Atur buffer size kecil agar latency rendah
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        deadline = time.time() + timeout_s
        while not cap.isOpened() and time.time() < deadline:
            time.sleep(0.5)
        if not cap.isOpened():
            cap.release()
            print(f"[StreamManager] Gagal membuka stream: {url}")
            return None
        print(f"[StreamManager] Stream terbuka: {url}")
        return cap
    # ------------------------------------------------------------------
    # PRIVATE: DETECTOR THREAD
    # ------------------------------------------------------------------
    def _detector_loop(self) -> None:
        """
        Thread ini mengambil frame dari queue dan menjalankan inferensi.
        Emits: video_frame, violation_alert, stream_metrics ke frontend.
        """
        from deep_sort_realtime.deepsort_tracker import DeepSort
        tracker = DeepSort(max_age=30, n_init=3)
        frame_count = 0
        detect_frame_count = 0  # Frame yang benar-benar diinferensi
        fps_timer_start = time.time()
        fps_frame_count = 0
        fps_actual = 0.0
        total_detections = 0
        inference_ms = 0.0
        preprocess_ms = 0.0
        print("[StreamManager][Detector] Thread dimulai.")
        print(f"[StreamManager][Detector] Thread dimulai. "
              f"Resize={self.INFERENCE_WIDTH}px, SkipEvery={self.DETECT_EVERY_N} frame.")
        while not self._stop_event.is_set():
            try:
                frame = self._frame_queue.get(timeout=3.0)
            except queue.Empty:
                # Cek apakah reader masih hidup
                if self._reader_thread and not self._reader_thread.is_alive():
                    if self._stop_event.is_set():
                        break
                continue
            frame_count += 1
            fps_frame_count += 1
            current_time = time.time()
            # Hitung FPS aktual setiap 2 detik
            elapsed_fps = current_time - fps_timer_start
            if elapsed_fps >= 2.0:
                fps_actual = fps_frame_count / elapsed_fps
                fps_frame_count = 0
                fps_timer_start = current_time
            # ---- Frame skip: hanya infer setiap DETECT_EVERY_N frame ----
            if frame_count % self.DETECT_EVERY_N != 0:
                # Update preview dengan bounding box dari inferensi terakhir (re-use)
                continue
            detect_frame_count += 1
            frame_time_str = datetime.now().strftime("%H:%M:%S")
            # 1. Preprocess
            # 1. Preprocess dengan resize untuk mempercepat inferensi
            t0 = time.time()
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = frame.shape[:2]
            if w > self.INFERENCE_WIDTH:
                scale = self.INFERENCE_WIDTH / w
                new_h = int(h * scale)
                frame_resized = cv2.resize(frame, (self.INFERENCE_WIDTH, new_h))
            else:
                frame_resized = frame
                scale = 1.0
            frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
            img_tensor = self._transform(frame_rgb).to(self.device)
            preprocess_ms = (time.time() - t0) * 1000
            # 2. Inferensi
            # 2. Inferensi pada frame yang sudah di-resize
            t1 = time.time()
            with torch.no_grad():
                prediction = self.model([img_tensor])[0]
            inference_ms = (time.time() - t1) * 1000
            # 3. Filter deteksi
            boxes  = prediction['boxes'].cpu().numpy()
            scores = prediction['scores'].cpu().numpy()
            labels = prediction['labels'].cpu().numpy()
            detections_for_tracker = []
            class_counts = {}
            for i in range(len(boxes)):
                score    = scores[i]
                label_id = labels[i]
                if score < 0.6:
                    continue
                if label_id >= len(self.custom_classes):
                    continue
                class_name = self.custom_classes[label_id]
                if class_name == "background":
                    continue
                class_counts[class_name] = class_counts.get(class_name, 0) + 1
                x1, y1, x2, y2 = boxes[i]
                # Skala balik koordinat ke dimensi frame asli
                if scale != 1.0:
                    x1, y1, x2, y2 = x1/scale, y1/scale, x2/scale, y2/scale
                detections_for_tracker.append(
                    ([int(x1), int(y1), int(x2 - x1), int(y2 - y1)], score, class_name)
                )
            count_str = ", ".join([f"{v} {k}" for k, v in class_counts.items()]) or "no detections"
            print(f"[Detector] Frame #{frame_count}: {count_str} | {inference_ms:.0f}ms")
            print(f"[Detector] Frame #{frame_count} (infer #{detect_frame_count}): {count_str} | {inference_ms:.0f}ms")
            # 4. Update tracker
            # 4. Update tracker (gunakan frame asli, bukan yang diresized)
            tracks = tracker.update_tracks(detections_for_tracker, frame=frame)

            # --- PASS 1: Gambar SEMUA bbox ke frame utama (live preview) ---
            confirmed_tracks = [t for t in tracks if t.is_confirmed()]
            for track in confirmed_tracks:
                tracking_id = track.track_id
                ltrb = track.to_ltrb()
                x1, y1, x2, y2 = map(int, ltrb)
                object_name = track.get_det_class()
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"{object_name} ID:{tracking_id}",
                            (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # --- PASS 2: Kumpulkan pelanggaran baru dalam frame ini ---
            new_violations = []  # list of (tracking_id, object_name, confidence)
            with self._state_lock:
                for track in confirmed_tracks:
                    tracking_id = track.track_id
                    object_name = track.get_det_class()
                    confidence  = track.get_det_conf() or 0.0

                    # Cek cooldown (5 detik)
                    last_t = self._last_detection_time.get(tracking_id, 0)
                    if current_time - last_t < 5:
                        self._last_detection_time[tracking_id] = current_time
                        continue

                    if tracking_id in self._violators_logged:
                        self._last_detection_time[tracking_id] = current_time
                        continue

                    new_violations.append((tracking_id, object_name, float(confidence)))
                    self._last_detection_time[tracking_id] = current_time

            # --- PASS 3: Simpan SATU gambar gabungan jika ada pelanggaran baru ---
            if new_violations:
                combined_filename = (
                    f"stream_violation_{frame_count}_{int(time.time())}.jpg"
                )
                detected_objects = [
                    {'name': name, 'confidence': conf, 'tracking_id': tid}
                    for tid, name, conf in new_violations
                ]
                used_image_url = self.save_detection_cb(
                    frame_time=frame_time_str,
                    frame_number=frame_count,
                    confidence=max(conf for _, _, conf in new_violations),
                    detected_objects=detected_objects,
                    frame=frame,  # <--- Satu frame berisi SEMUA bbox
                    image_filename=combined_filename
                )
                with self._state_lock:
                    for tid, name, conf in new_violations:
                        self._violators_logged.add(tid)
                total_detections += len(new_violations)
                for tid, name, conf in new_violations:
                    self.socketio.emit('violation_alert', {
                        'message': 'Pelanggaran terdeteksi!',
                        'frame_time': frame_time_str,
                        'frame_number': frame_count,
                        'object_name': name,
                        'tracking_id': tid,
                        'confidence': conf,
                        'image_path': used_image_url
                    })
            # 5. Update MJPEG frame buffer
            _, jpeg_buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            with self._latest_frame_lock:
                self._latest_frame_bytes = jpeg_buf.tobytes()
            # 6. Update & emit metrics
            sys_metrics = self._collect_system_metrics()
            self.metrics.update(
                fps_actual=round(fps_actual, 2),
                inference_ms=round(inference_ms, 1),
                preprocess_ms=round(preprocess_ms, 1),
                frame_number=frame_count,
                detections_count=total_detections,
                **sys_metrics
            )
            self.socketio.emit("stream_metrics", self.get_metrics())
        print("[StreamManager][Detector] Thread selesai.")
    # ------------------------------------------------------------------
    # PRIVATE: SYSTEM METRICS
    # ------------------------------------------------------------------
    def _collect_system_metrics(self) -> dict:
        result = {"cpu_percent": 0.0, "ram_mb": 0.0, "gpu_percent": 0.0, "gpu_mem_mb": 0.0}
        if PSUTIL_AVAILABLE:
            try:
                result["cpu_percent"] = psutil.cpu_percent(interval=None)
                result["ram_mb"] = round(psutil.virtual_memory().used / (1024 ** 2), 1)
            except Exception:
                pass
        if GPU_AVAILABLE:
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                util   = pynvml.nvmlDeviceGetUtilizationRates(handle)
                mem    = pynvml.nvmlDeviceGetMemoryInfo(handle)
                result["gpu_percent"] = util.gpu
                result["gpu_mem_mb"]  = round(mem.used / (1024 ** 2), 1)
            except Exception:
                pass
        return result
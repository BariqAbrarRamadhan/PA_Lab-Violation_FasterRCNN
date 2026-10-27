# Black Box Testing - SafeVision Lab

Dokumen ini berisi skenario Black Box Testing untuk menguji fungsionalitas sistem secara menyeluruh sesuai dengan spesifikasi. Pengujian otomatis telah diimplementasikan menggunakan `pytest` di dalam file `tests/test_api.py`.

## Skenario Pengujian

| ID Test | Fungsionalitas | Skenario | Input / Aksi | Expected Output | Status Automasi |
|---|---|---|---|---|---|
| BB-01 | Navigasi Halaman | Mengakses halaman utama (Upload Video) | GET `/` | Mengembalikan HTTP 200 dan memuat template index.html | ✅ `test_index_page` |
| BB-02 | Navigasi Halaman | Mengakses halaman URL Stream | GET `/url` | Mengembalikan HTTP 200 dan memuat template url.html | ✅ `test_url_page` |
| BB-03 | Navigasi Halaman | Mengakses halaman Riwayat | GET `/history` | Mengembalikan HTTP 200 dan memuat template history.html | ✅ `test_history_page` |
| BB-04 | Upload Video | Gagal upload karena tidak ada file | POST `/upload_video` tanpa form data `video` | Mengembalikan HTTP 400 dengan pesan error `No file uploaded` | ✅ `test_upload_video_no_file` |
| BB-05 | Upload Video | Gagal upload karena format salah | POST `/upload_video` dengan file berekstensi `.txt` | Mengembalikan HTTP 400 dengan pesan error `Tipe file tidak didukung` | ✅ `test_upload_video_invalid_format` |
| BB-06 | Live Stream | Gagal memulai stream karena URL kosong | POST `/detect_from_stream` JSON `{"stream_url": ""}` | Mengembalikan HTTP 400 dengan pesan error `No stream URL provided` | ✅ `test_detect_from_stream_empty_url` |
| BB-07 | Live Stream | Berhasil menghentikan stream | POST `/stop_stream` | Mengembalikan HTTP 200 dengan pesan sukses | ✅ `test_stop_stream` |
| BB-08 | Live Stream | Mendapatkan status metrik stream | GET `/stream_status` | Mengembalikan HTTP 200 dengan metrik performa (FPS, dll) | ✅ `test_stream_status` |
| BB-09 | Riwayat | Mengambil list riwayat deteksi | GET `/api/detections` | Mengembalikan HTTP 200 dengan struktur JSON `data` dan `count` | ✅ `test_api_detections` |
| BB-10 | Riwayat | Mengambil statistik pelanggaran | GET `/api/detections/stats` | Mengembalikan HTTP 200 dengan struktur JSON `total` dan `by_type` | ✅ `test_api_detections_stats` |

## Cara Menjalankan Pengujian Otomatis

Pastikan environment siap dan `pytest` sudah terinstal:
```bash
pip install pytest
```

Jalankan perintah berikut di root folder project:
```bash
pytest tests/test_api.py -v
```

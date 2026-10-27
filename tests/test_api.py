import pytest
import os
import sys
import io

# Tambahkan folder backend agar bisa import main.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from main import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_index_page(client):
    """Test akses halaman utama (Upload Video)"""
    res = client.get('/')
    assert res.status_code == 200
    assert b'Upload Video' in res.data

def test_url_page(client):
    """Test akses halaman URL Stream"""
    res = client.get('/url')
    assert res.status_code == 200
    assert b'Stream URL' in res.data

def test_history_page(client):
    """Test akses halaman Riwayat"""
    res = client.get('/history')
    assert res.status_code == 200
    assert b'Riwayat Pelanggaran' in res.data

def test_upload_video_no_file(client):
    """Test upload video tanpa mengirimkan file"""
    res = client.post('/upload_video')
    assert res.status_code == 400
    assert res.json['error'] == 'No file uploaded'

def test_upload_video_invalid_format(client):
    """Test upload video dengan format file yang tidak didukung (contoh: .txt)"""
    data = {
        'video': (io.BytesIO(b'fake file content'), 'test.txt')
    }
    res = client.post('/upload_video', data=data, content_type='multipart/form-data')
    assert res.status_code == 400
    assert 'Tipe file tidak didukung' in res.json['error']

def test_detect_from_stream_empty_url(client):
    """Test mulai deteksi stream tanpa URL"""
    res = client.post('/detect_from_stream', json={'stream_url': ''})
    assert res.status_code == 400
    assert res.json['error'] == 'No stream URL provided'

def test_stop_stream(client):
    """Test menghentikan stream"""
    res = client.post('/stop_stream')
    assert res.status_code == 200
    assert 'message' in res.json

def test_stream_status(client):
    """Test endpoint status stream (Performance Monitor)"""
    res = client.get('/stream_status')
    assert res.status_code == 200
    assert 'is_running' in res.json
    assert 'fps_actual' in res.json

def test_api_detections(client):
    """Test API list riwayat deteksi dari database"""
    res = client.get('/api/detections')

    # Jika database tidak tersedia (misal di CI/CD tanpa env DB), dia mengembalikan 503
    assert res.status_code in [200, 503]
    if res.status_code == 200:
        assert 'data' in res.json
        assert 'count' in res.json

def test_api_detections_stats(client):
    """Test API statistik deteksi"""
    res = client.get('/api/detections/stats')
    assert res.status_code in [200, 503]
    if res.status_code == 200:
        assert 'total' in res.json
        assert 'by_type' in res.json

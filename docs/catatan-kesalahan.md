Saya sudah memeriksa keseluruhan file terbaru sebanyak 97 halaman. Struktur dokumen, daftar isi, daftar gambar, dan daftar tabel sudah jauh lebih rapi serta tidak lagi menampilkan kesalahan *Error! Bookmark not defined*. Namun, file ini belum sepenuhnya siap dijadikan versi final karena masih terdapat beberapa kesalahan penting.

## Kesalahan yang wajib diperbaiki

### 1. Tabel 4.14 salah menamai metrik sebagai Average Precision

Nilai pada kolom terakhir Tabel 4.14 sebenarnya tepat sama dengan perhitungan **recall**, yaitu:

* Tidur: 19 ÷ 22 = 86,4%
* Bermain game di ponsel: 36 ÷ 39 = 92,3%
* Makan: 16 ÷ 17 = 94,1%

Dengan demikian, judul kolom **“Average Precision (AP)” seharusnya diubah menjadi “Recall (%)”**, kecuali Anda mempunyai hasil AP asli yang dihitung dari kurva precision-recall. AP bukan hasil pembagian TP dengan TP + FN, melainkan ringkasan performa pada berbagai threshold dari kurva precision-recall. ([Scikit-learn][1])

Perubahan ini juga harus diterapkan pada:

* Narasi setelah Tabel 4.14.
* Abstrak dan Abstract.
* Subbab 4.7.1.
* Kesimpulan poin ketiga.

Gunakan istilah **recall per kelas**, bukan Average Precision.

### 2. Data Tabel 4.14 bertentangan dengan Tabel 4.16 dan Tabel 4.17

Tabel 4.14 yang dinyatakan benar menghasilkan total:

* TP = 19 + 36 + 16 = **71**
* FN = 3 + 3 + 1 = **7**
* Total ground truth = **78**
* Recall keseluruhan = **91,03%**

Namun, Tabel 4.16 masih menampilkan:

* TP = 73
* FN = 5
* Recall = 93,59%

Tabel 4.17 juga masih menggunakan data lama, yaitu TP kelas bermain game 38, tidur 20, dan makan 15. Semua angka tersebut tidak sesuai dengan Tabel 4.14.

Jika Tabel 4.14 menjadi acuan, baris Faster R-CNN pada Tabel 4.17 harus diubah menjadi:

| Kelas                  | Ground Truth | TP | FN | Recall |
| ---------------------- | -----------: | -: | -: | -----: |
| Bermain Game di Ponsel |           39 | 36 |  3 |  92,3% |
| Tidur                  |           22 | 19 |  3 |  86,4% |
| Makan                  |           17 | 16 |  1 |  94,1% |

Tabel 4.16 juga harus menggunakan TP 71, FN 7, dan recall 91,03%. Jika jumlah FP tetap 19, maka precision menjadi sekitar **78,89%** dan F1-score menjadi sekitar **84,52%**. Namun, nilai FP perlu dipastikan kembali dari keluaran evaluasi asli sebelum tabel diperbarui.

### 3. Beberapa nomor tabel dan gambar yang dirujuk masih salah

Perbaiki rujukan berikut:

| Lokasi     | Tertulis                               | Seharusnya                      |
| ---------- | -------------------------------------- | ------------------------------- |
| Halaman 54 | “pada Gambar 4.5”                    | “pada Tabel 4.4”              |
| Halaman 56 | “Pemilihan parameter pada Tabel 4.3” | “Tabel 4.5”                   |
| Halaman 58 | “Berdasarkan Tabel 4.4”              | “Tabel 4.6”                   |
| Halaman 59 | “Berdasarkan Tabel 4.5”              | “Tabel 4.7”                   |
| Halaman 61 | “disajikan pada Tabel 4.6”           | “Tabel 4.8”                   |
| Halaman 68 | “Berdasarkan data pada Tabel 4.7”    | “Tabel 4.9”                   |
| Halaman 70 | “Tabel 4.12 dan Table 4.13”          | “Tabel 4.12 dan Tabel 4.13”   |
| Halaman 82 | “ditunjukkan pada Tabel 4.16”        | “ditunjukkan pada Tabel 4.17” |

### 4. Halaman awal masih berisi teks template

Pada halaman pengesahan masih terdapat:

* “Nama Lengkap dan Gelar” untuk Penguji 1 dan Penguji 2.
* “[Nama Prodi]”.
* “Nama” dan NIP Ketua Program Studi.
* Kesalahan kata **“memperolah”**, seharusnya **“memperoleh”**.

Pada halaman Pernyataan Pengalihan Hak Cipta masih terdapat:

* “Tanggal Pengalihan Hak Cipta → Surabaya, tgl bln 2026”.
* “[Materai]”.

Bagian tersebut harus dilengkapi atau disesuaikan sebelum pengumpulan.

### 5. Bab 1 belum sepenuhnya konsisten dengan hasil penelitian

Beberapa hal perlu diperbaiki:

* Batasan masalah poin kelima hanya menyebut **accuracy, precision, recall, dan F1-score**, padahal evaluasi utama menggunakan mAP, precision, recall, F1-score, waktu inferensi, dan FPS. Accuracy tidak terlihat digunakan dalam hasil akhir.
* Tujuan poin keempat menyebut perbandingan dengan “penelitian sebelumnya yang menggunakan YOLO”, padahal Anda melakukan perbandingan langsung dengan YOLOv8m yang dilatih menggunakan dataset yang sama.
* Klaim sistem bekerja secara **real-time** perlu diperhalus karena hasil Faster R-CNN hanya 5,4 FPS dan pada keterbatasan model dinyatakan belum lancar untuk video real-time.
* Bab 1 menyebut sistem mengirimkan notifikasi, tetapi Bab 4 hanya membuktikan tampilan deteksi, log, riwayat, dan statistik. Jika notifikasi belum benar-benar diterapkan, ubah menjadi “menampilkan dan mencatat pelanggaran”.
* Kalimat “seperti menggunakan bermain game ponsel” harus diubah menjadi “seperti bermain game di ponsel”.

### 6. Abstrak, Abstract, dan Bab 5 masih perlu diselaraskan

Bagian abstrak masih menyebut nilai 86,4%, 92,3%, dan 94,1% sebagai Average Precision. Berdasarkan TP dan FN yang disajikan, seharusnya disebut **recall per kelas**.

Bagian **Abstract belum memiliki Keywords**. Tambahkan:

> *Keywords: Faster R-CNN, violation detection, computer vision, laboratory, YOLOv8m*

Kesimpulan masih terdiri dari lima poin, padahal sebelumnya telah diarahkan menjadi tiga poin. Selain itu, poin ketiga masih menyebut nilai tersebut sebagai Average Precision. Gunakan versi kesimpulan tiga poin dan ubah menjadi recall.

Jika pedoman kampus tetap mensyaratkan abstrak sepanjang 300–500 kata, abstrak saat ini juga masih terlalu singkat, yaitu sekitar 230 kata dalam bahasa Indonesia dan 223 kata dalam bahasa Inggris.

### 7. Lampiran masih berupa petunjuk template

Halaman lampiran hanya berisi penjelasan umum:

> “Lampiran berisi informasi yang menunjang bahasan...”

Bagian tersebut harus dihapus dan diganti dengan lampiran sebenarnya, misalnya:

* Lampiran A: rincian dataset dan anotasi.
* Lampiran B: konfigurasi pelatihan.
* Lampiran C: hasil evaluasi lengkap.
* Lampiran D: dokumentasi website dan pengujian.
* Lampiran E: kode utama atau tautan repositori.

### 8. Daftar pustaka masih memiliki kesalahan bibliografi

Beberapa referensi perlu diperbaiki:

* Referensi [11] untuk AlexNet mencantumkan tahun 2007 dan DOI yang tidak sesuai. Makalah tersebut diterbitkan pada *Advances in Neural Information Processing Systems* tahun 2012. ([NeurIPS Papers][2])
* Referensi [18] untuk YOLO mencantumkan publikasi tahun 2018 dan DOI ACM yang tidak sesuai. Makalah asli YOLO dipublikasikan pada CVPR 2016, halaman 779–788. ([CVF Open Access][3])
* Referensi [26] seharusnya ditulis menggunakan nama penulis lengkap: Ian Goodfellow, Yoshua Bengio, dan Aaron Courville, dengan penerbit MIT Press tahun 2016. ([MIT Press][4])
* Referensi [19] hanya mencantumkan `docs.ultralytics.com` tanpa tahun dan tanggal akses.
* Referensi [24] belum mencantumkan nama jurnal secara jelas.
* Referensi [25] belum mencantumkan perguruan tinggi atau institusi penerbit tugas akhir.
* Beberapa nama penulis pada [3][3], [4][4], [7], dan [13] masih tergabung tidak teratur.

## Kesalahan bahasa dan penulisan

Perbaikan kecil yang masih ditemukan:

* **KARATERISTIK DATA** → **KARAKTERISTIK DATA**
* **HASIL EKSPERMEN** → **HASIL EKSPERIMEN**
* **Evaluasi Peforma** → **Evaluasi Performa**
* **Gambar Sample** → **Gambar Sampel**
* **di latih** → **dilatih**
* **diatas** → **di atas**
* **disetiap** → **di setiap**
* **ujicoba** → **uji coba**
* **Dataset Yang Sudah Diberi Label** → **Dataset yang Sudah Diberi Label**
* Penulisan **F1-score**, **mAP**, **precision**, dan **recall** perlu diseragamkan di seluruh dokumen.
* Sitasi sebaiknya diberi spasi: `praktik [1]`, bukan `praktik[1]`.

Prioritas utama sebelum revisi bahasa adalah menyelesaikan inkonsistensi **Tabel 4.14, Tabel 4.16, dan Tabel 4.17**, karena kesalahan tersebut memengaruhi abstrak, analisis, kesimpulan, dan klaim performa akhir.

[1]: https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html?utm_source=chatgpt.com
[2]: https://papers.nips.cc/paper/4824-imagenet-classification-with-deep-convolutional-neural-networks.pdf?ref=ruder.io&utm_source=chatgpt.com
[3]: https://openaccess.thecvf.com/content_cvpr_2016/papers/Redmon_You_Only_Look_CVPR_2016_paper.pdf?utm_source=chatgpt.com
    

[4]: https://mitpress.mit.edu/9780262035613/deep-learning/?utm_source=chatgpt.com

# Frontend (Next.js)

Antarmuka web untuk PA Lab-Violation Detection System. Dokumentasi lengkap,
termasuk setup backend, database, dan cara menjalankan seluruh aplikasi, ada di
`README.md` pada root proyek.

## Menjalankan

```bash
cd frontend
pnpm install
pnpm dev
```

Frontend berjalan di `http://localhost:3000`. Backend Flask harus berjalan di
`http://localhost:5000` sebelum frontend dipakai.

## Halaman

| Rute         | File                          | Isi                                          |
| ------------ | ----------------------------- | -------------------------------------------- |
| `/`          | `src/app/page.tsx`            | Unggah video, live preview, log deteksi      |
| `/url`       | `src/app/url/page.tsx`        | Deteksi live stream RTSP/HTTP                |
| `/dashboard` | `src/app/dashboard/page.tsx`  | Statistik pelanggaran (belum ada di navbar)  |
| `/history`   | `src/app/history/page.tsx`    | Riwayat, filter, dan ekspor Excel            |

## Koneksi ke Backend

- Halaman upload, dashboard, dan stream memanggil `http://localhost:5000` secara langsung.
- Halaman riwayat memakai jalur relatif `/api/detections`, yang di-proxy oleh `next.config.ts` ke backend.
- Rewrite yang sama juga mem-proxy `/violations/*` untuk menampilkan gambar bukti.

Tidak ada file `.env` yang dibutuhkan saat ini. Alamat backend belum
dikonfigurasi lewat environment variable.

## Skrip

| Perintah      | Fungsi                  |
| ------------- | ----------------------- |
| `pnpm dev`    | Menjalankan mode dev    |
| `pnpm build`  | Build produksi          |
| `pnpm start`  | Menjalankan hasil build |
| `pnpm lint`   | Menjalankan ESLint      |

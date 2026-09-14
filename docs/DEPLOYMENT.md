# Deployment pertama

- Website: **https://vortex-xau.vercel.app**
- Proyek Vercel: `vortex-xau`.
- Sumber dashboard: commit [`a6bfef2`](https://github.com/achaer31/VORTEX/commit/a6bfef236ad208fcc976e8bedb4b211bf17b7cdb).
- Tanggal penerbitan: 14 September 2026.
- Status Vercel yang diverifikasi: `READY`, target `production`. Permintaan awal memakai preview; proyek pertama mendapat alias production dari layanan. Halaman dapat diakses publik dan hanya memuat snapshot riset yang juga ada dalam repo publik.

Lima file statis diterbitkan: `index.html`, `style.css`, `app.js`, `assets/favicon.svg`, dan `assets/snapshot.json`. Seluruh respons HTTP 200 dicocokkan byte-per-byte dengan sumber lokal. Tidak ada kode Python, konfigurasi VPS, atau data akun yang dikirim ke hosting.

Deployment pertama menggunakan unggahan file yang sudah diperiksa melalui konektor Vercel. **Git integration/auto-deploy belum tersambung**. Commit GitHub tidak otomatis mengubah halaman ini sampai integrasi tersebut diaktifkan atau deployment berikutnya dilakukan secara eksplisit. Tidak ada domain berbayar atau paket berbayar yang dibeli.

Untuk integrasi Git berikutnya, hubungkan proyek dengan `achaer31/VORTEX`, branch `main`, Root Directory `dashboard`, Framework **Other**, tanpa build command. Pertahankan proteksi yang tersedia; jangan meletakkan data akun dalam aset statis. Bila dibutuhkan dashboard privat dengan data akun, implementasikan login dan akses server terlebih dahulu seperti [arsitektur](ARCHITECTURE.md).

## Validasi

- [Research checks berhasil](https://github.com/achaer31/VORTEX/actions/runs/34811000475): 37 unit test.
- [Dashboard checks berhasil](https://github.com/achaer31/VORTEX/actions/runs/34811821938): sintaks JavaScript dan pencocokan snapshot terhadap arsip hasil.
- Browser lokal: 32 kombinasi periode/risiko/biaya cocok, detail dan tabel berfungsi, chart merespons timeframe serta keyboard, tidak ada error konsol, layout 390 piksel tanpa overflow.
- Browser hosted: halaman dan snapshot termuat dari domain Vercel.

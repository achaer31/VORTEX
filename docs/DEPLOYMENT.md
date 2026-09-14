# Deployment v0.2 — dashboard terbit, runtime belum aktif

- Konsol: **https://vortex-xau.vercel.app/v02.html**.
- Tanggal: 14 September 2026.
- Sumber: commit [`db1c939`](https://github.com/achaer31/VORTEX/commit/db1c939a9237907a2e39a5c14ee9ef22ee607453).
- Deployment Vercel: `dpl_55pDud5c5deGGQ8ExNzCqxem6DYb`, target `production`, status `READY`, alias tanpa error.
- URL versi tetap: https://vortex-nzsfkz00x-parasuhudigital-s-projects.vercel.app/v02.html.

Sembilan file statis diterbitkan: lima file dashboard pertama, ditambah
`v02.html`, `v02.css`, `v02.js`, dan `assets/v02.json`. Seluruh sembilan respons
HTTP 200 cocok byte-per-byte dengan sumber lokal. Snapshot v0.2 juga cocok
dengan keluaran eksperimen yang dibekukan: 100 skenario, saldo awal dan akhir
$50, nol transaksi. Ini hasil BACKTEST, bukan saldo atau P/L akun broker.

[GitHub Actions v0.2 berhasil](https://github.com/achaer31/VORTEX/actions/runs/34816891936):
73 tes riset, 54 tes observer/adapter/publisher, 17 tes evaluator otonomi,
22 tes API/database, dan 13 tes UI. Verifikasi hash sumber riset, arsip skenario
dan snapshot juga lulus. [Pemeriksaan dashboard lama](https://github.com/achaer31/VORTEX/actions/runs/34816891839)
tetap lulus. Tes tersebut memakai fixture sintetis untuk perilaku perangkat
lunak; bukan bukti transaksi, profitabilitas, atau otonomi VPS.

Browser lokal memeriksa 100 kombinasi skenario dan layout 390 piksel tanpa
overflow halaman. Browser production memuat hasil asli, tidak menunjukkan
error konsol, dan mengosongkan seluruh nilai akun ketika pindah ke DEMO tanpa
sumber terhubung. REAL tetap terkunci. Tidak ada data akun, identifier akses,
password, reader token, atau kode eksekusi dalam unggahan hosting.

**Status strategi: NO-GO / NOT_EVALUABLE. Status otonomi: NOT_TESTED / NOT_READY.**
VPS, observer, broker execution v0.2, database jarak jauh, watchdog dan Telegram
belum diaktifkan. Manajemen posisi v0.2 masih berupa simulator dan harus
diintegrasikan serta diuji pada broker demo. Tugas Windows yang disiapkan
berjalan saat logon; itu belum membuktikan restart tanpa interaksi. Pengujian
MacBook/Astra terputus, restart VPS, rekonsiliasi dan protective orders belum
dijalankan. Lihat [kontrak runtime](ARCHITECTURE-v02.md) dan
[gate bukti otonomi](../deploy/autonomy/README.md).

Vercel hanya menyajikan antarmuka dan laporan. Runtime final harus tetap
beroperasi di VPS ketika browser, dashboard, Telegram atau Astra tidak
tersedia. Tidak ada LLM dalam jalur keputusan wajib. Git integration/auto-deploy
belum tersambung; commit GitHub berikutnya tidak otomatis menerbitkan halaman.

## Deployment pertama

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

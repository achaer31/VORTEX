# VORTEX / XAU dashboard

`v02.html` adalah konsol EXTREME v0.2. Ia membaca `assets/v02.json` dari `research_v02/run_research.py` dan memilih skenario yang benar-benar tersedia, bukan menghitung ulang hasil di browser. Angka backtest tetap terpisah dari PAPER/DEMO.

PAPER/DEMO awalnya DISCONNECTED. Panel koneksi opsional menerima endpoint HTTPS tanpa query/credential dan reader token 64 karakter hex yang hanya ditahan di memori. GET menggunakan header Authorization, polling 15 detik; quote lebih tua dari 10 detik atau snapshot lebih tua dari 90 detik ditampilkan non-live. Data tidak ditahan sebagai angka live saat request gagal. Snapshot legacy tidak dipresentasikan sebagai skor v0.2. Tombol REAL terkunci; tidak ada kontrol order atau aktivasi.

Card September adalah target pengguna, bukan forecast atau izin trading. NO-GO tetap ditampilkan sampai penilaian terpisah; halaman tidak dapat mempromosikan dirinya sendiri.

Dashboard statis tanpa build/dependensi frontend. `index.html`, `style.css`, `app.js`, dan `assets/` adalah berkas publik. Jalankan lewat HTTP; browser membatasi pembacaan JSON jika HTML dibuka langsung dengan `file://`.

```sh
python3 -m http.server 8000 --directory dashboard
```

Halaman membaca **snapshot historis**, bukan broker atau feed live. Filter periode/risiko/biaya memilih salah satu dari 32 skenario tersimpan. Grafik candle dan modul sinyal memakai snapshot pasar terakhir, sementara metrics, equity, budget dan event mengikuti skenario terpilih. Equity berasal dari sampel CSV simulasi; tidak ada P/L per modul yang dibuat-buat. Pusaran ditandai sebagai ilustrasi.

## Memperbarui snapshot

Gunakan Python 3.10+ dengan standard library. Data sumber harus tersedia secara lokal; tidak ada unduhan/account login dalam builder.

```sh
python3 dashboard/tools/build_snapshot.py \
  --results /path/to/vortex-xau-results-v0.1 \
  --data /path/to/vortex-xau-data \
  --out dashboard/assets/snapshot.json
```

`--data` menerima satu folder run atau induknya yang berisi tepat satu run. Input results adalah keluaran eksperimen v0.1, termasuk `signals.csv`, `experiment.json`, dan seluruh direktori skenario. Parameter opsional memiliki default untuk struktur outputs asli; gunakan argumen eksplisit di checkout GitHub.

Builder menolak eksperimen selain model `VORTEX-XAU-v0.1` / eksperimen `xau-50-fixed-grid-v0.1` berstatus selesai. SHA-256 ketiga CSV candle harus cocok dengan manifest eksperimen sebelum data dan hasil digabungkan.

Snapshot memakai allowlist: maksimum 200 candle nyata per M5/M15/H1, skor terakhir dan 48 observasi riwayat skor, 32 summary tersanitasi, maksimum 48 sampel equity dan 6 sampel penolakan per skenario. Diagnosis sizing dihitung ulang dengan pembulatan yang sama dengan versi simulator v0.1. File metadata mentah, identitas akun, server, credential, IP, serta path lokal tidak disalin ke JSON.

Kontrol chart mendukung M5/M15/H1, 100/200 bar, pointer hover, serta tombol panah/Home/End saat chart difokuskan. Semua kartu modul dan diagnosis membuka detail. Escape menutup dialog. Layout responsif dan menghormati preferensi reduced motion.

Sumber: [VORTEX](https://github.com/achaer31/VORTEX), [laporan eksperimen](https://github.com/achaer31/VORTEX/blob/main/reports/v0.1/REPORT.md), [aturan sinyal](https://github.com/achaer31/VORTEX/blob/main/research/SIGNALS.md).

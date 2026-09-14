# Riwayat perubahan

## 2026-09-14 — baseline riset XAUUSD

Ini catatan retrospektif pekerjaan lokal sebelum repo dibuat. Riwayat commit dimulai saat paket diimpor; commit lama tidak direkonstruksi atau diberi tanggal palsu.

- Fokus dipindahkan dari konsep BTC ke XAUUSD. Berkas implementasi BTC lama tidak tersedia, sehingga versi XAU dibuat sebagai hipotesis baru.
- Ditambahkan exporter MQL5 manual dan validator PowerShell. Exporter tidak mengirim order dan menghindari identifier akun atau kredensial dalam hasilnya.
- Ditambahkan enam skor deterministik, indikator dari bar tertutup, dan penyelarasan M15/H1 tanpa memakai data masa depan.
- Ditambahkan audit struktur CSV dan pemeriksaan agregasi antar-timeframe.
- Ditambahkan simulator Bid/Ask proxy, spread/slippage, ukuran lot dibulatkan turun, batas sesi dan risiko, serta pencatatan alasan skip.
- Saat review sebelum eksperimen, pemeriksaan quote yang sudah melampaui SL dipindahkan sebelum sizing dan harga target diselaraskan ke tick. Perbaikan ini sudah termasuk dalam baseline yang diimpor; tidak diklaim sebagai commit historis tersendiri.
- Sebanyak 37 unit test lulus: 9 audit, 6 sinyal, 22 simulator.
- Dijalankan 32 skenario tetap dengan saldo simulasi awal $50. Semua berakhir $50, 0 transaksi. Seluruh 1.201 kandidat periode penuh ditolak karena lot minimum melampaui budget risiko.
- Diagnosis independen mencocokkan timestamp kandidat dan jurnal penolakan. Risiko minimum lot 0,01 dalam model baseline paling rendah $5,761, melebihi budget tertinggi $5.

## 2026-09-14 — repositori dan dashboard

- Sumber, pengujian, instruksi penggunaan, hash eksperimen, dan ringkasan hasil dipaketkan dalam repo.
- Dataset penuh serta jurnal besar disimpan lokal. Cuplikan dashboard diterbitkan secara eksplisit tanpa detail akses VPS atau akun.
- Versi dependensi awal dicatat terpisah agar file historis yang diberi hash tetap utuh.
- Dashboard responsif diterbitkan di Vercel dengan candle historis M5/M15/H1, enam skor, pilihan 32 skenario, equity, event, dan diagnosis lot minimum.
- Angka seluruh 32 kombinasi kontrol cocok saat diuji di browser. Layout 390 piksel tidak overflow. Detail modul, diagnosis, tabel, timeframe, dan pemeriksaan candle menggunakan keyboard berhasil.
- GitHub Actions untuk riset dan pencocokan snapshot/sintaks dashboard berhasil. File yang disajikan Vercel cocok byte-per-byte dengan sumber yang diperiksa.

Perubahan berikutnya dicatat melalui commit dengan alasan dan validasinya. Perubahan aturan strategi harus memakai versi eksperimen dan folder hasil baru.

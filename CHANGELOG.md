# Riwayat perubahan

## 2026-09-14 — parity enam engine native MT5

- Port perhitungan indikator, enam skor, konsensus dan mode v0.2 ke kernel MQL5
  murni; harness default nonaktif membaca fixture sintetis tanpa akses broker.
- Harness dikompilasi di VPS Exness dengan 0 error/0 warning. Hasil MQL5 aktual
  lulus comparator Python: 9 skenario, 8.685 baris sinyal dan 22 kasus mode;
  [ringkasan beserta hash](native_mt5/validation-native-parity-2026-09-14.json)
  disimpan tanpa data akun atau lokasi privat.
- Wrapper observer DEMO baca-saja dikompilasi 0 error/0 warning. Start dicoba
  dengan Allow Algo Trading tidak dicentang, tetapi Mac terkunci sebelum jurnal
  diperiksa; [operasi runtime belum terverifikasi](native_mt5/validation-target-2026-09-14.json).
  Total 29 tes native lokal lulus: 11 harness, 6 observer dan 12 fixture/comparator.
- Input wajib kalender/macro/session belum terhubung; ATLAS tetap tidak valid
  dan kontrak observer mewajibkan FROZEN/WAIT. Adapter risiko/eksekusi native belum tersedia.
  Parity bukan profit atau GO; sumber dan hasil riset historis tetap utuh.

## 2026-09-14 — bukti native MT5 pada VPS Exness

- Collector native mulai merekam heartbeat, quote/spread, metrik akun aktual,
  candle tertutup dan spesifikasi simbol secara privat tanpa Python atau order.
- Exporter akun sekali jalan mempertahankan deal/cost/cashflow yang dilaporkan
  broker. Funding/reset dipisahkan dari laba, arsip riset lama tetap utuh.
- Pemeriksaan identitas sebelum penulisan, redaksi saat INVALID, lock eksklusif,
  penulisan UTF-8 utuh dan marker capture parsial diperiksa secara independen.
- Kedua script dikompilasi di Exness tanpa error/warning; capture akun dan dua
  salinan collector diperiksa.34 tes pengumpulan data lulus,18 di antaranya
  merupakan tes kontrak sumber native.
- Pengumpulan bukti berjalan; enam engine/eksekusi, cloud/Telegram, pemulihan
  restart dan acceptance Mac-off belum aktif/lulus. NO-GO/NOT_READY tetap berlaku.

## 2026-09-14 — collector, adapter DEMO dan persiapan migrasi

- Ditambahkan mode collector DEMO eksplisit sebelum GO: candle tertutup,
  manifest, saldo aktual dan riwayat deal privat, tanpa order atau reset modal.
- Adapter eksekusi terpisah memakai risk gate v0.2 yang dibekukan, sizing dari
  ekuitas berjalan, lot dibulatkan turun, SL/TP, exit adaptif, dua winner adds,
  journal intent dan rekonsiliasi. Supervisor default offline; aktivasi tetap
  memerlukan seluruh gate. Tidak ada order nyata atau promosi strategi.
- Wrapper menjaga seluruh panggilan terminal pada satu thread, membuang hasil
  terlambat, memeriksa kesehatan lebih dahulu dan tidak mengulang order ambigu.
- Kalender satu kali dan adapter macro mempertahankan waktu penerimaan aktual;
  input tidak lengkap tidak menghasilkan skor atau izin entry yang dibuat-buat.
- MQL5 berhasil dikompilasi dan mengambil satu snapshot aktual, tetapi snapshot
  tetap ditolak karena jam belum terverifikasi dan coverage belum diattestasi.
- Paket runtime offline diverifikasi dengan hash/tanda tangan. Instalasi pada
  VPS lama ditolak kebijakan Windows (1625); runtime belum aktif. Parser native
  menerima empat script PowerShell tanpa kesalahan. Panduan migrasi diperbarui.
- Pengujian baru memakai broker sintetis. Hasil riset, starting capital $50,
  larangan top-up, NO-GO dan NOT_READY tetap utuh.

## 2026-09-14 — EXTREME v0.2 dan challenge, NO-GO

- Audit v0.1 dipertahankan; model baru memakai H4, liquidity sweep, session/DST,
  news/macro point-in-time, unsigned volatility quality dan independent risk gate.
- Menjelang eksperimen, pengguna mengubah exit menjadi adaptif terhadap lot
  executable dan menambahkan stress EXTREME10%. Amendment A1 dibekukan sebelum
  run; SPEC sebelum amendment diarsipkan. Tidak ada tuning setelah hasil.
- Simulator baru mencakup partial/single trailing, winner-only max2 adds,
  financing, risk caps, daily/streak freeze, lot/tick constraints dan SL-first.
-73 tes v0.2 lulus.100 profil/biaya/periode/walk-forward selesai: semua$50,
  0trade karena input mandatory hilang; statistik performa belum evaluable.
  Diagnosis minimum0.01lot mulai sekitar$6.17 vs budget$5 pada stress10%.
- Ditambahkan observer Windows v0.2 baca-saja, private publisher, optional
  Telegram dan journal hash chain;54 tes live lulus. Tidak ada proses diaktifkan.
- Database/Edge API/Docker template terpisah dari runtime MT5; pengujian HTTP
  dan SQL lokal. Token tidak masuk browser bundle/Git; infrastruktur belum dibuat.
- Dashboard v0.2 memisahkan BACKTEST/PAPER/DEMO; REAL terkunci.100 kombinasi
  terverifikasi di browser, layar390px tidak overflow;13 tes batas UI lulus.
- September challenge$50→$50.000 dicatat sebagai target, top-up0, tanpa kenaikan
  risiko karena tenggat. GO dan AUTONOMOUS READY tetap belum terpenuhi.
- Runtime final tidak bergantung Astra/OpenAI/MacBook/dashboard/Telegram.
  At-logon task belum membuktikan unattended reboot; acceptance Mac-off dan
  rekonsiliasi/protection pada VPS belum dijalankan.

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

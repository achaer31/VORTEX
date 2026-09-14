# Deployment v0.2 — dashboard terbit, collector native berjalan

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
Observer Python, broker execution v0.2, database jarak jauh, watchdog dan Telegram
belum diaktifkan. Adapter DEMO dan supervisor v0.2 kini tersedia sebagai kode
yang default-nya offline; integrasi aktual masih harus diuji pada broker demo.
Tugas Windows yang disiapkan
berjalan saat logon; itu belum membuktikan restart tanpa interaksi. Pengujian
MacBook/Astra terputus, restart VPS, rekonsiliasi dan protective orders belum
dijalankan. Lihat [kontrak runtime](ARCHITECTURE-v02.md) dan
[gate bukti otonomi](../deploy/autonomy/README.md).

Vercel hanya menyajikan antarmuka dan laporan. Runtime final harus tetap
beroperasi di VPS ketika browser, dashboard, Telegram atau Astra tidak
tersedia. Tidak ada LLM dalam jalur keputusan wajib. Git integration/auto-deploy
belum tersambung; commit GitHub berikutnya tidak otomatis menerbitkan halaman.

## Pemeriksaan VPS dan persiapan migrasi — 14 September 2026

- Terminal MT5 DEMO yang sudah login dapat diakses. Balance, equity dan posisi
  diperiksa secara privat; nilai berjalan tidak direset ke modal eksperimen.
  Tidak ada order dikirim dan Algo Trading tetap OFF.
- Installer Python resmi telah disalin, SHA-256 dicocokkan dan tanda tangan
  Python Software Foundation diterima. Instalasi ditolak dengan **1625**:
  kebijakan sistem melarang pemasangan. Python/venv/dependensi belum terpasang;
  collector Python, supervisor dan scheduled task belum berjalan. Tidak ada perubahan
  kebijakan keamanan atau percobaan menghindari pembatasan tersebut.
- Paket offline membawa installer dan wheel Windows dengan hash serta versi
  tetap. Empat script PowerShell diperiksa parser pada Windows PowerShell
  **5.1.17763.9121**, menghasilkan nol kesalahan sintaks. Ini bukan bukti bahwa
  instalasi, auto-start, atau pemulihan reboot berhasil.
- Pembaca kalender MQL5 dikompilasi pada MetaEditor: **0 error, 0 warning**.
  Satu query USD aktual selesai dengan dua record berdampak rendah. Jam host
  dan kelengkapan kalender belum diattestasi; adapter secara benar **REJECTED**.
  [Bukti terbatas beserta hash](../data_collection/calendar-validation-2026-09-14.json)
  mempertahankan status NO-GO; log dan data mentah tetap privat.
- [Collector](../live/README-v02-observer.md) dapat diaktifkan secara eksplisit
  untuk membaca bukti DEMO sebelum baseline lolos. Ia tidak mengirim order.
  [Supervisor eksekusi terpisah](../live/README-v02-execution.md) memerlukan
  persetujuan baseline, biaya, riwayat modal dan aktivasi DEMO sebelum koneksi.
  Tidak ada flag persetujuan yang diisi otomatis.
- Sasaran migrasi: Windows VPS milik pengguna dengan akses Administrator untuk
  MT5 dan Python native. Konfigurasi awal yang direkomendasikan 4 vCPU, RAM 8 GB,
  SSD minimal 80 GB; kapasitas dan latensi tetap harus diukur saat acceptance.
  Docker backend adalah paket Linux terpisah, bukan syarat menjalankan MT5.
  Windows penuh tidak menjadikan image Docker Linux otomatis kompatibel.

Hambatan yang tersisa: izin instalasi atau VPS pengganti; kalender yang lengkap
dan feed DXY/US10y intraday beserta riwayat point-in-time yang sah; baseline yang
benar-benar evaluable/lolos; konfigurasi owner untuk pengiriman privat dan
Telegram; serta uji broker DEMO, crash/reboot, rekonsiliasi dan MacBook terputus.
Kode dan tes lokal yang lolos tidak mengubah **NOT_READY** menjadi AUTONOMOUS READY.
Lihat [langkah Windows](../deploy/windows/README.md). Arsitektur riset dan seluruh
100 hasil eksperimen yang dibekukan tidak diubah.

## Collector native Exness — pengujian aktual 14 September 2026

Pencarian/pembelian VPS baru dihentikan sesuai arahan pengguna; tidak ada instance
Vultr yang dibuat atau biaya pembelian yang dikomit. Pengumpulan bukti dilanjutkan
pada MT5 Exness yang sudah tersedia melalui fitur script native, tanpa mengubah
kebijakan instalasi Windows.

- `VortexAccountEvidence.mq5` dikompilasi **0 error/0 warning** dan berhasil
  mengambil satu capture akun DEMO yang stabil selama pemeriksaan. Arsip mentah
  dan rekonsiliasi cashflow disimpan privat. Perubahan funding/reset dipisahkan
  dari profit; kerugian manual dan arsip eksperimen lama tidak dihapus. Capture
  valid tidak berarti modal, biaya, kelengkapan order, atau strategi disetujui.
- `VortexEvidenceCollector.mq5` versi yang ditinjau dua kali dikompilasi
  **0 error/0 warning**, lalu dijalankan di MT5 dengan Algo Trading **OFF**.
  Dua salinan privat menunjukkan 10 lalu 37 heartbeat berurutan, mempertahankan
  byte salinan pertama. Salinan kedua mencakup satu candle M5 dan satu M15
  tertutup; H1 masih menunggu penutupan berikutnya. Waktu host tercatat
  08:42:59–08:46:01 dan tetap dilabeli belum diverifikasi dalam data mentah.
- Semua heartbeat tersebut `COLLECTING_ONLY / WAIT`, `execution_enabled=false`.
  `WAIT` adalah status pencatat, bukan hasil konsensus enam engine. Data hanya
  disimpan pada VPS; belum dipublikasikan sebagai feed dashboard atau Telegram.
- Snapshot spesifikasi memiliki marker STARTED/COMPLETE, sementara komisi tetap
  UNKNOWN. Nilai biaya deal historis yang kebetulan nol tidak menjadi asumsi biaya
  masa depan. Kalender, DXY dan US10y tetap belum memenuhi gate input wajib.
- 18 pemeriksaan kontrak sumber native ditambahkan, sehingga suite pengumpulan
  data berisi 34 tes yang lulus. Tes tersebut statis/sintetis; hasil compile dan
  capture aktual dicatat terpisah beserta hash.

[Bukti publik yang telah disanitasi](../data_collection/native-validation-2026-09-14.json)
tidak membawa saldo akun, deal ID, login, alamat VPS, screenshot, atau kredensial.
Saldo DEMO aktual mengikuti perubahan pemilik; perubahan modal eksplorasi
memerlukan segmen eksperimen prospektif terpisah, bukan penggantian hasil $50
yang sudah dibekukan atau penghapusan kill-switch/riwayat rugi.

Collector native adalah script di terminal yang sedang hidup. Auto-start setelah
reboot/crash, pemulihan posisi/proteksi, penghentian MacBook/Astra, pengiriman
alert dan enam engine belum diuji sebagai satu runtime. **AUTONOMOUS READY tetap
belum tercapai; supervisor eksekusi belum diaktifkan dan tidak ada order dikirim.**

## Port enam engine native — parity aktual 14 September 2026

[Kernel native dan harness offline](../native_mt5/README.md) memakai input CSV
sintetis yang disiapkan dari Python v0.2 yang dibekukan. Harness dikompilasi pada
MetaEditor VPS dengan **0 error/0 warning**, lalu hasil eksekusi MQL5 dibandingkan
secara terpisah terhadap oracle Python: **PARITY_PASS**, 9 skenario, 8.685 baris
sinyal dan 22 kasus voting mode. Manifest, jumlah/urutan baris, nilai hilang,
flag dan alasan cocok; angka memakai toleransi absolut `1e-7` dan relatif `1e-10`.
[Ringkasan parity beserta hash](../native_mt5/validation-native-parity-2026-09-14.json)
telah disanitasi; bukti compiler dan proses terminal dicatat terpisah.
Sebanyak **29 tes native lokal** lulus: 11 kontrak harness, 6 kontrak observer dan
12 tes fixture/comparator, terpisah dari bukti compile dan hasil native tersebut.

Wrapper `VortexNativeObserve.mq5` dikompilasi **0 error/0 warning** dalam 2.924 ms.
Input observasi dan identitas DEMO diisi, lalu Start dikirim melalui MT5 dengan
Allow Algo Trading tetap tidak dicentang. Mac terkunci sebelum jurnal VPS dapat
dibaca; pembukaan otomatis gagal. **Status proses dan jurnal observer belum
diverifikasi; belum dapat diklaim berjalan.** [Catatan target beserta hash](../native_mt5/validation-target-2026-09-14.json)
mencatat percobaan mulai dan hambatan pemeriksaan. Wrapper ini baca-saja;
adapter risiko/eksekusi native belum diimplementasikan.
Kalender/coverage, DXY, US10y dan session/DST runtime belum terhubung, sehingga
ATLAS serta gate input wajib tetap menghasilkan **FROZEN/WAIT**. Tidak ada order
atau perubahan izin Algo Trading dalam paket native ini.

Kesetaraan numerik berlaku pada array fixture yang sama. Observer mengambil
riwayat terbatas dan memulai ulang seed indikator; itu belum membuktikan
kesetaraan terhadap seluruh riwayat backtest atau menyediakan replay lengkap
setiap keputusan. Port ini tidak mengubah aturan, hash atau 100 hasil riset
historis. **NO-GO / NOT_EVALUABLE dan NOT_READY tetap berlaku.**

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

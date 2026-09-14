# Paket Windows VPS: koleksi baca-saja dan observasi

Target Windows Server 2019, Python x64 dan terminal MT5 desktop dalam session pengguna yang sama. Source ini tidak menyatakan bahwa instalasi, koneksi, atau recovery VPS sudah lolos pengujian. Tidak ada order yang dapat dikirim oleh kolektor v0.2.

Semua script default **dry-run/preflight**. Koleksi data DEMO boleh dimulai secara eksplisit sebelum baseline lolos. Mode `Observe` tetap memerlukan baseline yang benar-benar sudah ditinjau. Tidak ada script yang menetapkan `VORTEX_BASELINE_STATUS=passed_reviewed`; koleksi data tidak mengubah NO-GO penelitian.

## Hasil instalasi VPS yang sudah diamati

Percobaan pada VPS Exness berhenti pada Windows Installer **error 1625**, yang berarti pemasangan dilarang oleh kebijakan sistem. **Python/runtime VORTEX belum terpasang dan kolektor belum dimulai pada VPS tersebut.** Terminal MT5 yang sudah tersedia tidak membuktikan runtime Python berhasil terpasang. Arti kode ini sesuai [dokumentasi Windows Installer Microsoft](https://learn.microsoft.com/en-us/windows/win32/msi/error-codes).

Unduhan langsung sebelumnya juga gagal terhubung. Bundle offline sudah disiapkan untuk membawa installer dan dependency resmi dengan hash terpin; pemasangan offline tetap tunduk pada kebijakan Windows. Log installer tetap privat. Source dan hasil unit test lokal tidak mengubah status instalasi VPS yang gagal ini.

| Berkas | Perilaku |
| --- | --- |
| `runtime.json` | Versi, URL dan hash installer resmi yang digunakan oleh installer |
| `Install-Runtime.ps1` | Default dry-run; pemasangan hanya dengan `-Apply`, termasuk verifikasi paket |
| `offline-runtime.json` / `offline-requirements.txt` | Manifest installer dan wheel Windows x64 terpin, termasuk SHA-256 setiap paket |
| `prepare_offline.py` | Mengunduh bundle dari sumber resmi dan memeriksa hash; tidak memasang atau menjalankan paket |
| `Preflight.ps1` | Pemeriksaan dependency terpin, konfigurasi privat dan tes; `-Mode Collect` tetap offline |
| `preflight_imports.py` | Pemeriksaan import tanpa koneksi terminal; file Python menghindari masalah quoting `-c` PowerShell 5.1 |
| `Watch-Observer.ps1` | Default preflight; `-StartCollector` menjalankan `--collect`; `-StartObserver` menjalankan `--observe` dengan gate baseline |
| `Register-ObserverTask.ps1` | Default dry-run; `-Apply -Mode Collect` mendaftarkan kolektor, `-Apply -Mode Observe` mendaftarkan observer yang telah lolos gate |

Runtime berada di `%LOCALAPPDATA%\VORTEX\runtime`; state/jurnal/data ada di `VORTEX_STATE_DIR`, di luar checkout. Task tidak menaruh password atau identitas akun dalam argumennya. Setting privat untuk logon berikutnya harus tersedia sebagai environment User VPS, bukan hanya dalam proses PowerShell sementara.

## Menyiapkan dan menggunakan bundle offline

Pada komputer tepercaya yang sudah memiliki Python dan akses unduh, jalankan dari root checkout. Argumen terakhir adalah direktori bundle di luar checkout; contoh berikut menggunakan path Windows generik:

```powershell
python .\deploy\windows\prepare_offline.py C:\VORTEX-Private\runtime-bundle
```

Salin seluruh direktori hasil, termasuk `python-installer.exe` dan `wheels`, ke Windows tujuan bersama checkout versi yang sesuai. Simpan paket biner di luar Git. Pada Windows yang mengizinkan instalasi, lihat dry-run dahulu lalu lakukan pemasangan eksplisit:

```powershell
.\deploy\windows\Install-Runtime.ps1 -OfflineBundlePath C:\VORTEX-Private\runtime-bundle
.\deploy\windows\Install-Runtime.ps1 -Apply -OfflineBundlePath C:\VORTEX-Private\runtime-bundle
```

Installer memeriksa hash paket dan tanda tangan resmi Python sebelum menjalankan installer. Dependency offline dipasang dari wheel lokal dengan `--no-index` dan `--require-hashes`. Setelah instalasi berhasil, versi/arsitektur runtime dan tes keselamatan sintetis diperiksa. Langkah ini tidak memulai terminal, kolektor, task, publisher atau trading. Jangan lanjut ke langkah koleksi jika instalasi atau pemeriksaan gagal.

## Migrasi ke Windows yang dikendalikan pemilik

Jalur berikutnya adalah Windows x64 yang dikendalikan pemilik dengan hak administrator penuh dan kebijakan yang mengizinkan instalasi resmi. Kebijakan VPS Exness yang menolak pemasangan tetap berlaku; paket ini tidak mengubah atau melewati kebijakan tersebut.

1. Siapkan checkout yang sesuai dan bundle terverifikasi pada Windows tujuan. Jika ada state/jurnal koleksi sebelumnya, pindahkan secara privat di luar checkout dan pertahankan seluruh riwayatnya.
2. Pasang runtime resmi dengan langkah di atas. Pasang terminal MT5 resmi dan masuk secara manual ke akun DEMO yang diharapkan, dalam session pengguna yang akan menjalankan kolektor.
3. Isi konfigurasi privat sesuai panduan kolektor. Gunakan saldo dan riwayat broker yang sebenarnya; jangan membuat saldo awal pengganti atau menghapus kerugian manual.
4. Jalankan preflight, lalu probe koleksi eksplisit sesuai bagian berikut. Catat hasil Windows/MT5 yang benar-benar diamati sebelum menyatakan kolektor berjalan. Registrasi task saat logon tetap merupakan langkah terpisah.

Panduan ini belum membuktikan instalasi pada Windows pengganti, recovery reboot, atau kesiapan eksekusi otonom. Baseline penelitian dan gate aktivasi tetap berlaku.

## Koleksi data sebelum baseline lolos

Set konfigurasi privat yang dijelaskan dalam [panduan kolektor](../../live/README-v02-observer.md). Terminal harus sudah masuk ke akun DEMO USD hedging yang diharapkan. Akun sebenarnya diperiksa saat runtime; preflight tidak mengklaim koneksi broker.

1. Jalankan `Preflight.ps1 -Mode Collect` setelah runtime resmi tersedia. Ini tidak memulai terminal atau mengambil data broker.
2. Untuk probe tunggal, jalankan `live/observe_v02.py --collect --once` dengan Python runtime yang benar. Untuk koleksi berkelanjutan, gunakan `Watch-Observer.ps1 -StartCollector`.
3. Jika koleksi saat logon berikutnya diinginkan, lakukan tindakan terpisah `Register-ObserverTask.ps1 -Apply -Mode Collect`. Registrasi tidak langsung memulai task.
4. File `STOP` pada direktori state menghentikan kolektor dan mencegah watchdog memulainya lagi. Guard/error halt tidak di-retry otomatis; data dan jurnal tidak boleh dihapus untuk menyembunyikan masalah.

`--collect` tetap **FROZEN / WAIT**, tidak mengirim order, dan tidak mengubah saldo. Saldo broker saat itu dicatat apa adanya. Candle tertutup, observasi akun dan deal history disimpan privat; identitas deal/comment tidak masuk dashboard. Rekonstruksi saldo awal hari menggunakan riwayat broker yang tersedia, dan drawdown ekuitas tetap belum tersedia jika jalur ekuitas intraday tidak lengkap.

## Observasi yang menunggu review baseline

`Watch-Observer.ps1 -StartObserver` dan `Register-ObserverTask.ps1 -Apply -Mode Observe` mempertahankan gate `passed_reviewed`. Mode ini juga hanya membaca, bukan mengaktifkan mesin order. Publisher cloud dan helper Telegram adalah proses terpisah dan tidak diaktifkan oleh task kolektor.

## Batas startup dan otonomi

Task dijalankan **saat user logon**, dalam session interactive. Disconnect RDP berbeda dari Windows sign out: session dan terminal harus tetap hidup. Paket tidak mengatur autologin atau menyimpan password. Pemulihan reboot tanpa login, reconnection dan rekonsiliasi mesin order masa depan belum dibuktikan oleh task ini. Status bukan `auto_ready`.

Kolektor tidak bergantung pada Mac, ChatGPT, LLM, dashboard atau Telegram. Unit test lokal tidak menggantikan pemeriksaan runtime Windows/MT5 sebenarnya. Riwayat penelitian dan report yang sudah dibekukan tidak diubah oleh koleksi ini.

Sumber: [MetaTrader5 resmi MetaQuotes](https://pypi.org/project/MetaTrader5/), [UTC dan copy_rates_range](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py), [history_deals_get](https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py).

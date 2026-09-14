# Paket Windows VPS — belum diterapkan

Target Windows Server 2019, Python x64 dan terminal MT5 desktop di session pengguna yang sama. Paket ini tidak mengasumsikan Linux Docker dapat menjalankan terminal Windows. Tidak ada installer, task, observer atau order yang dijalankan saat paket ditulis.

Semua script default **dry-run/preflight**. Aktivasi forward DEMO menunggu baseline v0.2 lolos review; strategi v0.1 tetap observe-only dan CLI armed diblokir.

## Isi

| Berkas | Perilaku |
| --- | --- |
| `runtime.json` | Python 3.13.15 x64, URL dan SHA-256 installer dari python.org |
| `Install-Runtime.ps1` | Dry-run; `-Apply` baru mengunduh, memverifikasi hash + signature PSF, memasang per-user dan dependensi terpin, menjalankan tes sintetis |
| `Preflight.ps1` | Memeriksa dependency, konfigurasi privat dan tes. Tidak memanggil initialize/login/order MT5 |
| `Watch-Observer.ps1` | Default preflight; `-StartObserver` baru menjalankan observe, dengan gate baseline dan log privat. Safety/error halt tidak di-retry |
| `Register-ObserverTask.ps1` | Dry-run; `-Apply` baru mendaftarkan task observe saat user logon, bukan service SYSTEM atau autologin. Tidak langsung memulai task |

Runtime dipisahkan di `%LOCALAPPDATA%\VORTEX\runtime`; state/jurnal di `VORTEX_STATE_DIR` yang harus berada di luar Git checkout. Task tidak menyimpan password atau nomor login pada argumentnya. Konfigurasi privat yang perlu tersedia pada logon berikutnya harus disetel sebagai environment User di VPS, bukan hanya environment process.

## Urutan setelah baseline ditinjau

1. Tinjau dry-run installer. Operator dapat menerapkan `Install-Runtime.ps1 -Apply` bila instalasi memang diinginkan. Paket tidak mengubah konfigurasi MT5 atau login.
2. Set environment privat yang tercantum di [live/README.md](../../live/README.md). Jalankan `Preflight.ps1`. Akun/clock/koneksi masih perlu probe baca-saja terpisah; preflight tidak mengklaim koneksi broker.
3. Hanya setelah baseline v0.2 benar-benar lolos review, set gate privat `VORTEX_BASELINE_STATUS=passed_reviewed`. Flag ini acknowledgment operator, bukan bukti otomatis kualitas strategi.
4. `Watch-Observer.ps1 -StartObserver` menjalankan **observasi v0.1** saja. Integrasi v0.2 dan aktivasi trading belum disediakan. Untuk logon berikutnya, `Register-ObserverTask.ps1 -Apply` adalah tindakan terpisah dan tidak langsung menjalankan proses.
5. File `STOP` pada direktori state menghentikan observer dan mencegah watchdog memulai lagi. Hentikan task bila perlu. Jangan hapus journal atau state sebagai recovery; intent ambigu harus direkonsiliasi terlebih dahulu.

Task memakai session interactive yang sudah login. Disconnect RDP berbeda dari Windows sign out: session pengguna harus tetap berjalan agar terminal dan bridge tetap tersedia. Tidak ada autologin atau penyimpanan password dalam paket.

## Validasi dan batas

36 tes safety Python sintetis lulus pada runtime lokal Python 3.12.14. PowerShell/installer/Task Scheduler belum dieksekusi atau diuji pada VPS. Installer versi 3.13.15 tersedia resmi dan SHA-256 dipin, tetapi kompatibilitas lingkungan Windows tetap perlu diverifikasi ketika instalasi disetujui.

Sumber: [Python 3.13.15 dan checksum installer](https://www.python.org/downloads/release/python-31315/), [MetaTrader5 resmi MetaQuotes](https://pypi.org/project/MetaTrader5/), [clock MetaTrader Exness](https://get.exness.help/hc/en-us/articles/360014390760-What-is-the-default-timezone-set-for-MetaTrader).
# v0.2 observer target and autonomy limitation

The prepared watchdog now targets `live/observe_v02.py --observe`, and preflight runs its offline `--check`. Both remain behind the existing reviewed-baseline gate; no process or task was activated. See `live/README-v02-observer.md` for private configuration and verification.

The scheduled task is **at user logon**, in an interactive session. It does not prove unattended restart after a Windows reboot. No automatic sign-in or credential storage is configured. MT5 interactive-session recovery, publisher/cloud reconnection, and the future full order-engine reconciliation remain separate acceptance checks. Current status is not `auto_ready`.

# Infrastruktur forward DEMO

**Status: scaffold observasi; belum mengaktifkan strategi EXTREME atau mengirim transaksi.** Permintaan terbaru menambahkan aturan EXTREME yang berbeda dari riset v0.1. CLI menolak `--mode armed`, dan sinyal lama v0.1 tidak dapat membuka entry. Fungsi eksekusi generik ada untuk pengujian sintetis dan integrasi versi berikutnya.

Python berjalan di Windows VPS, berkomunikasi dengan MT5 yang sudah login. Tidak ada `login()` atau password di kode. Enam skor yang ditampilkan masih hasil `research/vortex_xau/signals.py` v0.1. News, macro, H4, mode EXTREME dan penambahan posisi belum diimplementasikan di bridge ini.

## Menjalankan observasi

Tes lokal memakai Python 3.12.14; paket Windows menargetkan Python 3.13.15 x64 yang memiliki installer resmi dengan hash terverifikasi. Pengujian pada runtime Windows tersebut belum dilakukan. Terminal MT5 harus sudah login pada **DEMO, USD, hedging**. Satu terminal dan satu direktori state dipakai konsisten. Instal dependensi dari checkout:

```powershell
python -m pip install -r live/requirements.txt
```

Konfigurasi berikut harus disetel secara privat di VPS, bukan ditulis ke repository:

| Variabel environment | Isi |
| --- | --- |
| `VORTEX_EXPECTED_LOGIN` | Nomor akun DEMO yang memang diizinkan |
| `VORTEX_SESSION_UTC_OFFSET_MINUTES` | Offset clock session terhadap UTC yang sudah diverifikasi; 0 adalah nilai eksplisit, bukan default |
| `VORTEX_STATE_DIR` | Folder runtime absolut di luar checkout; menyimpan state, jurnal dan status |
| `VORTEX_TERMINAL_PATH` | Opsional: path terminal MT5 yang sudah login |

```powershell
python live/demo_runner.py --mode observe --once
python live/demo_runner.py --mode observe
```

Observasi tidak memerlukan tombol Algo Trading aktif. Hentikan proses dengan Ctrl+C. Proses ini tidak memasang scheduled task atau service. `--risk` hanya parameter sizing untuk observasi: 0.01, 0.02, 0.03, 0.04, 0.05 atau 0.075; default 0.03. Angka ini belum merupakan implementasi mode EXTREME.

Paket operasional tersedia di [deploy/windows](../deploy/windows/README.md). Sesuai permintaan terbaru, jangan mulai forward/paper DEMO sebelum baseline v0.2 selesai diuji dan ditinjau. Scaffold ini tidak menyatakan baseline telah lolos.

## Batas yang diterapkan

- Akun harus DEMO, nomor login harus cocok konfigurasi privat, currency USD, dan margin mode hedging. Pengiriman generik memeriksa kembali akun sesaat sebelum `order_send`; akun real selalu ditolak.
- Simbol harus tepat XAUUSD dengan chart Bid. Jalur eksekusi generik dibatasi Instant/Request + FOK dan SL/TP wajib. Sizing menggunakan estimasi `order_calc_profit` serta `order_calc_margin` broker, bukan kontrak atau leverage yang ditebak.
- Basis risiko maksimum `min(balance, equity, 50 USD)`. Lot dibulatkan turun, risiko maksimal 7,5% dari basis tersebut. Tidak ada pembesaran minimum lot atau penyempitan stop agar trade dipaksakan masuk.
- Alokasi margin maksimal 25%. Stop mengikuti 2,2 × ATR dan minimum 10 tick; slippage 0,03 USD/ounce per sisi serta komisi nol masih asumsi scaffold. Hasil fill dan loss aktual tidak dijamin oleh estimasi tersebut.
- Pengunci harian berdasarkan P/L posisi milik bot dan baseline alokasi maksimal 50 USD: 15%; 2 kerugian berturut-turut membagi dua risiko, 3 membekukan entry sampai pergantian tanggal session. Baseline, realized P/L, streak dan keputusan dipersistenkan.
- Tidak mengadopsi atau mengubah posisi manual. Posisi/order lain menghalangi entry. Magic, identifier, volume, SL dan TP posisi bot harus sesuai journal; perubahan eksternal membekukan proses. Generic lifecycle mendukung satu posisi bot dan keluar pada akhir session 08–18, pergantian tanggal, atau 180 menit.
- Tick harus berumur maksimal 10 detik. Entry generik hanya pada 30 detik pertama bar baru, dari M5 sebelumnya yang sudah closed dan adjacent. Konteks M15/H1 harus sudah closed serta belum melewati usia satu periodenya.
- Keputusan disimpan sebelum entry; intent disimpan dan disinkronkan ke disk sebelum send. Timeout, hasil parsial, atau hasil selain DONE meninggalkan intent yang membekukan proses. Tidak ada pengulangan order otomatis atau penambahan volume untuk mengejar fill.

Jangan menghapus state/journal untuk mengatasi intent ambigu. Rekonsiliasi order, deal, dan posisi pada terminal dahulu. Walau submit dan pemeriksaan berdekatan, API MT5 tidak menyediakan transaksi atomik untuk mengunci pergantian akun di UI; terminal yang dikhususkan untuk akun DEMO tetap diperlukan untuk operasi yang diawasi.

## Data dan clock

API resmi MetaTrader5 Python menyatakan timestamp rate/tick dalam UTC. Offset konfigurasi hanya memetakan clock session; ini tidak membuktikan historical UTC/DST pada dataset lama. History start dipatok pada midnight UTC 180 hari sebelum state pertama dibuat. Bar yang belum closed dibuang. Batas awal history tiap timeframe dipersistenkan agar perubahan seed EMA tidak terjadi diam-diam. Minimal 220 bar per timeframe dan seluruh readiness v0.1 tetap diperlukan; ketersediaan history bergantung terminal.

[Exness menyatakan clock MetaTrader GMT+0](https://get.exness.help/hc/en-us/articles/360014390760-What-is-the-default-timezone-set-for-MetaTrader). Masukkan 0 secara eksplisit setelah identitas terminal dan timestamp probe dikonfirmasi; ketentuan ini tidak mengubah provenance dataset historis.

Runtime `status.json` ditulis atomik dengan daftar field terbatas: quote XAUUSD, status proses, angka akun DEMO, posisi bot ber-ID hash, dan skor lama v0.1. Tidak berisi login, password, nama akun, server, IP, atau path mesin. `state.json` dan `journal.jsonl` tetap privat. `eaRunning` pada kontrak status berarti proses bridge berjalan, bukan bahwa sebuah EA MQL5 sudah dipasang. Publisher HTTPS terautentikasi belum menjadi bagian dari file ini.

## Validasi

```sh
python -m unittest discover -s live/tests -v
```

Tes memakai FakeMT5 dan harga/akun sintetis, bukan akun broker. Tes tidak membuktikan hasil trading atau kelayakan EXTREME. Pengujian koneksi Windows dan observasi VPS harus dilaporkan terpisah.

Dokumentasi primer: [timestamp dan history](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py), [profit dalam mata uang akun](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcprofit_py), [order check](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercheck_py), [order send](https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py), [package resmi MetaQuotes](https://pypi.org/project/MetaTrader5/).

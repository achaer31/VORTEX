# VORTEX XAU — riset historis dengan saldo awal $50

Paket ini mengaudit ekspor XAUUSD dan menjalankan simulasi historis offline. Tidak ada koneksi broker, pengiriman order, atau perubahan saldo akun demo/real. Model **VORTEX-XAU-v0.1 adalah hipotesis baru**, bukan reproduksi `vortex_x100.py` yang belum tersedia. Enam skor dan bobot lengkap dijelaskan dalam [SIGNALS.md](SIGNALS.md).

## Menjalankan

Python 3.10 atau lebih baru diperlukan. Runtime awal diperiksa memakai Python 3.12.14, pandas 2.2.3, dan NumPy 2.3.5. Instal kebutuhan lalu jalankan dari direktori paket:

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python run_research.py --data /path/to/VortexExport/run --out /path/to/new-results
```

`--data` harus menunjuk satu folder berisi `XAUUSD_M5.csv`, `XAUUSD_M15.csv`, `XAUUSD_H1.csv`, serta idealnya `manifest.csv` dan `metadata.csv`. `--out` wajib baru atau kosong; hasil lama tidak ditimpa. Gunakan data broker nyata untuk laporan riset dan pisahkan fixture sintetis yang digunakan pengujian. Tidak dibutuhkan login, password, API key, MT5 yang berjalan, atau VPS untuk menjalankan paket ini.

## Protokol tetap

Audit struktur dijalankan terlebih dahulu. CSV yang hilang/ambigu, kosong, malformed, atau berisi timestamp/OHLC/volume tidak valid menghentikan proses. Perbedaan agregasi M5 terhadap M15/H1 dan perbedaan manifest dicatat terpisah untuk ditinjau; kelolosan struktur tidak otomatis berarti konsistensi atau kelengkapan history.

Konfigurasi dan hash data/kode ditulis ke `experiment.json` **sebelum menghitung sinyal atau P/L**. Sinyal dihitung sekali secara kausal atas seluruh data. Model hanya memakai bar yang telah selesai: sinyal M5 tersedia saat close; eksekusi paling cepat pada open bar selanjutnya. Konteks M15/H1 harus sudah tutup pada waktu keputusan. Gap tidak diisi dan entry setelah gap dilewati.

Eksperimen memuat tepat **32 skenario tetap**: empat periode × empat risiko × dua asumsi biaya. Tidak ada pencarian parameter, optimasi, pemilihan pemenang, atau Monte Carlo.

- Periode: seluruh data untuk deskripsi; development 60% hari kalender; validation 20%; holdout sisa hari. Tiga bagian terakhir terpisah secara kronologis. Full bertumpang tindih dan bukan validasi independen.
- Saldo dan posisi mulai ulang dari **$50** pada setiap skenario. Fitur bagian berikutnya dapat memakai bar sebelumnya yang tersedia secara kausal, tanpa membawa saldo/posisi. Entry tidak dilakukan pada bar pertama partisi.
- Risiko rencana per entry: 3%, 5%, 7,5%, 10%. Lot dibulatkan turun per 0,01. Jika lot minimum melebihi anggaran, trade dilewati; saldo kecil tidak dipaksa masuk.
- Baseline: spread bar sebelumnya ×1, slippage $0,03 per ons. Stress: spread ×2, slippage $0,10. Slippage diterapkan pada market/stop fill menurut simulator; TP memakai levelnya. Komisi diasumsikan nol; biaya ini belum diverifikasi dari transaksi broker.
- Pembatas tetap: stop 2,2 ATR, target 2,2R, satu posisi, maksimum 36 bar waktu tahan, jam riset 08:00–18:00 dalam clock server, pendekatan leverage 1:2000 dan cap margin 25%.
- Risiko dipotong setengah setelah dua kerugian beruntun dan entry dibekukan setelah tiga sampai tanggal server berikutnya. Batas rugi harian 15% diperiksa pada open/close, bukan jaminan maksimum rugi intrabar/gap.
- Tidak ada martingale, peningkatan risiko otomatis, atau transfer ke vault. Posisi tersisa ditutup pada akhir data. Nilai `vault_balance` tetap nol.

Konfigurasi eksplisit dari simulator dan definisi kode yang diberi hash dalam setiap hasil adalah rujukan angka yang berlaku. Setelah holdout dilihat, perubahan model harus disebut eksperimen baru; hasil tidak boleh berulang kali dipakai memilih parameter sambil tetap diklaim sebagai holdout baru.

## Isi hasil

| Berkas | Isi |
| --- | --- |
| `audit.json` | Struktur tiap CSV, rentang/jumlah bar, SHA-256, manifest dengan nilai terakhir menang, perbandingan M5→M15/H1 |
| `experiment.json` | Parameter tetap, waktu pembekuan, versi runtime, hash kode/data, pembagian periode, status eksekusi |
| `signals.csv` | Semua bar M5, kesiapan indikator, skor, consensus, sinyal, dan timestamp konteks HTF |
| `summaries.csv` | Semua hasil skenario, termasuk saldo akhir, drawdown yang disampel, jumlah trade, biaya proxy dan alasan skip |
| `scenarios/<nama>/` | `trades.csv`, `equity.csv`, `events.csv`, dan `summary.json` lengkap tiap skenario |
| `REPORT.md` | Laporan berbahasa Indonesia, tabel seluruh skenario dan batas interpretasi |

Skenario tanpa trade tetap menghasilkan CSV dengan header; saldo akhir $50 berarti tidak ada transaksi, bukan keberhasilan strategi. Spread/slippage proxy sudah termuat dalam P/L melalui harga fill; jangan dikurangkan lagi dari saldo akhir. Kolom biaya hanya atribusi pendekatan. Profit factor tanpa kerugian dapat tak terbatas; JSON menyimpannya sebagai string `Infinity`, tanpa menyiratkan kepastian hasil.

## Audit dan batas data

Agregasi hanya menggunakan grup M5 yang lengkap, berurutan, dan tepat sejajar dengan awal M15/H1 (3 atau 12 bar). Open/close/high/low dibandingkan dalam integer tick tepat **0,001**; tick volume dan real volume dijumlahkan. Grup tidak lengkap dilewati; tidak dibuat bar untuk akhir pekan, libur, jeda sesi, atau history yang hilang. Perbedaan antar-timeframe adalah temuan untuk ditinjau, bukan otomatis bar rusak.

Waktu tetap `broker_server_unknown_offset`: clock server broker tanpa offset UTC/DST historis terverifikasi. Jam penelitian tidak boleh dilabeli sesi London/New York. Indikator menghitung bar yang tersedia; metadata kontrak/biaya adalah snapshot, bukan jadwal historis.

`experiment.json` dan laporan mencatat umur konteks HTF: waktu keputusan dikurangi waktu tutup M15/H1 yang dipilih. Dihitung jumlah umur ≥15/60 menit dan umur maksimum pada seluruh bar, bar siap, sinyal nonnol, serta kandidat jam riset 08:00–18:00. Ini diagnostik tanpa filter umur baru; konteks lama dapat mencerminkan penutupan sesi maupun data tidak tersedia.

OHLC Bid dan spread per bar tidak dapat merekonstruksi seluruh Bid/Ask intrabar. Ask dalam simulasi memakai proxy spread bar sebelumnya, sehingga requote, latensi, likuiditas, dynamic margin dan stop-out broker belum direplikasi. SL didahulukan bila SL/TP tersentuh dalam satu bar. Drawdown disampel pada close; penurunan intrabar dapat lebih besar.

Swap tidak dimodelkan. Pembatas sesi dan pergantian tanggal mengurangi carry dalam model, tetapi penutupan pada bar pertama setelah gap tidak membuktikan bebas rollover. Komisi nol, slippage, spread stress dan formula margin adalah asumsi penelitian. P/L hasil ini belum merupakan biaya/eksekusi real yang tervalidasi, dan tidak memprediksi pertumbuhan akun demo $50.

Tick volume adalah jumlah aktivitas quote, bukan volume jual/beli transaksi. Hasil lulus pengujian perangkat lunak, struktur CSV, atau backtest belum membuktikan keunggulan. Pengujian fixture sintetis tidak boleh disajikan sebagai performa pasar. Forward test demo MT5 dan rekonsiliasi eksekusi memerlukan tahap terpisah.

## Sumber primer

- [MQL5 CopyRates: history dan struktur data bar](https://www.mql5.com/en/docs/series/copyrates)
- [MQL5 MqlRates: OHLC, spread, tick volume dan real volume](https://www.mql5.com/en/docs/constants/structures/mqlrates)
- [MetaTrader 5: pembentukan harga dan volume pasar OTC](https://www.metatrader5.com/en/terminal/help/trading_advanced/price_data)
- [MQL5: properti simbol, lot, tick, swap dan model kalkulasi](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants)
- [Exness: spesifikasi komoditas](https://get.exness.help/hc/en-us/articles/17854173039388-Commodities)

Sumber tersebut mendukung semantik data dan spesifikasi produk. Aturan sinyal, bobot, risiko, jam, dan biaya stress dalam paket ini merupakan keputusan penelitian sendiri, bukan rekomendasi atau strategi resmi dari sumber tersebut.

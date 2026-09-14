# VORTEX XAU EXTREME v0.2

Model hipotesis baru untuk BACKTEST/PAPER; belum layak forward trading. Lihat
[SPEC.md](SPEC.md) untuk aturan yang dibekukan, [audit v0.1](../reports/v0.2/AUDIT-V0.1.md)
dan [September challenge](../challenge/README.md) untuk pemisahan target vs bukti.

Modal awal$50, deposit tambahan$0. Baseline mode NORMAL2%, AGGRESSIVE3.5%,
EXTREME5%; stress EXTREME7.5/10% terpisah dan tidak dapat dipromosikan otomatis.
Volume dibulatkan turun; lot minimum yang melampaui budget ditolak. Exit adaptif:
25/25/50 bila executable, selain itu satu posisi SL/trailing/TP2.5R.

## Modul

| Modul | Peran |
|---|---|
| `data.py` | Validasi UTC, H4 lengkap, session/DST, data point-in-time |
| `engines.py` | ORION/VORTEX/NOVA/LUNA/KIRA/ATLAS kausal dan voting |
| `risk.py` | Sizing/lot/margin/cost gate independen, tanpa broker |
| `backtest.py` | Simulator bid OHLC: entry, SL, exits, pyramids, financing, brakes |
| `statistics.py` | Expectancy dan moving-block bootstrap dengan seed tetap |
| `protocol.py` | Split60/20/20, expanding walk-forward, gate evaluasi |
| `run_research.py` | Semua profil/biaya, hash sebelum run, laporan, snapshot |

## Menjalankan

Python3.12 pada lingkungan virtual. Dari direktori ini:

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python run_research.py --data ../data/<run-export> --out ../local-results/v02-new-run
```

Runner menolak menimpa output yang sudah ada. Dataset privat asli diperlukan
untuk mereproduksi hasil pasar; synthetic tests tidak memerlukan akun broker.
Arsip berisi `preregistration.json` sebelum kalkulasi, parameter, sumber/hash,
100 skenario, jurnal dan equity lengkap. Ringkasan/hash dipublikasikan; CSV
besar tetap lokal. Tidak ada optimasi atau pemilihan parameter setelah hasil.

## Input eksternal wajib

Tambahkan `--news calendar.csv --coverage coverage.csv --macro macro.csv` untuk
arsip historis yang provenance/availability-nya dapat diaudit. Semua timestamp
harus ber-offset atau Z. Jangan memasukkan data revisi final seolah diketahui
di masa lalu. Header:

```csv
event_time,known_at,currency,impact,title
```

```csv
start,end,known_at
```

```csv
observed_at,available_at,dxy,us10y_yield
```

News memakai USD/impact=`high`; coverage membuktikan jendela kalender memang
tersedia termasuk ketika tidak ada event. Macro yield dalam percentage points,
bukan basis points. Current feed/history ini belum tersedia pada arsip ekspor.
Input hilang menghasilkan INVALID dan entry diblokir; tidak ada sakelar untuk
menganggap no-news atau mengarang skor ATLAS. Provider/adaptor data berbayar
tidak diciptakan tanpa konfigurasi pengguna.

## Pembacaan hasil

IS/validation/OOS dan walk-forward pada data v0.1 bersifat retrospektif karena
seluruh dataset sudah dilihat. Diperlukan data unseen baru setelah freeze dan
riwayat biaya broker untuk menilai statistik.0 trade berarti expectancy, PF,
confidence interval dan probabilitas ruin belum dapat dihitung. $50 yang tetap
utuh tanpa trade bukan hasil proteksi modal. Target yang belum tercapai sebelum
akhir dataset adalah censored; simulator tidak menciptakan harga masa depan.

Margin/biaya/slippage/rollover masih asumsi offline. Source contract snapshot
dan skenario stress dicatat terpisah dari sejarah biaya broker. SL-first pada
candle yang menyentuh dua batas adalah asumsi konservatif, bukan rekonstruksi
urutan tick. Forward DEMO menunggu baseline dan review; REAL tidak aktif.

# VORTEX-XAU-v0.1 — hipotesis sinyal baru

Ini implementasi riset baru untuk XAUUSD. Ini **bukan audit/replikasi** `vortex_x100.py` yang belum tersedia, dan belum menjadi bukti strategi mempunyai keunggulan. Modul hanya membaca CSV dan menghitung sinyal; tidak mengakses akun, jaringan, atau fungsi transaksi. Saldo demo tidak menentukan skor sinyal.

## API

```python
from vortex_xau.signals import load_exporter_data, build_signals, build_signals_from_export

frames = load_exporter_data(run_dir)  # dict: M5, M15, H1
result = build_signals(frames['M5'], frames['M15'], frames['H1'])
# atau: result = build_signals_from_export(run_dir)
```

Input adalah tiga file `XAUUSD_M5.csv`, `XAUUSD_M15.csv`, `XAUUSD_H1.csv` dari exporter. Simbol harus persis `XAUUSD`; suffix lain sengaja ditolak untuk versi penelitian ini. Modul memeriksa CSV tidak kosong, timestamp unik/berurutan naik, harga finite/positif dan hubungan OHLC masuk akal, volume/spread integer nonnegatif, serta label simbol/timeframe/timezone. Timestamp string harus `YYYY-MM-DDTHH:MM:SS`; input DataFrame juga boleh memakai DatetimeIndex tanpa zona waktu.

Output memakai indeks `bar_open_server` dan mempertahankan seluruh bar M5. Kolom untuk simulator: `open,high,low,close,spread_points,atr,signal,ready`. Ada enam skor huruf kecil, `consensus`, `decision_time`, dan waktu buka/tutup konteks M15/H1 untuk audit. `signal` bernilai +1/-1/0; bar belum siap memiliki 0, skor dan consensus NaN. `atr` adalah ATR M5 dalam satuan harga.

## Clock dan urutan data

Seluruh waktu adalah clock server broker; label persisnya `broker_server_unknown_offset`. Offset UTC/DST belum diketahui dan tidak dikonversi. Modul mengandalkan ekspor closed-bar yang sudah diperiksa; tanpa snapshot manifest modul sendiri tidak membuktikan bar terakhir sudah closed.

Sinyal bar M5 baru tersedia pada `bar_open_server + 5 menit`. Konteks HTF digabung dengan ASOF mundur pada **waktu tutup**: waktu buka HTF + durasinya harus ≤ waktu keputusan M5. Kesamaan waktu diizinkan; HTF yang baru selesai tepat pada keputusan dapat digunakan. Simulator wajib membaca sinyal dari bar sebelumnya dan entry paling cepat di open bar selanjutnya; jangan memakai high/low berikutnya untuk keputusan entry.

Gap tetap dipertahankan, tanpa pengisian, pengurutan ulang, atau penghapusan duplikat. Window indikator menghitung bar yang benar-benar tersedia, termasuk melintasi penutupan pasar. ASOF memakai konteks terakhir yang telah selesai tanpa batas umur tambahan; aturan penghentian ketika data terlalu lama perlu ditangani terpisah oleh simulator/operasional. Ini bukan sertifikasi kelengkapan history atau konsistensi agregasi tiga timeframe.

## Indikator dan kesiapan

- EMA 20/50/200 di setiap timeframe: pandas `ewm(span=n, adjust=False, min_periods=n)`. Nilai awal rekursi adalah close pertama; EMA baru tersedia setelah n observasi.
- RSI14: perubahan close, gain/loss terpisah, seed rata-rata sederhana 14 perubahan pertama, kemudian rekursi Wilder alpha=1/14. Keduanya nol → 50; loss nol dan gain positif → 100; gain nol dan loss positif → 0. Sebelum seed tersedia hasil NaN.
- ATR14: true range maksimum dari high−low, |high−close sebelumnya| dan |low−close sebelumnya|. TR bar pertama memakai high−low. Seed rata-rata 14 TR pertama lalu Wilder alpha=1/14.
- ROC12 = `(close / close 12 bar sebelumnya − 1) × 100`.
- High/low rentang dan rata-rata tick volume memakai **20 bar sebelumnya, tidak termasuk bar sekarang**.
- `ready` membutuhkan seluruh fitur finite di M5 serta konteks M15/H1 yang tersedia dan fitur finite, termasuk EMA200 di ketiganya. ATR M5, lebar rentang sebelumnya dan rata-rata tick volume sebelumnya juga harus positif. Pembagian nol menghasilkan WAIT, bukan skor buatan. Kondisi ini hanya kesiapan fitur, bukan kelayakan eksekusi.

## Enam skor

Semua skor dibatasi −100 sampai +100. Alignment sebuah timeframe adalah +100 bila `close > EMA20 > EMA50 > EMA200`, −100 bila seluruh urutannya terbalik, selain itu 0. Perbandingan alignment bersifat ketat.

| Engine | Aturan baru v0.1 | Bobot |
| --- | --- | ---: |
| ORION | Rata-rata alignment M5, M15 dan H1 | 22% |
| VORTEX | Rata-rata `clip((RSI−50)×4)` dan `clip(ROC12/(ATR/close×100)×50)`; indikator dari M5 | 18% |
| NOVA | +100 jika close M5 di atas prior20 high; −100 jika di bawah prior20 low; selain itu `clip((close−midrange)/(range/2)×100)` | 20% |
| LUNA | `clip((close−open)/ATR×100) × min(tick_volume/prior20_mean_tick_volume,1)` dari M5 | 15% |
| KIRA | `sign(close−EMA20)×100` bila ATR/close M5 berada di 0,0003–0,005, kedua batas termasuk; selain itu 0 | 10% |
| ATLAS | Rata-rata alignment M15 dan H1 | 15% |

`clip` pada tabel berarti batas −100/+100. LUNA adalah proxy aktivitas quote dan body candle, **bukan taker-buy ratio, order flow transaksi, atau probabilitas**. Rentang volatilitas KIRA adalah asumsi penelitian yang belum dioptimasi/tervalidasi; nilainya 0 di luar rentang, bukan veto global atas consensus. ATLAS hanya konteks, bukan risk gate. Keenam skor memakai data yang tumpang tindih sehingga tidak independen.

Consensus adalah jumlah skor × bobot. Saat ready: consensus ≥75 → +1, ≤−75 → −1, selain itu 0. Tidak ada kalibrasi probabilitas, penentuan lot, X-MODE sizing, stop/TP, biaya, atau pengiriman order dalam modul ini.

## Pemeriksaan

`tests/test_signals.py` memakai **data sintetis berlabel**, bukan data pasar/performance trading. Kasus meliputi batas waktu HTF, perubahan bar masa depan yang tidak boleh mengubah output sebelumnya, warm-up EMA200 H1, RSI datar/naik/turun, dan pengecualian bar berjalan dari prior range/volume. Hasil pengujian dan backtest broker perlu dilaporkan terpisah; angka synthetic bukan hasil profit.

# Riset XAUUSD — simulasi awal $50

Hasil berikut berasal dari simulasi historis offline atas hipotesis baru VORTEX-XAU-v0.1. Ini bukan transaksi atau pertumbuhan saldo akun demo MT5. Program tidak menghubungi broker dan tidak mengirim order.

Eksperimen: `xau-50-fixed-grid-v0.1`. Empat tingkat risiko dan dua asumsi biaya ditetapkan sebelum perhitungan; seluruh hasil ditampilkan tanpa memilih pemenang atau mengoptimasi parameter.

Struktur CSV: lolos. Temuan untuk ditinjau: 0. Lihat `audit.json` untuk agregasi timeframe, SHA-256, gap, dan manifest.

## Umur konteks timeframe

Sinyal memakai konteks HTF terakhir yang sudah selesai tanpa batas umur tambahan. Tabel ini hanya diagnostik dan tidak mengubah sinyal. Konteks lama dapat terjadi karena sesi tutup atau history tidak tersedia; tidak otomatis berarti data rusak. Kandidat jam riset berarti ready + sinyal nonnol + waktu keputusan 08:00–18:00 menurut clock server, belum tentu menjadi entry.

| HTF | Subset | Bar | Umur ≥ satu HTF | Umur maksimum (menit) |
| --- | --- | ---: | ---: | ---: |
| M15 | Fitur siap | 32490 | 236 | 4390.0 |
| M15 | Sinyal nonnol | 2921 | 20 | 3190.0 |
| M15 | Kandidat jam riset | 1201 | 0 | 10.0 |
| H1 | Fitur siap | 32490 | 1304 | 4435.0 |
| H1 | Sinyal nonnol | 2921 | 117 | 3235.0 |
| H1 | Kandidat jam riset | 1201 | 0 | 55.0 |

## Pembagian data

Pembagian memakai hari kalender dalam clock server broker: 60% development, 20% validation, dan sisa hari holdout. Ketiga bagian terpisah; simulasi seluruh periode bertumpang tindih dan hanya deskriptif. Saldo direset $50 untuk setiap skenario. Indikator dihitung secara kausal sekali atas seluruh data; setiap bagian dapat membawa riwayat indikator sebelumnya, tetapi tidak membawa posisi atau saldo. Bar pertama setiap bagian tidak dipakai untuk entry.

| Bagian | Awal inklusif server | Akhir eksklusif server | Bar M5 |
| --- | --- | --- | ---: |
| Seluruh periode (deskriptif) | 2026-03-18T00:00:00 | 2026-09-15T00:00:00 | 34890 |
| Development | 2026-03-18T00:00:00 | 2026-07-04T00:00:00 | 21039 |
| Validation | 2026-07-04T00:00:00 | 2026-08-09T00:00:00 | 6900 |
| Holdout | 2026-08-09T00:00:00 | 2026-09-15T00:00:00 | 6951 |

## Hasil seluruh skenario

Risiko adalah batas anggaran stop yang direncanakan per entry, bukan jaminan rugi maksimum. Lot selalu dibulatkan turun; jika 0,01 lot melebihi anggaran, sinyal dilewati. Drawdown di bawah disampel pada penutupan bar dan dapat lebih kecil daripada penurunan intrabar yang sebenarnya.

| Bagian | Risiko | Biaya | Saldo akhir | P/L bersih | Trade | Win rate | Drawdown close | Lewat: min lot |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Seluruh periode (deskriptif) | 3.00% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 1201 |
| Seluruh periode (deskriptif) | 3.00% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 1201 |
| Seluruh periode (deskriptif) | 5.00% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 1201 |
| Seluruh periode (deskriptif) | 5.00% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 1201 |
| Seluruh periode (deskriptif) | 7.50% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 1201 |
| Seluruh periode (deskriptif) | 7.50% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 1201 |
| Seluruh periode (deskriptif) | 10.00% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 1201 |
| Seluruh periode (deskriptif) | 10.00% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 1201 |
| Development | 3.00% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 701 |
| Development | 3.00% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 701 |
| Development | 5.00% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 701 |
| Development | 5.00% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 701 |
| Development | 7.50% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 701 |
| Development | 7.50% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 701 |
| Development | 10.00% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 701 |
| Development | 10.00% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 701 |
| Validation | 3.00% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 241 |
| Validation | 3.00% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 241 |
| Validation | 5.00% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 241 |
| Validation | 5.00% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 241 |
| Validation | 7.50% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 241 |
| Validation | 7.50% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 241 |
| Validation | 10.00% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 241 |
| Validation | 10.00% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 241 |
| Holdout | 3.00% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 259 |
| Holdout | 3.00% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 259 |
| Holdout | 5.00% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 259 |
| Holdout | 5.00% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 259 |
| Holdout | 7.50% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 259 |
| Holdout | 7.50% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 259 |
| Holdout | 10.00% | baseline | $50.00 | $0.00 | 0 | — | 0.00% | 259 |
| Holdout | 10.00% | stress | $50.00 | $0.00 | 0 | — | 0.00% | 259 |

Sebanyak 32 dari 32 skenario tidak menghasilkan trade. Saldo yang tetap $50 pada skenario tersebut berarti tidak ada transaksi simulasi, bukan bukti perlindungan modal atau keunggulan strategi.

## Asumsi dan batas hasil

- Baseline: spread bar sebelumnya ×1 dan slippage $0,03 per ons per sisi yang memakai market/stop fill. Stress: spread ×2 dan slippage $0,10. Ini sensitivitas biaya, bukan estimasi biaya broker yang sudah divalidasi.
- OHLC adalah harga Bid. Ask dibentuk dari proxy spread bar sebelumnya; pergerakan Bid/Ask intrabar, antrean, requote dan likuiditas tidak direkonstruksi. Jika SL dan TP tersentuh dalam satu bar, SL didahulukan.
- Komisi diasumsikan nol dan swap tidak dimodelkan. Posisi ditutup pada aturan sesi/pergantian tanggal yang tersedia, tetapi gap data tidak menjamin nihil rollover. Hasil bukan P/L setelah seluruh biaya broker yang terverifikasi.
- Leverage 1:2000 dan pembatas margin memakai pendekatan sederhana; perubahan margin, persyaratan khusus berita dan stop-out broker belum direplikasi.
- Pembatas rugi harian diperiksa pada open/close; gap dapat melampaui batasnya. Tidak ada martingale, kenaikan risiko otomatis, atau transfer dana ke vault.
- Jam 08:00–18:00 adalah pembatas riset menurut clock server, bukan identifikasi sesi London/New York. Offset UTC/DST historis belum diketahui.
- Tick volume adalah aktivitas quote, bukan volume jual/beli transaksi. Kelengkapan history belum tersertifikasi dan gap tidak otomatis berarti data rusak.
- Holdout dihitung satu kali dengan aturan tetap. Hasil yang sudah dibaca tidak boleh dipakai berulang untuk memilih parameter lalu disebut holdout baru. Tidak ada Monte Carlo, pemilihan skenario terbaik, atau klaim keunggulan.

Seluruh trade, equity dan event tersedia per skenario. `experiment.json` menyimpan konfigurasi, rentang, hash data/kode, versi runtime, dan status eksekusi. `summaries.csv` memuat hasil mentah; `signals.csv` memuat sinyal beserta konteks waktunya.

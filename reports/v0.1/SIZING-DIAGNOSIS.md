# Mengapa simulasi VORTEX-XAU-v0.1 tidak membuka posisi

**Seluruh 1.201 kandidat entry pada periode penuh ditolak karena ukuran posisi hasil perhitungan lebih kecil daripada minimum 0,01 lot.** Saldo awal US$50 tidak berubah karena tidak ada transaksi simulasi yang terjadi. Hasil ini belum menguji profit/loss transaksi atau membuktikan keunggulan strategi.

Pemeriksaan independen membaca `signals.csv`, konfigurasi yang sudah dibekukan di `experiment.json`/`summary.json`, dan jurnal `events.csv`. Kandidat dihitung dari sinyal nonzero yang sudah ready pada bar sebelumnya, bar berikutnya tepat berjarak 5 menit, dan waktu entry 08:00 sampai sebelum 18:00 dalam clock server broker. Hasilnya **468 kandidat long dan 733 short**. Seluruh timestamp kandidat cocok persis dengan penolakan `min_lot` pada delapan skenario periode penuh: empat tingkat risiko × baseline/stress.

## Perhitungan yang diperiksa

Asumsi v0.1: contract size 100 ounce/lot, minimum dan step 0,01 lot, SL 2,2 × ATR M5 sebelumnya dengan batas minimum 10 tick; tick harga 0,001. Jarak stop dibulatkan ke luar lalu harga SL ke grid tick absolut, sesuai sumber simulator yang telah dijalankan. Baseline memakai slippage US$0,03/ounce per sisi dan komisi nol sebagai asumsi riset.

Untuk minimum 0,01 lot (=1 ounce), planned loss sampai SL adalah:

`0,01 × [100 × (jarak SL setelah pembulatan + 2 × slippage per sisi) + 2 × komisi per lot per sisi]`

Ini estimasi stop-loss dalam model, bukan jaminan kerugian maksimum saat eksekusi broker. Seluruh kandidat juga lolos pemeriksaan bahwa quote pembukaan belum melewati SL; penolakan awalnya memang `min_lot`.

| Profil biaya | Risiko minimum 0,01 lot terendah | Median | Tertinggi |
| --- | ---: | ---: | ---: |
| Baseline: spread ×1; slippage US$0,03/sisi | US$5,761 | US$13,649 | US$34,246 |
| Stress: spread ×2; slippage US$0,10/sisi | US$5,901 | US$13,789 | US$34,386 |

Tabel memakai pembulatan persis implementasi v0.1. Sebelum pembulatan stop, angka baseline sekitar US$5,7591 / US$13,6473 / US$34,2452. Secara praktis, minimum risiko baseline sekitar **US$5,76**, median **US$13,65**, dan maksimum **US$34,25**.

| Risiko per kandidat | Budget dari saldo US$50 |
| --- | ---: |
| 3% | US$1,50 |
| 5% | US$2,50 |
| 7,5% | US$3,75 |
| 10% | US$5,00 |

Bahkan budget terbesar US$5,00 masih di bawah kebutuhan minimum terendah US$5,761. Pada skenario 10% baseline, ukuran mentah terbesar hanya sekitar **0,008679 lot**. Dibulatkan turun ke step 0,01 lot, hasilnya 0 lot; sistem tidak menaikkannya menjadi 0,01 lot untuk memaksakan entry. Keempat tingkat risiko karena itu menghasilkan penolakan pada semua kandidat tersebut.

## Batas kesimpulan

Pemeriksaan terhadap **32 summary** juga cocok: masing-masing 0 transaksi, net profit US$0 dan final equity US$50. Win rate/expectancy belum tersedia; equity datar dan drawdown nol di sini merupakan konsekuensi tidak membuka posisi, bukan bukti performa trading atau pengujian biaya/fill pada transaksi nyata. Periode penuh tumpang tindih dengan development/validation/holdout sehingga bukan sampel validasi tambahan yang independen.

Tidak ada parameter yang diubah atau pengujian ulang untuk mencari hasil yang menguntungkan dalam diagnosis ini. Holdout yang sudah dijalankan tetap dipertahankan sebagai hasil versi v0.1.

Sumber yang diperiksa: `signals.csv`, `experiment.json`, dan `scenarios/*/summary.json`; kecocokan timestamp diuji terhadap `scenarios/full_*/events.csv`. SHA-256 `signals.csv`: `634c527ac4be512867991a3216af24aee4a6acb31b939681c16aa99c1621e3a4`. SHA-256 simulator yang tercatat pada eksperimen: `14745b70d5ac0afa715a2d8b1a03c13e467aea8180c773374242eeb28394068a`.

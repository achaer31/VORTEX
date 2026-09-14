# v0.2 — NO-GO, belum dapat dievaluasi secara statistik

Eksperimen `xau50-fixed-v02-001`, model `VORTEX-XAU-EXTREME-v0.2`, amendment A1
sesuai permintaan pengguna: modal$50, tanpa top-up, adaptive exits dan stress
EXTREME7.5/10% terpisah. Seluruh100 skenario selesai. Tidak ada order broker.

**100/100 skenario: equity akhir$50, P/L$0,0 campaign,0 trade,0 pyramid.**
Semua34.890 keputusan M5 diblokir karena kalender berita dan macro point-in-time
tidak tersedia. Saldo datar bukan bukti profitabilitas atau perlindungan modal.

## Perbandingan profil

Tabel ini merangkum hasil seluruh periode; kedua biaya menghasilkan hasil sama
karena tidak ada transaksi. Semua hasil IS, validation, OOS retrospektif dan
walk-forward tercantum lengkap di `summaries.csv` dan100 `scenarios/*/summary.json`.

| Profil | Budget base maksimal dari$50 | Equity akhir | Campaign | DD teramati |
|---|---:|---:|---:|---:|
| Cap mode2% |$1.00|$50.00|0|0%|
| Cap mode3.5% |$1.75|$50.00|0|0%|
| Baseline NORMAL2/AGGRESSIVE3.5/EXTREME5% |$2.50|$50.00|0|0%|
| Stress EXTREME7.5%, mode lain tetap |$3.75|$50.00|0|0%|
| Stress EXTREME10%, mode lain tetap |$5.00|$50.00|0|0%|

Multiple saldo teramati1.00×; tidak ada distribusi return transaksi. Expectancy,
profit factor, geometric growth per campaign, confidence interval, target-hit
probability dan risk-of-ruin probability adalah **N/A**, bukan nol. Tidak ada
milestone100/250/500/1000/50000 tercapai pada data ini. Seluruh run berakhir
karena data habis (censored), bukan karena berhasil menyelesaikan challenge.
Tidak ada pemilihan pemenang berdasarkan saldo akhir.

## Data dan walk-forward

Arsip asli:34.890 M5,11.630 M15,2.908 H1;630 H4 lengkap diturunkan hanya dari
kelompok empat H1 yang tepat. Rentang18 Maret–14 September2026. Clock Exness
GMT+0 adalah asumsi v0.2 yang didokumentasikan; label unknown-offset pada raw
export dan arsip v0.1 dipertahankan.

Pembagian kalender60% IS/20% validation/20% OOS tidak tumpang tindih. Expanding
walk-forward memakai warmup awal60 hari, test20 hari, maju20 hari:6 jendela test
terpisah. Tidak ada fitting/optimasi; indikator hanya memakai data sebelumnya.
Setiap skenario reset ke$50 dan tidak mewarisi posisi/equity skenario lain.
Skenario full bersifat deskriptif dan tumpang tindih dengan bagian lain.

Seluruh dataset telah dilihat di v0.1. Karena itu **OOS dan walk-forward ini
retrospektif, bukan validasi unseen**. Mengganti nama bagian data tidak menghapus
kontaminasi. Batas waktu/hashes lengkap ada di `preregistration.json`.

## Mengapa tidak ada entry

- Kalender point-in-time hilang:34.890 bar. Macro DXY/yield hilang:34.890 bar.
  ATLAS INVALID sepanjang data; tidak diisi0 atau skor netral rekaan.
- ORION belum valid pada16.444 bar karena warmup/freshness H4 dan HTF lain.
  VORTEX invalid33, NOVA/LUNA masing-masing294, KIRA444. Ini diagnosa kesiapan
  data, bukan statistik kemenangan modul.
- Secara terpisah,52.460 anchor stop dua arah yang diketahui membutuhkan risiko
  minimum0.01lot mulai sekitar$6.1700, median$13.3247 pada asumsi baseline.
  Stress mulai$6.5480, median$13.7187. Perhitungan ini diagnostik pada stop
  historis, **bukan kandidat yang lolos voting atau simulasi fill berikutnya**.
  Angka minimum itu pun lebih besar dari budget$5 pada stress10% modal$50.

Adaptive exit tetap mengizinkan0.01lot bila risk gate membiayainya. Tidak ada
round-up, kenaikan modal, penyempitan stop untuk memaksa lot, atau pelepasan
filter wajib. Kekurangan data dan ketidakcocokan ukuran kontrak/modal adalah
dua hambatan berbeda.

## Biaya dan realisme

Baseline: spread bar sebelumnya×1, market/stop slippage$0.03/oz/sisi, komisi
$0/lot/sisi sebagai asumsi belum terverifikasi. Stress: spread×2, slippage$0.10,
komisi$3.50/lot/sisi. Swap baseline long−$53.49/lot/hari, short0, Wednesday triple,
berdasarkan snapshot terbaru; stress long−$106.98, short−$5/lot/hari.

Snapshot bukan jadwal historis biaya broker. Bid OHLC dengan proxy Ask, urutan
SL-first dan gap fills tidak menggantikan tick bid/ask. Simulator mencakup
financing, adaptive exit, max2 winner adds, risk caps dan daily/streak limits.
Tidak adanya trade berarti biaya terealisasi nol dan kemampuan mekanik ini
dibuktikan melalui tes sintetis, bukan performa pasar.

## Validasi software dan keputusan

73 tes v0.2 lulus, termasuk42 jalur eksekusi.37 tes arsip v0.1 tetap lulus.
Tes mencakup no-lookahead HTF/pivots, data eksternal available_at, exit minimum
lot, adaptive partial/single trail, swap yang memicu kill, stop-gap, quote Ask
untuk SHORT, max2 adds, no averaging loser dan penghentian setelah3 loss.
Hash sumber/artefak diverifikasi setelah run.73 tes bukan73 eksperimen profit.

**Gate: NOT_EVALUABLE / NO-GO.** Belum ada forward demo aktif atau real trade.
Butuh data berita/macro point-in-time, biaya/metadata broker yang sesuai,
pengujian unseen setelah freeze, dan sampel campaign cukup sebelum review
baseline. Deadline September dan target$50.000 tidak mengubah gate.

Tidak ada alasan untuk menyimpulkan strategi ini rugi maupun untung dari0trade.
Tidak dilakukan optimasi lanjutan pada data ini. Hipotesis lanjutan tersedia di
[V03-HYPOTHESES.md](V03-HYPOTHESES.md), belum diuji/diaktifkan.

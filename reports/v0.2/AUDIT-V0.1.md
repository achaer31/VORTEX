# Audit v0.1 sebelum v0.2

v0.1 adalah hipotesis riset offline, bukan engine trading aktif. Arsip asli tetap
utuh. Pengujian ulang37 tes audit/sinyal/simulator lulus pada14 September2026.

| Temuan | Konsekuensi untuk v0.2 |
|---|---|
| Semua32 skenario berakhir$50, tanpa trade | Tidak ada bukti expectancy/profit; saldo datar bukan keberhasilan |
|1.201 kandidat full ditolak minimum lot | Stop termurah .01lot memerlukan$5.761, lebih dari budget$5 pada risiko10%; batas modal/kontrak dominan |
| LUNA adalah proxy body/tick-volume | Diganti deteksi sweep dan reclaim eksplisit |
| ATLAS adalah alignment M15/H1 | Diganti input macro, kalender, session, execution; data hilang INVALID |
| Tidak ada H4, partial TP, runner, pyramid | Ditambahkan sebagai model baru dan diuji sintetis terpisah |
| Risk3/5/7.5/10%, stop2.2×ATR_M5 | Hipotesis baru memakai2/3.5/5% mode, stop ATR_M15+structure, batas total7.5% |
| Clock asli unknown-offset; session08–18 | v0.2 mendokumentasikan asumsi Exness GMT+0 dan session lokal/DST |
| Biaya bar-spread dan slip; komisi0, swap tak dimodelkan | Sensitivitas komisi dan snapshot swap ditambahkan; bukan biaya historis terverifikasi |
| Holdout lama sudah dilihat | Label OOS baru pada data yang sama hanya pembagian retrospektif; tidak mengembalikan status unseen |
| DD disampel bar, intrabar bid/ask tak tersedia | Jalur OHLC konservatif, batas stop/DD bukan jaminan; ticks masih diperlukan |

Snapshot kontrak yang diekspor:100oz/lot, tick/point.001, minimum/step.01lot,
swap long−534.9points, short0, Wednesday triple. Metadata menyatakan snapshot
sekarang, bukan jadwal kontrak/biaya historis. Commission tidak tersedia dari
symbol properties. Tidak ada login/password/nomor akun dalam laporan.

Perubahan parameter v0.2 datang dari hipotesis pengguna yang baru; hasil v0.1
tidak dipoles, disembunyikan, atau dipakai memilih parameter yang tampak profit.

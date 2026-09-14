# Validasi ekspor pertama

Pada 14 September 2026, `VortexExport.mq5` berhasil dikompilasi dengan MetaEditor/MT5 build 6182: **0 error, 0 warning**. Script mengumpulkan data harga tanpa mengirim order.

| Timeframe | Bar | Validasi awal |
| --- | ---: | --- |
| M5 | 34.890 | Header dan manifest cocok; 0 bar invalid; 0 kesalahan urutan |
| M15 | 11.630 | Header dan manifest cocok; 0 bar invalid; 0 kesalahan urutan |
| H1 | 2.908 | Header dan manifest cocok; 0 bar invalid; 0 kesalahan urutan |

Audit Python membandingkan 11.628 grup M15 lengkap dan 2.903 grup H1 lengkap terhadap agregasi M5. OHLC, tick volume, dan real volume cocok. Grup parsial dilewati; gap tidak diisi.

Rentang M5 aktual: 18 Maret 2026 04:55 hingga 14 September 2026 04:45 dalam clock broker. Offset UTC/DST belum diverifikasi. `history_incomplete=unknown` bukan jaminan kelengkapan history.

Hash arsip ekspor asli: `c83dac61a5148198114b4c76900974357bcabe1f5f8dfce523d9f3c8a852de7e`. Hash setiap CSV ada dalam [experiment.json](../reports/v0.1/experiment.json). Detail validasi ada dalam [audit.json](../reports/v0.1/audit.json).

Catatan ini sengaja tidak menyimpan konfigurasi remote desktop, identifier akun, atau kondisi sesi pribadi. Untuk mengumpulkan dataset sendiri, ikuti [panduan exporter](../exporter/README-exporter.md).

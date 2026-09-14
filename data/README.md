# Data lokal

Simpan hasil ekspor MT5 dalam `data/<nama-run>/`. Isi direktori ini selain README diabaikan Git. Dataset broker lengkap dan arsip aslinya tetap berada pada penyimpanan lokal pemilik; tidak disalin ke repo publik.

File yang dibutuhkan: `XAUUSD_M5.csv`, `XAUUSD_M15.csv`, `XAUUSD_H1.csv`, `manifest.csv`, dan `metadata.csv`. Prosedur tersedia di [exporter](../exporter/README-exporter.md).

Untuk mengulang **persis** eksperimen v0.1, gunakan CSV asli dengan SHA-256 yang tercatat dalam [experiment.json](../reports/v0.1/experiment.json). Ekspor baru dapat memiliki rentang atau revisi history berbeda. Repo saja tidak cukup untuk mereproduksi seluruh hasil pasar tanpa dataset tersebut; unit test menggunakan fixture sintetis dan tetap dapat berjalan tanpa MT5.

Dashboard menyertakan cuplikan harga historis dan hasil agregat yang telah dipilih secara eksplisit untuk publikasi. Cuplikan ini bukan pengganti dataset penuh atau feed harga langsung.

# Arsip hasil VORTEX-XAU-v0.1

[Laporan](REPORT.md) dan [diagnosis ukuran posisi](SIZING-DIAGNOSIS.md) berasal dari eksperimen yang benar-benar dijalankan pada 14 September 2026. Semua 32 skenario berakhir pada saldo simulasi $50 dengan 0 transaksi.

Repo menyimpan konfigurasi, audit, tabel hasil, dan 32 ringkasan skenario. File `signals.csv`, `equity.csv`, `events.csv`, dan `trades.csv` lengkap yang disebut laporan berada dalam arsip lokal asli. File besar dan duplikat tersebut tidak disertakan dalam Git. [artifact-manifest.json](artifact-manifest.json) mencatat ukuran dan SHA-256 seluruh artefak asli agar perubahan dapat diperiksa.

Enam file sumber yang disebut `source_sha256` di `experiment.json` disalin tanpa perubahan ke `research/`; hash merujuk isi file, bukan letaknya. Dokumen tambahan dan dashboard dibuat setelah eksperimen selesai dan tidak mengubah hasil atau parameter v0.1.

Untuk menghasilkan kembali CSV lengkap, lihat [cara menjalankan riset](../../research/README.md) dan [kebutuhan dataset](../../data/README.md). Gunakan folder keluaran baru untuk setiap eksperimen. Holdout v0.1 sudah dilihat dan tidak boleh disebut data uji baru pada pengembangan berikutnya.

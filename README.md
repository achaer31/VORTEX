# VORTEX · XAUUSD Research

Mesin riset historis dan dashboard untuk melihat data harga, enam skor strategi, hasil simulasi, dan alasan sistem melewati entry.

**[Buka dashboard VORTEX](https://vortex-xau.vercel.app)** · [catatan deployment](docs/DEPLOYMENT.md)

**Status v0.1: 32 skenario, saldo simulasi awal $50, saldo akhir $50, 0 transaksi.** Seluruh 1.201 kandidat periode penuh ditolak karena kebutuhan risiko pada lot minimum melampaui budget. Ini belum membuktikan strategi menghasilkan profit. Akun demo MT5 dan saldo simulasi adalah dua hal terpisah.

## Mulai dari sini

- [Laporan eksperimen](reports/v0.1/REPORT.md) dan [diagnosis lot minimum](reports/v0.1/SIZING-DIAGNOSIS.md).
- [Riwayat perubahan](CHANGELOG.md) dan [commit GitHub](https://github.com/achaer31/VORTEX/commits/main).
- [Arsitektur dashboard, Vercel, dan VPS](docs/ARCHITECTURE.md).
- [Definisi enam skor strategi](research/SIGNALS.md).

| Direktori | Isi |
| --- | --- |
| `exporter/` | Script MQL5 pengumpul harga dan validator PowerShell |
| `research/` | Audit data, sinyal, simulator, runner, dan 37 unit test |
| `reports/v0.1/` | Laporan, parameter, hash, audit, dan ringkasan 32 skenario |
| `dashboard/` | Tampilan web dan cuplikan historis yang disiapkan untuk publikasi |
| `data/` | Petunjuk dataset lokal; CSV penuh tidak diunggah |
| `docs/` | Arsitektur dan catatan validasi |

## Jalankan riset

Gunakan Python 3.12 dan lingkungan virtual. Dari direktori `research`:

```sh
python -m pip install -r requirements-repro.txt
python -m unittest discover -s tests -v
python run_research.py --data ../data/<nama-run> --out ../local-results/<eksperimen-baru>
```

Unit test menggunakan fixture sintetis. Untuk mengulang eksperimen pasar persis seperti v0.1 diperlukan dataset asli dengan hash yang sesuai; lihat [data/README.md](data/README.md). Hasil besar tetap berada dalam arsip lokal, dengan fingerprint di [artifact-manifest.json](reports/v0.1/artifact-manifest.json).

## Buka dashboard

Dashboard berupa HTML, CSS, dan JavaScript statis. Dari root repo:

```sh
python -m http.server 8000 --directory dashboard
```

Buka `http://localhost:8000`. Chart adalah cuplikan harga historis; pergantian timeframe tidak mengambil harga baru. Pilihan skenario menampilkan hasil yang sudah dihitung, bukan menjalankan order atau simulasi baru.

Untuk Vercel, impor repo ini dengan Root Directory `dashboard`, Framework Preset **Other**, tanpa build command. Panduan dan batas pemantauan langsung ada di [arsitektur](docs/ARCHITECTURE.md).

Deployment pertama diterbitkan dari file dashboard yang sudah diverifikasi. Integrasi Git untuk penerbitan otomatis setiap push belum tersambung; perubahan repo tetap tercatat dan diuji oleh GitHub Actions.

## Riwayat dan batas versi

Riwayat Git dimulai saat impor pekerjaan pada 14 September 2026. Pekerjaan sebelumnya dicatat secara retrospektif di CHANGELOG; tidak ada rekonstruksi commit lama. Model XAU v0.1 adalah hipotesis baru karena implementasi BTC sebelumnya tidak tersedia.

Tidak ada koneksi broker atau pengiriman order dalam mesin Python/dashboard. Kredensial, identifier akun, screenshot pribadi, konfigurasi RDP, dan arsip mentah tidak masuk repo. Data OHLC dan spread proxy belum mereplikasi eksekusi tick broker; offset UTC/DST historis belum diverifikasi. Holdout v0.1 sudah digunakan dan tidak boleh dipakai memilih parameter lalu disebut data uji baru.

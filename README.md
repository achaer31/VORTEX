# VORTEX · XAUUSD Research

Mesin riset historis, infrastruktur demo dan dashboard untuk memeriksa data,
enam skor strategi, hasil simulasi, dan alasan sistem melewati entry.

**v0.2: NO-GO.100 skenario, modal awal$50, equity akhir$50,0 trade.** Kalender
berita/macro point-in-time belum tersedia; statistik strategi belum dapat
dievaluasi. [Laporan v0.2](reports/v0.2/REPORT.md) · [Konsol v0.2](https://vortex-xau.vercel.app/v02.html)
· [Kontrak runtime autonomous](docs/ARCHITECTURE-v02.md).

Exit adaptif dan stress EXTREME7.5/10% diuji terpisah dari baseline2/3.5/5%.
Modal tetap$50, top-up0; [September challenge](challenge/README.md) belum aktif.
Software runtime tidak memerlukan Astra/LLM. VPS/auto-start/rekonsiliasi/Mac-off
acceptance belum dijalankan, sehingga status **bukan AUTONOMOUS READY**.

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
| `research_v02/` | Model baru modular, adaptive exits, risk gate, walk-forward,73 tes |
| `reports/v0.1/` | Laporan, parameter, hash, audit, dan ringkasan 32 skenario |
| `reports/v0.2/` |100 skenario beku, audit, diagnosa, hash dan NO-GO |
| `live/` | Observer v0.2, demo safeguards, private publisher, optional Telegram |
| `cloud/` | Database, API privat dan template Docker; belum diprovision |
| `deploy/` | Paket Windows dan evidence gate autonomy; belum diterapkan |
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

Riset/dashboard tidak mengirim order. Adapter demo generik tersedia untuk tes
sintetis; arming/entry legacy diblokir, v0.2 broker execution belum diaktifkan.
Kredensial, identifier akun, screenshot pribadi, RDP dan arsip mentah tidak masuk
repo. Data OHLC/spread proxy belum mereplikasi tick broker; historical costs
belum terverifikasi. Holdout v0.1 sudah digunakan dan tidak boleh disebut unseen.

# VortexExport — ekspor manual data XAUUSD

Status: sumber MQL5 sudah dikompilasi di MetaEditor/MT5 build **6182 dengan 0 error dan 0 warning**. Ekspor dan validasi CSV di VPS berhasil untuk **34.890 bar M5, 11.630 bar M15, dan 2.908 bar H1**. Ketiganya memiliki `HeaderOK=True`, `ManifestOK=True`, `BadRows=0`, dan `OrderErrors=0`; ringkasannya disimpan dalam `validation-summary.csv` di folder hasil VPS. Ketiganya melaporkan `history_incomplete=unknown`, yang bukan bukti history lengkap. Lihat [catatan validasi ekspor](../docs/EXPORT-VALIDATION.md) untuk rincian. Ini pengumpul data sekali jalan, bukan bot trading atau pemantau terus-menerus.

## Menjalankan

1. Di MT5 Windows, pilih **File → Open Data Folder**. Salin `VortexExport.mq5` ke `MQL5\Scripts`.
2. Buka berkas itu di MetaEditor, tekan **F7**, dan pastikan hasil kompilasi tidak memiliki error sebelum menjalankan. Biarkan Algo Trading nonaktif; script tidak mengirim order dan tidak memerlukan izin DLL.
3. Pastikan terminal tersambung. Pilih simbol emas yang benar di Market Watch, lalu buka chart-nya. Nama harus diawali `XAUUSD` dan metadata mata uang harus XAU/USD. Simbol custom ditolak.
4. Jalankan **Scripts → VortexExport**. `ExportSymbol` kosong memakai simbol chart; isi nama broker yang persis jika perlu. `HistoryDays` default 180 hari kalender, dibatasi 1–366 hari.
5. Baca hasil di **File → Open Data Folder → MQL5 → Files → VortexExport**. Tiap eksekusi membuat subfolder baru. Tab Experts menampilkan jumlah bar tiap timeframe dan statusnya.

## Isi hasil

- `metadata.csv`: mata uang akun saja, simbol dan mata uang kontrak, ukuran kontrak/lot/tick, digit dan point, model eksekusi/perhitungan, spread snapshot, stop/freeze level, swap mode/long/short/hari triple, build terminal, dan koneksi. Field gagal dibaca diberi status unavailable. Angka enum mengikuti dokumentasi MQL5. Tidak ada nomor akun, nama pemilik, server login, saldo, kata sandi, atau riwayat transaksi.
- `XAUUSD…_M5.csv`, `_M15.csv`, `_H1.csv`: bar yang lolos pemeriksaan closed-bar, berurutan dari lama ke baru. Kolom: `bar_open_server,timezone,symbol,timeframe,open,high,low,close,tick_volume,spread_points,real_volume`. CSV dipisahkan koma dan memakai UTF-8.
- `manifest.csv`: rentang diminta dan rentang aktual, jumlah bar, hasil/error CopyRates, status sinkronisasi, awal history terminal/server, bar terakhir, gap, bar ditolak, status file dan `history_incomplete`. Bar kosong bukan keberhasilan pengumpulan data.

## Cara menafsirkan

Waktu disimpan sebagai `YYYY-MM-DDTHH:MM:SS` **dalam clock server broker dengan offset/DST belum diketahui**; tidak ada `Z` dan tidak diklaim UTC. Clock snapshot adalah `TimeCurrent`, yakni waktu quote server terakhir, sehingga dapat berhenti bergerak saat pasar tutup. Jangan menggabungkan kalender berita berbasis UTC sebelum offset historis diperiksa.

Interval berjalan pada snapshot dan bar paling baru yang diketahui MT5 dikeluarkan. Akibatnya, satu bar terakhir dapat sengaja tertinggal ketika pasar tutup. Data harga dan metadata biaya adalah data broker saat diekspor; metadata bukan jadwal historis perubahan kontrak/biaya. Komisi tidak tersedia dari properti simbol dan ditandai belum tersedia.

`history_incomplete=true` adalah tanda konservatif: data/error/sinkronisasi/cakupan tepi perlu diperiksa. `unknown` berarti tidak ditemukan masalah tersebut, **bukan bukti history lengkap**; `completeness_verified` tetap false. Weekend, jeda sesi, libur dan history hilang belum dibedakan. Tidak ada target jumlah bar dengan asumsi pasar buka 24/7. Tick volume adalah aktivitas quote, bukan volume transaksi beli/jual; `real_volume=0` tidak otomatis berarti tidak ada aktivitas pasar. Spread bar bukan rekaman seluruh perubahan spread intrabar, sehingga ekspor ini belum cukup untuk menguji eksekusi tick secara realistis.

Manifest mencatat `run_status` saat mulai dan saat selesai; gunakan baris terakhir untuk status akhir. `finished_with_data_issues` berarti metadata tidak berhasil ditulis, salah satu timeframe tidak menghasilkan bar, terjadi kegagalan file/history, atau pemeriksaan konservatif history menandai masalah. Baca `export_status` dan `history_incomplete` tiap timeframe untuk rinciannya. `finished` hanya berarti ekspor berakhir tanpa masalah yang terdeteksi, bukan bukti history lengkap; `write_error` menandai kegagalan penulisan yang terdeteksi pada metadata/manifest.

Script hanya meminta history **sekali per timeframe**, tanpa retry otomatis atau penantian berulang. MT5 dapat tetap menunggu timeout internal CopyRates dan melanjutkan unduhan history di latar belakang. Jika hasil kurang, biarkan history selesai tersinkronisasi lalu jalankan ulang secara manual. `Max bars in chart` bisa membatasi data; baca manifest sebelum menyimpulkan 180 hari telah tersedia. Untuk menghentikan script, gunakan kontrol MT5; manifest bisa masih berstatus `started` jika proses dihentikan sebelum penutupan.

## Validasi hasil

Jalankan `Validate-VortexExport.ps1 -RunPath '<folder hasil ekspor>'` melalui PowerShell. Validator membaca CSV hasil, memeriksa header, jumlah/rentang terhadap manifest, format dan aturan OHLC, volume/spread nonnegatif, urutan waktu, serta batas closed-bar. Ringkasan ditampilkan dan disimpan sebagai `validation-summary.csv` di folder hasil yang sama. Validator tidak mengakses akun atau terminal.

Hasil yang diharapkan: tiap timeframe memiliki bar, `HeaderOK=True`, `ManifestOK=True`, `BadRows=0`, dan `OrderErrors=0`. Periksa pula status ekspor, error CopyRates dan sinkronisasi. Lolos pemeriksaan ini belum membuktikan kelengkapan historis, offset waktu broker, atau realisme eksekusi transaksi.

## Referensi resmi

- [CopyRates: timeout, pengunduhan, urutan dan batas history](https://www.mql5.com/en/docs/series/copyrates)
- [Properti history: sinkronisasi dan rentang](https://www.mql5.com/en/docs/constants/tradingconstants/enum_series_info_integer)
- [Properti simbol: model eksekusi, lot, tick, swap dan enum](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants)
- [TimeCurrent: clock quote server](https://www.mql5.com/en/docs/dateandtime/timecurrent)
- [FileOpen: lokasi output terminal dan encoding](https://www.mql5.com/en/docs/files/fileopen)

# Bukti akun privat melalui MT5

[VortexAccountEvidence.mq5](VortexAccountEvidence.mq5) adalah script sekali jalan, baca-saja dan khusus DEMO/USD/Hedge. Default `EnableExport=false` dan `ExpectedDemoLogin=0` tidak membaca atau mengekspor akun. Nilai identitas hanya dimasukkan secara privat ketika script dijalankan; jangan menyimpannya dalam source, preset, screenshot publik, atau Git.

Script tidak mengirim/mengubah/menutup order, melakukan autentikasi, atau mengubah permission/Algo Trading. Tidak membutuhkan Python. Pada 14 September 2026 source ini dikompilasi di MetaEditor Exness dengan **0 error, 0 warning** dan satu capture DEMO aktual lolos pemeriksaan pengambilan. Data serta rekonsiliasi finansial tetap privat. [Bukti terbatas dan hash](native-validation-2026-09-14.json) tidak memberi GO atau membuktikan kelengkapan riwayat independen.

Sesudah opt-in, script memeriksa akun yang diharapkan dan meminta `HistorySelect(0, TimeTradeServer())`. Ia mengambil semua deal yang dikembalikan broker untuk interval tersebut, termasuk transaksi manual dan balance adjustment, tanpa filter magic/simbol. Tidak ada asumsi bahwa modal tetap $50. Getter yang gagal tidak diganti nol; error atau perubahan identitas/angka akun menghasilkan **INVALID**.

Lokasi keluaran adalah folder unik di `MT5 Data Folder/MQL5/Files/VortexAccountEvidence/`. Ini **arsip privat**, bukan asset dashboard:

- `deals.csv`: deal/order/position ID asli; waktu server dan nilai waktu mentah; type/entry/reason/magic; volume/harga/SL/TP; profit, komisi, swap dan fee; simbol, komentar serta external ID asli. Komentar adalah data, bukan instruksi.
- `account.csv`: snapshot balance/equity/profit/credit/margin/free margin, leverage serta jumlah posisi/order. Login, server, password dan IP tidak diekspor.
- `manifest.json`: interval persis yang diminta, jumlah deal yang dikembalikan/ditulis, hasil pemeriksaan, build terminal dan batas bukti. File ini ditulis terakhir sebagai tanda commit; abaikan folder tanpa manifest akhir dan file `.part`.

Jika capture gagal setelah folder dibuat, `INVALID.json` mencatat alasan, interval request, dan returned count yang diketahui (`null` bila tidak diketahui), tanpa menyatakan data lengkap. Saat identitas tidak lagi cocok, tidak ada penulisan lanjutan; folder dapat tetap tanpa marker akhir. Marker INVALID atau `.part` tidak boleh diperlakukan sebagai capture berhasil.

File menggunakan UTF-8 dan CSV dengan quote/escape string; komentar dapat memuat newline sehingga jumlah baris teks bukan jumlah deal. Parsing harus memakai parser CSV. Writer mengonversi teks menjadi byte UTF-8, mengecualikan NUL terminal, dan mewajibkan jumlah byte `FileWriteArray` sama persis dengan yang diminta sebelum flush/close/commit. Short write menghasilkan kegagalan. Folder/file lama tidak ditimpa. Publikasi beberapa file bukan transaksi filesystem/broker atomik; manifest akhir hanya menandai bahwa langkah penulisan dan pemeriksaan selesai.

Identity diperiksa sebelum/selama pembacaan, sebelum penulisan dan commit. Balance, equity, profit, credit, margin, free margin, leverage, serta jumlah posisi/order harus tetap sama pada pemeriksaan yang mengapit pembacaan/penulisan. Pergerakan floating dapat membuat snapshot ditolak. Pemeriksaan tersebut bukan bukti bahwa broker menyediakan snapshot atomik atau bahwa tidak ada perubahan singkat yang luput di antara pemeriksaan.

`VALID_CAPTURE` berarti pemeriksaan pengambilan data lolos, **bukan** riwayat lengkap independen, validasi modal/biaya, kelayakan strategi, atau baseline GO. Waktu tetap dilabeli server dengan offset belum diverifikasi. Daily equity drawdown tidak dihitung dari history deal.

History kosong tetap dicatat `INVALID`, tanpa dianggap bukti tidak ada transaksi. Jenis accounting selain buy/sell/balance, reversal/close-by, nilai enum tak didukung, atau credit nonzero membuat hasil `INVALID`; field yang berhasil dibaca tetap disimpan agar bisa ditinjau. Error getter/identity/write menghentikan capture dan dapat hanya menghasilkan pesan INVALID atau folder yang belum commit. Riwayat di atas 100.000 deal ditolak sebagai INVALID, bukan dipotong diam-diam. Tidak ada loop retry panjang.

Referensi primer: [HistorySelect dan interval waktu server](https://www.mql5.com/en/docs/trading/historyselect), [field deal dan makna fee/swap](https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties), [FileMove dan aturan overwrite](https://www.mql5.com/en/docs/files/filemove).

Tujuh tes kontrak sumber mencakup opt-in/identitas, full-history, larangan capability transaksi/network, byte I/O, urutan commit, dan parsing template manifest aktual. Jalankan `python -m unittest discover -s data_collection/tests -p test_account_evidence_source.py -v`. Tes ini bukan compiler MQL atau simulasi broker, dan tidak membuktikan bahwa script berhasil dijalankan.

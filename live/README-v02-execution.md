# Pengelola posisi DEMO v0.2

[execution_v02.py](execution_v02.py) adalah pengelola posisi; [run_demo_v02.py](run_demo_v02.py) menyediakan CLI/supervisor terpisah yang default-nya offline. Wrapper memakai fungsi pembacaan dan kalkulasi observer tanpa mengubah kontrak observer baca-saja. Integrasi ini belum diaktifkan atau diverifikasi pada VPS. Mengimpor modul tidak mengirim order. Akun REAL ditolak; tidak tersedia jalur untuk mengaktifkannya.

Status implementasi dan hasil tes bukan baseline **GO**. Persyaratan promosi pada [SPEC yang dibekukan](../research_v02/SPEC.md#frozen-research-protocol-and-promotion-gates) tetap berlaku. Modul tidak menilai bukti tersebut atau memberikan persetujuannya sendiri.

## Antarmuka yang tersedia

```python
Config(
    expected_login: int,
    history_origin_utc: float,
    baseline_approved: bool = False,
    manual_approved: bool = False,
    costs_verified: bool = False,
    slippage: float = 0.03,
    commission_per_lot_side: float = 0.0,
)
Store(private_directory, config)
Manager(broker, config, store, clock=time.time)
Decision.from_observer(observation)
manager.step(decision=None)
store.close()
```

Ini merupakan ringkasan signature, bukan perintah aktivasi. Identitas akun, asal waktu riwayat, dan direktori state harus diberikan secara privat oleh integrator. `history_origin_utc` adalah epoch UTC yang sudah diverifikasi mendahului pendanaan awal akun; jangan menebaknya dari waktu proses mulai.

`broker` merupakan objek API kompatibel MT5 yang disediakan pemanggil. Untuk pengujian, objek ini adalah broker tiruan. Modul membutuhkan pembacaan account/terminal/symbol/tick, posisi dan order, riwayat deal, kalkulator profit/margin, serta `order_check` dan `order_send`. Tidak ada koneksi terminal yang dibuat oleh constructor. Integrator bertanggung jawab atas lifecycle koneksi dan menutup `Store` dalam `finally`.

`Decision.from_observer(...)` menerima hasil `calculate_row` dari [observer](observe_v02.py): `row` berupa Series dengan index UTC pembukaan M5, `sources` dengan `latestAvailableAtUtc` untuk M5/M15/H1/H4, serta `specSha256`. Waktu keputusan adalah pembukaan M5 + 300 detik. Bar harus sudah tutup dan bersebelahan dengan bar eksekusi; keputusan paling tua 30 detik. Konteks HTF harus sudah tersedia dan umurnya kurang dari satu periode masing-masing. Quote broker harus paling tua 10 detik.

`step(decision)` melakukan satu pemeriksaan terbatas, rekonsiliasi, pengelolaan proteksi dan, hanya jika seluruh gate terpenuhi, percobaan entry/add. `step(None)` tetap dapat membaca akun, merekonsiliasi exit, dan menangani proteksi/daily kill, tetapi tidak menghasilkan entry. Gate tertutup tidak membuat `step` menjadi pemeriksaan offline: pembacaan broker dan jurnal privat tetap berlangsung ketika API sungguhan diberikan.

Nilai kembalian berupa alasan status terbatas. Penolakan atau kondisi tidak pasti dapat menghasilkan `ExecutionStop`; pemanggil harus menghentikan percobaan terkait dan menyimpan alasan untuk tinjauan. Jangan menangkap exception lalu mengulang `enter` atau `send` secara otomatis. Helper tersebut bukan jalur alternatif untuk melewati `step`.

## Gate default dan identitas broker

Ketiga flag persetujuan default `False`. Semuanya harus `True` sebelum **mutasi apa pun**, termasuk penutupan darurat. Flag adalah pernyataan eksplisit pemanggil, bukan bukti kriptografis bahwa baseline dan biaya benar-benar sudah ditinjau. Wrapper hanya memetakan pengaturan privat yang diberikan operator; tidak membuat, menyimpan, atau meluluskan flag persetujuan sendiri.

Setiap tindakan memeriksa ulang akun DEMO yang diharapkan, mata uang USD, model hedging, koneksi, serta izin algoritmik akun/terminal. Entry hanya mendukung simbol tepat `XAUUSD`, chart Bid dan execution Request/Instant dengan FOK. Metadata lot/tick/stop dan kemampuan SL/TP harus tersedia. Posisi atau pending order manual menghalangi entry; modul tidak mengadopsi transaksi manual. Penutupan posisi milik modul dapat tetap dilakukan tanpa mengubah pending order manual.

Pembacaan posisi/order yang menghasilkan `None` berarti tidak diketahui, bukan kosong. Identitas ticket/position, magic, arah, volume dan harga masuk harus cocok dengan jurnal. Perubahan volume atau identitas memerlukan tinjauan; modul tidak menebak kepemilikan dari simbol saja.

## Ekuitas berjalan dan asal modal

Sizing memakai **ekuitas akun saat itu**, lalu menghitung kerugian dan margin melalui kalkulator broker. Lot dibulatkan turun; jika minimum lot tidak muat, hasilnya penolakan. Tidak ada penambahan lot ke minimum, setoran otomatis, atau reset ekuitas menjadi $50.

Sebagai contoh, bila saldo/ekuitas berubah dari $50 menjadi $44,28 akibat transaksi manual, anggaran NORMAL 2% menjadi **$0,8856**, sebelum pembulatan lot. Bila riwayat yang dapat direkonsiliasi membuktikan anchor awal hari $50 dan tidak ada posisi terbawa pada tengah malam, penurunan ke $44,28 adalah 11,44% terhadap anchor itu: EXTREME dinonaktifkan. Contoh ini bukan laporan saldo aktual atau izin entry.

Modul meminta seluruh deal sejak asal riwayat yang diberikan, bukan hanya riwayat sejak proses dimulai. Ledger harus menunjukkan satu pendanaan awal positif maksimal $50, tanpa top-up/adjustment tambahan yang tidak didukung. Net profit, komisi, swap dan fee seluruh transaksi—termasuk manual—direkonsiliasi terhadap saldo broker; volume masuk/keluar harus cocok dengan posisi terbuka. Riwayat terpotong, kredit/jenis deal tak didukung, atau ketidaksesuaian saldo/volume membekukan proses.

Anchor harian berasal dari ledger sebelum tengah malam UTC; pendanaan pada hari pertama menjadi anchor pendanaan hari itu. Jika suatu posisi sudah terbuka saat tengah malam, ledger deal tidak membuktikan floating equity pada saat tersebut. Anchor disimpan sebagai tidak diketahui dan entry dibekukan, tanpa menggantinya dengan ekuitas saat peluncuran. Dukungan bukti equity tengah malam tambahan belum diimplementasikan. Ini juga bukan rekonstruksi maximum drawdown intraday dari tick yang tidak tersedia.

## Aturan dan pengelolaan posisi

Aturan suara dan mode diimpor dari [engines.py](../research_v02/vortex_v02/engines.py); pembulatan, pembagian lot dan gate risiko dari [risk.py](../research_v02/vortex_v02/risk.py). Modul tidak mengubah sumber penelitian atau memilih threshold berdasarkan hasil. Sumber aturan dan konfigurasi dicatat dalam fingerprint state.

- Risiko baseline NORMAL/AGGRESSIVE/EXTREME adalah 2%/3,5%/5% ekuitas berjalan. Profil stress 7,5%/10% tidak dapat dipilih sebagai risiko base di sini. Stop awal memakai invalidasi struktur dan minimum jarak 1,4×ATR M15 dari estimasi entry yang merugikan, dibulatkan keluar; lebih dari 2,2×ATR ditolak. Spread aktual, margin dan risiko diperiksa lagi sebelum pengiriman.
- Bila lot dapat dibagi tepat 25%/25%/50% pada minimum dan step broker, satu leg strategi direpresentasikan sebagai tiga ticket hedging: SL+TP1 pada 1,5R; SL+TP2 pada 2,5R; dan runner 50% dengan SL serta **TP=0 yang disengaja**. Runner tidak mempunyai fixed target pada aturan yang dibekukan. Harga target disesuaikan terhadap fill broker yang benar-benar terkonfirmasi.
- Jika pembagian tersebut tidak executable, volume tetap dipakai sebagai satu posisi, termasuk 0,01 lot. Posisi memiliki SL dan full TP2 pada 2,5R; tanpa partial semu. Breakeven mencadangkan biaya/slippage/swap debit setelah bar tertutup mencapai +1R. Trailing satu posisi mulai pada +1,5R; runner partial mulai setelah TP2 terbukti ditutup oleh TP broker. SL tidak dilonggarkan dan status trailing dipertahankan dalam state.
- Maksimal satu base campaign dan dua add. Add hanya searah, setelah ambang kemenangan/consensus terpenuhi, quote saat itu masih untung, dan proteksi breakeven terdahulu terkonfirmasi. Risiko nominal add adalah 1,5% lalu 1%, dengan pengurangan risiko setelah dua campaign rugi. Batas kumulatif nominal campaign dan net planned open risk tetap 7,5%; profit terkunci tidak menutupi risiko ticket lain untuk membesarkan add.
- Dua campaign rugi mengurangi risiko baru setengah dan memblokir EXTREME. Tiga campaign rugi membuat FROZEN persisten, termasuk setelah pergantian hari/restart. DD harian 10% memblokir EXTREME; 15% memicu penutupan ticket milik modul jika broker dan gate tindakan memungkinkan. Floating akun/manual ikut memengaruhi equity harian.

SL yang hilang atau melebar pada ticket yang kepemilikannya masih pasti memblokir entry dan memicu penutupan darurat setelah gate DEMO/persetujuan lolos. Kehilangan SL saat fill atau saat pembaruan juga ditangani. Perubahan proteksi lain yang tidak sesuai dapat memerlukan tinjauan. Ini bukan jaminan bahwa broker menerima penutupan atau bahwa gap akan berhenti pada harga SL.

## State, restart dan hasil ambigu

`Store` mewajibkan direktori di luar checkout. File `execution-v02.jsonl` berisi state privat lengkap dalam rantai hash dan di-fsync; lock OS membatasi satu writer pada direktori tersebut. Marker mendeteksi jurnal yang hilang setelah inisialisasi. Record terpotong/rusak atau fingerprint berbeda menghentikan startup. Ticket, request dan detail ledger di dalamnya tidak boleh dikirim ke dashboard, log publik, atau Git.

Keputusan ditandai sudah dipakai sebelum aksi. Intent order dipersistenkan sebelum `order_send`. Akun, exposure, quote dan anggaran diperiksa kembali sebelum pengiriman. Respons timeout/None/partial/non-DONE tidak dianggap sebagai bukti bahwa tidak terjadi fill: intent tetap tertahan, tanpa retry otomatis atau top-up partial fill.

Rekonsiliasi hanya memulihkan outcome bila state broker cocok persis dengan intent dan kepemilikan dapat dibuktikan. Penutupan memerlukan riwayat volume dan biaya yang lengkap. Submission tiga tranche tidak atomik; sebagian dapat diterima sebelum yang lain gagal. Campaign yang pembukaannya tidak lengkap tetap tertahan untuk review meskipun ticket yang sudah diterima dapat direkonsiliasi dan dilindungi. Modul tidak melanjutkan sisa tranche secara otomatis setelah restart.

Rantai hash mendeteksi kerusakan pada arsip yang dipertahankan, bukan penggantian seluruh direktori atau penghapusan suffix jurnal yang valid oleh pihak yang menguasai disk. Backup/checkpoint independen tetap diperlukan untuk bukti audit. Tidak ada tool reset state otomatis.

## CLI terpisah dan loop pengelolaan

Default dan `--check` hanya memvalidasi import/konfigurasi privat. Keduanya tidak membuat direktori/state, mengimpor MetaTrader5, menginisialisasi terminal, atau mengakses broker:

```sh
python live/run_demo_v02.py --check
```

CLI memerlukan pengaturan privat observer yang sudah ada: `VORTEX_EXPECTED_LOGIN`, `VORTEX_STATE_DIR`, dan `VORTEX_SESSION_UTC_OFFSET_MINUTES=0`. `VORTEX_TERMINAL_PATH` opsional. Sumber kalender/news coverage/macro menggunakan variabel yang dijelaskan dalam [panduan observer](README-v02-observer.md). Pengaturan khusus eksekusi:

| Pengaturan | Makna |
| --- | --- |
| `VORTEX_ACCOUNT_HISTORY_ORIGIN_UTC` | ISO datetime dengan zona waktu eksplisit, terverifikasi sebelum pendanaan awal |
| `VORTEX_VERIFIED_SLIPPAGE_USD` | Cadangan slippage per ounce per sisi, minimal 0,03 |
| `VORTEX_VERIFIED_COMMISSION_PER_LOT_SIDE_USD` | Cadangan komisi USD per lot per sisi; wajib eksplisit, nol tidak diasumsikan sebagai biaya broker terverifikasi |
| `VORTEX_BASELINE_STATUS` | Harus tepat `passed_reviewed` untuk mode aktif |
| `VORTEX_DEMO_EXECUTION_APPROVAL` | Harus tepat `demo_execution_reviewed` untuk mode aktif |
| `VORTEX_EXECUTION_COST_STATUS` | Harus tepat `verified_reviewed` untuk mode aktif |

Hanya `--run-demo` meminta mode aktif; pilihan ini tidak cukup tanpa seluruh gate di atas dan Windows. Jangan mengatur flag agar bisa melewati baseline yang belum lulus. Gate diperiksa sebelum pembuatan state, pemuatan adapter dan inisialisasi terminal. Tidak ada API login atau password yang diterima.

Supervisor memegang lock observer dan lock manager dalam **satu direktori runtime privat yang dikonfigurasi** sebelum terminal diinisialisasi. Collector yang sudah memakai direktori itu akan membuat runner ditolak, bukan berjalan bersamaan. Lock bukan pengunci global akun: menjalankan proses lain dengan direktori berbeda masih mungkin. Packaging/operator harus menetapkan satu direktori dan satu job manager; pencegahan job lintas direktori belum tersedia.

Setiap putaran memanggil `Manager.step(None)` terlebih dahulu untuk kesehatan, rekonsiliasi dan batas risiko. Hasil kalkulasi yang sudah selesai baru diteruskan sebagai `Decision`; yang sudah terlambat dibuang tanpa mengulang entry. Satu worker hanya menjalankan `calculate_row` pada frame yang sudah dibaca. Semua pemanggilan MT5, pembacaan frame dan tindakan manager tetap berada pada thread utama. Karena itu, worker kalkulasi tidak mengambil alih atau berbagi akses terminal secara bersamaan.

Loop menunggu dua detik setelah setiap putaran. Itu target polling, bukan jaminan interval/latensi: pembacaan terminal atau ledger dapat memperlambatnya. Frame dicoba maksimal sekali per bar M5. Ketika kalkulasi belum selesai, hasil sudah tua, atau input strategi belum siap, kesehatan posisi tetap diperiksa pada putaran berikutnya. Kalkulasi data lengkap pada VPS 2 GB belum diukur; batas kedaluwarsa tidak diperpanjang untuk mengakomodasi keterlambatan.

Gangguan pembacaan yang tercantum eksplisit dapat menunggu pemulihan bila tidak ada intent/campaign pembukaan yang belum selesai. Penolakan sinyal/risk yang normal dicatat sebagai skip. Kesalahan mutasi, hasil ambigu, ketidakcocokan integritas/identitas, atau campaign yang tidak lengkap menghentikan runner untuk review; tidak ada blanket retry sekitar order. Pada startup berikutnya, rekonsiliasi manager tetap wajib dan tidak melanjutkan tranche yang hilang otomatis.

`--once` membatasi satu putaran kesehatan/pengelolaan. Pilihan ini tidak menunggu kalkulasi worker, sehingga tidak menjanjikan keputusan baru atau entry. File `STOP` di direktori runtime mengakhiri loop sebelum tindakan putaran berikutnya. STOP, interupsi dan shutdown **tidak melakukan flatten implisit**: broker SL/TP serta posisi yang ada tetap mempunyai lifecycle sendiri. Setelah STOP, trailing Python tidak lagi diperbarui. Worker yang sudah berjalan hanya menyelesaikan kalkulasi murni; ia tidak dapat mengirim order, tetapi penyelesaiannya dapat menunda akhir proses Python.

`execution-status.json` dan `execution-supervisor-journal.jsonl` merupakan file privat terpisah. Status berisi role supervisor, waktu, alasan/state, jumlah posisi yang dikenal, flag intent/campaign, daily kill dan freeze; tanpa ID akun/ticket atau quote/angka akun. `executionArmed` hanya menyatakan konfigurasi persetujuan proses, bukan kelayakan entry saat itu atau bukti keberhasilan order. `entryEligible` tetap null: polling status tidak mengklaim keputusan berikutnya telah lolos data, strategi dan risiko. Journal menyimpan sumber/skor keputusan dan disposition manager dengan rantai hash/fsync. Outcome order yang definitif tetap dirujuk ke jurnal manager dan riwayat broker, bukan disimpulkan dari keputusan yang diserahkan.

Wrapper tidak menulis `status.json` milik observer, tidak memakai schema dashboard/cloud, dan tidak mengklaim publisher atau notifikasi eksekusi tersedia. Saat berhenti, status menunjukkan tidak aktif; fatal reason dipertahankan sebagai `halted`. Status/jurnal privat ini belum menjadi API publik dan jangan dikirim langsung ke frontend.

## Yang belum tersedia dan verifikasi

Belum ada startup/watchdog manager, pencegahan proses lintas direktori, publisher status manager, integrasi notifikasi, ataupun bukti eksekusi Windows/MT5 aktual dari wrapper ini. [Observer yang ada](README-v02-observer.md) tetap baca-saja. Tidak ada jaminan cadence, latensi, restart VPS, ataupun proteksi saat broker tidak bisa dijangkau. Baseline, asal/kelengkapan riwayat, biaya, dan kemampuan pemulihan operasional tetap perlu diverifikasi terpisah.

Jalankan dari root repository:

```sh
python -m unittest discover -s live/tests -p test_execution_v02.py -v
python -m unittest discover -s live/tests -p test_run_demo_v02.py -v
python -m unittest discover -s live/tests -v
```

Pada penyelesaian wrapper, 35 tes manager dan 16 tes supervisor lulus. Tes khusus menggunakan broker tiruan sepenuhnya: tidak ada terminal, akun, network, atau order broker sungguhan. Cakupan manager meliputi penolakan REAL/gate default, saldo berjalan dan anchor manual loss, minimum lot, race saat preflight, SL/TP/trailing/add, daily kill, partial/ambiguous outcomes, outage/restart, serta integritas state. Tes supervisor menjalankan batas CLI offline/gate/lock, broker tiruan dengan worker nyata, urutan rekonsiliasi, hasil terlambat, polling saat worker menunggu, STOP tanpa flatten, dan pemisahan status privat.

Hasil tersebut membuktikan perilaku pada skenario sintetis yang diuji, bukan profitabilitas, kelengkapan baseline, atau status VPS. Persetujuan baseline dan integrasi operasional tetap terpisah. Referensi primer API: [order_send dan lifecycle request](https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py), [riwayat deal](https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py).

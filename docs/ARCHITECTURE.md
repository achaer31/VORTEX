# Dashboard dan mesin riset

## Versi saat ini

```text
MT5 di VPS Windows
    ↓ ekspor manual harga historis
CSV lokal → audit + indikator + simulasi Python
    ↓ hasil riset + cuplikan terpilih
GitHub VORTEX → dashboard statis → Vercel
```

Dashboard menampilkan hasil riset historis yang dibundel saat penerbitan. Browser tidak tersambung ke MT5, tidak membaca saldo akun pribadi, dan tidak mengirim order. Enam kartu adalah skor aturan dalam satu strategi gabungan, bukan enam trader dengan laba sendiri. Visual vortex merupakan ilustrasi, bukan aliran order atau ukuran kondisi pasar.

Pemisahan ini memungkinkan halaman ringan di Vercel dan pekerjaan MT5 tetap berada di Windows VPS. Pembaruan kode tercatat di GitHub. Dataset lengkap, konfigurasi remote desktop, dan kredensial tidak dipublikasikan.

## Jika nantinya ditambahkan pemantauan langsung

Tahap berikut membutuhkan pengirim data dari VPS, endpoint penerima dengan autentikasi, penyimpanan snapshot, dan login pembaca. Web perlu menampilkan waktu update terakhir, data terlambat, serta koneksi putus secara eksplisit. Password MT5 tidak boleh dikirim ke browser atau disimpan di Git.

Data akun sebaiknya hanya dibaca setelah akses pengguna tervalidasi di server. Pengirim data cukup mengirim field yang diperlukan, menggunakan token terpisah dari password trading, dan tidak mengaktifkan perdagangan otomatis. Modul order, bila dikembangkan kemudian, membutuhkan spesifikasi serta pengujian tersendiri. Infrastruktur ini belum menjadi bagian versi saat ini.

## Hosting

Dashboard statis ini dapat dihosting di Vercel sebagai proyek **Other**, dengan Root Directory `dashboard`; tidak memerlukan build atau variabel rahasia. Mulai dari Preview dan pertahankan proteksi deployment yang tersedia. Snapshot dalam repo publik tetap dapat dibaca dari GitHub, sehingga proteksi Preview tidak menjadikan isi repo rahasia.

Referensi resmi: [Git deployments](https://vercel.com/docs/deployments/git), [build configuration](https://vercel.com/docs/builds/configure-a-build), [deployment protection](https://vercel.com/docs/deployment-protection).

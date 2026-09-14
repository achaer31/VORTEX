# Hipotesis lanjutan — belum dijalankan

v0.2 belum menghasilkan transaksi dan belum dapat dievaluasi. Karena itu tidak
ada optimasi parameter setelah hasil supaya grafik tampak profit.

1. **Kelengkapan input.** Uji apakah calendar coverage serta DXY/yield intraday
   yang benar-benar tersedia saat keputusan dapat dipenuhi secara konsisten.
   Bekukan provider, lag, freshness dan aturan revisi sebelum data baru dinilai.
   Jalankan v0.2 yang sama dulu; ini melengkapi data, bukan mengubah strategi.
2. **Kelayakan kontrak pada$50.** Audit metadata broker untuk apakah volume yang
   lebih kecil memang tersedia. Jangan berasumsi tersedia, jangan ganti ukuran
   kontrak dalam simulator tanpa simbol/akun yang mendukung, jangan naikkan
   starting capital. Jika minimum risiko tetap melampaui budget, sistem WAIT.
3. **Hipotesis entry baru bila diperlukan.** Definisikan strategi struktur emas
   yang berbeda beserta stop invalidation yang masuk akal secara independen;
   jangan memilih stop lebih sempit hanya untuk memasukkan0.01lot. Freeze versi
   v0.3 dan uji pada data setelah freeze yang belum dipakai memilih aturan.

Tetap modal$50, top-up0, no martingale/averaging loser, tanpa kenaikan risiko
karena target/tenggat. Ini daftar hipotesis, bukan rekomendasi akun, janji
profit, atau perubahan konfigurasi v0.2 yang sedang diuji.

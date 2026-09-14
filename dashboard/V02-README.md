# Konsol v0.2

`v02.html`, `v02.css`, dan `v02.js` adalah UI baca-saja. Halaman tidak membuka, mengubah, menutup, atau mengaktifkan order. REAL terkunci. Card challenge menyatakan target pengguna dan NO-GO, bukan proyeksi atau izin trading.

## Data BACKTEST

`assets/v02.json` berasal dari `research_v02/run_research.py` → `dashboard.json`, dengan `schemaVersion:2`, `model:VORTEX-XAU-EXTREME-v0.2`, `environment:BACKTEST`, `liveFeed:false`. Model yang berbeda ditolak. Browser memilih skenario yang benar-benar tersedia lewat periode, profil alokasi, risiko/cap dan biaya. Kombinasi yang tidak ada tidak disimulasikan di browser.

| Field sumber | Tampilan |
| --- | --- |
| `scenarios` | Equity, realized P/L, campaign, drawdown, register dan pilihan skenario |
| `signal` | Snapshot skor terakhir, alasan tiap engine, consensus, mode, session dan ATR |
| `market` (opsional) | Bid bar historis, spread points dan waktu sumber; bukan quote live |
| `diagnostics`, `promotion` | Kekurangan news/macro serta alasan NO-GO; journal ditandai diagnostik laporan |

Filter skenario tidak mengubah snapshot skor pasar terakhir. Nilai yang tidak tersedia ditampilkan `—`; data historis tidak dipakai mengisi PAPER atau DEMO. Equity simulasi yang datar karena tidak ada trade bukan bukti strategi menguntungkan.

## Koneksi PAPER / DEMO opsional

Default kedua tab adalah **DISCONNECTED**, tanpa saldo/quote buatan. Panel koneksi menerima URL HTTPS tanpa userinfo, query atau fragment, serta reader token 64 karakter hex huruf kecil. Token dikirim lewat `Authorization: Bearer …`, tidak lewat URL; nilai field password dibersihkan setelah koneksi. Token hanya ada di memori halaman, tidak masuk localStorage, sessionStorage, cookie atau log. Putuskan koneksi atau tutup halaman untuk menghapusnya.

GET berlangsung setiap 15 detik dengan timeout 8 detik, tanpa credentials cookie, tanpa referrer dan tanpa mengikuti redirect. Endpoint harus mengizinkan CORS untuk origin dashboard. Bentuk response:

```text
schemaVersion: 1
mode: demo
state: fresh | stale | empty
receivedAt, ageSeconds
snapshot: producer snapshot privat yang tersanitasi
```

Snapshot v0.2 membutuhkan `snapshot.v02.model = VORTEX-XAU-EXTREME-v0.2` dan lingkungan yang cocok dengan tab. Field `v02.metrics/context/engines/protection/position/journal` mengikuti kontrak [cloud](../cloud/README.md). Snapshot legacy boleh menampilkan quote dan angka akun DEMO yang segar, dengan label **LEGACY OBSERVER**; ia tidak menyediakan skor v0.2 atau menjadi session PAPER v0.2.

Tabel posisi menampilkan posisi XAUUSD akun yang dilaporkan producer, tanpa mengklaim semuanya milik bot. Pada `runnerMode:observe`, flag kill ditampilkan **ENTRY TERKUNCI / OBSERVER**; ini tidak menyatakan bahwa penutupan posisi otomatis atau perlindungan broker sedang aktif.

Umur snapshot >90 detik, quote >10 detik, akun/koneksi belum terverifikasi, schema tidak valid, atau request gagal membuat tampilan non-live. Angka lama tidak dipertahankan sebagai angka live. Umur dihitung ulang di browser tiap detik; jam client yang salah dapat menyebabkan penolakan. Status fresh hanya berarti sampel masih segar, bukan izin eksekusi atau bukti profit.

Tidak ada feed endpoint atau token yang dibundel di repository. Keberadaan UI koneksi tidak berarti publisher, broker, PAPER atau DEMO sedang aktif.

## Pemeriksaan

```sh
node --check dashboard/v02.js
node --test dashboard/tools/test_v02.mjs
```

Tes menjalankan **kode produksi utuh** dalam VM Node dengan DOM inert dan input sintetis. Cakupan: default disconnected, legacy/environment isolation, batas freshness, metadata/quote salah, validasi endpoint/token, header privat, request gagal, race koneksi lama, literal external text dan penghapusan token. Tidak ada browser nyata, network, akun atau order dalam tes. Review layout desktop/mobile dan integrasi endpoint sungguhan merupakan pemeriksaan terpisah.

\*# Optimasi Rute Semarang-Jakarta melalui Semua Kota/Kabupaten di Jawa Tengah

Program Python untuk mencari urutan kunjungan terpendek dari Kota Semarang ke Jakarta, dengan syarat seluruh 35 ibu kota kabupaten/kota di Jawa Tengah dikunjungi lebih dulu. Masalah ini adalah Traveling Salesman Problem (TSP) berarah dengan titik awal dan titik akhir yang sudah ditentukan. Dibuat sebagai tugas Teori Graf / Matematika Diskrit.

Jarak antarkota berasal dari jaringan jalan nyata (OSRM), bukan garis lurus. Matriksnya asimetris, sehingga grafnya berarah.

## Struktur repositori

```
.
├── data/
│   ├── matriks_jarak.csv     matriks jarak OSRM, km (baris = asal, kolom = tujuan)
│   ├── matriks_jarak.meta.json   catatan sumber matriks: server, profil, waktu pengambilan
│   └── koordinat.csv         titik pusat kota (sekitar alun-alun)
├── rute/
│   ├── data.py               pembacaan dan validasi data
│   ├── algoritma.py          Dijkstra, Nearest Neighbor, 2-opt, solusi eksak (ILP)
│   ├── osrm.py               pengambilan matriks jarak dari OSRM
│   └── peta.py               gambar statis dan peta interaktif
├── main.py                   program utama (Soal D)
├── simulasi.py               simulasi dan eksperimen (Soal F)
├── hasil/                    keluaran program
├── requirements.txt
└── README.md
```

## Persyaratan

1. Pastikan Python 3.11 atau yang lebih baru sudah terpasang.

2. Lakukan clone atau download repositori ini.

3. Saat pertama kali setelah melakukan clone atau download, masih belum ada folder `.venv`, maka jalankan perintah di bawah ini. Ini hanya dijalankan satu kali saja di awal.

```bash
# Untuk macOS dan Linux
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Untuk Windows (PowerShell)
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

4. Sebelum program dijalankan, pastikan `.venv ` sudah aktif, yang ditandai dengan tulisan `(.venv)` di bagian paling kiri terminal.

```bash
# Untuk macOS dan Linux
source .venv/bin/activate

# Untuk Windows (PowerShell)
.venv\Scripts\activate
```

## Cara menjalankan

Program utama membaca matriks, menentukan rute dengan tiga metode, menghitung total kilometer, dan menulis peta:

```bash
python main.py
```

Simulasi (rute acak, multi-start, dan skala ukuran masalah). Seed yang sama menghasilkan angka yang sama:

```bash
python simulasi.py --seed 42
```

Opsi lain tersedia lewat `python main.py --help` dan `python simulasi.py --help`.

### Memperbarui matriks jarak dari OSRM

Matriks di `data/matriks_jarak.csv` sudah berasal dari OSRM. Untuk mengambilnya lagi, misalnya karena data peta OSRM berubah, tambahkan `--perbarui-matriks`:

```bash
python main.py --perbarui-matriks
```

Program mengirim koordinat di `data/koordinat.csv` ke Table API OSRM, membandingkan hasilnya dengan matriks lama, menimpa `data/matriks_jarak.csv`, lalu melanjutkan perhitungan dengan matriks baru. Tanggal, server, dan profil pengambilan dicatat di `data/matriks_jarak.meta.json`. Jika pengambilan gagal, matriks lama tidak diubah.

Server bawaannya adalah server demo publik OSRM (butuh internet). Untuk memakai server sendiri atau profil lain:

```bash
python main.py --perbarui-matriks --osrm-server http://localhost:5000 --osrm-profil driving
```

Satu permintaan memuat semua titik, jadi jumlah kota dibatasi `--max-table-size` di server (bawaan OSRM 100).

## Keluaran di folder `hasil/`

| Berkas                                              | Isi                                                                   |
| --------------------------------------------------- | --------------------------------------------------------------------- |
| `ringkasan.csv`                                     | jarak, penghematan, selisih dari optimal, dan waktu tiap metode       |
| `rute_nn.csv`, `rute_nn_2opt.csv`, `rute_eksak.csv` | urutan kunjungan, jarak per ruas, jarak kumulatif, kota yang dilewati |
| `rute_*.png`                                        | gambar rute (tanpa peta dasar, tidak butuh internet)                  |
| `peta_rute.html`                                    | peta interaktif dengan pilihan metode dan simulasi perjalanan         |
| `simulasi_*.png`, `simulasi_*.csv`                  | hasil percobaan di `simulasi.py`                                      |

### Cara membuka peta rute

`peta_rute.html` memuat Leaflet dan ubin peta OpenStreetMap dari internet, jadi perlu koneksi. Sebaiknya buka lewat server lokal, bukan dengan klik dua kali pada berkasnya. Jika dibuka langsung dari folder (alamat `file://`), peramban tidak mengirim asal halaman, dan server OpenStreetMap dapat menolak permintaan ubin sehingga petanya kosong.

Dari folder utama repositori, jalankan:

```bash
python -m http.server 8000 --directory hasil
```

Lalu buka <http://localhost:8000/peta_rute.html> di browser. Jika port 8000 sudah dipakai, ganti angkanya, misalnya `8080`, dan sesuaikan alamatnya. Untuk menghentikan server, tekan `Ctrl + C` pada terminal.

Perintah ini memakai modul bawaan Python, jadi tidak butuh pustaka tambahan.

## Cara kerja singkat

1. **Dijkstra** dijalankan dari setiap kota pada matriks jarak. Jarak OSRM diukur di rute tercepat, jadi A → C → B kadang lebih pendek daripada A → B langsung. Hasilnya dipakai oleh semua metode di bawah.
2. **Nearest Neighbor** dari Semarang selalu memilih kota terdekat yang belum dikunjungi, lalu berakhir di Jakarta.
3. **2-opt** memperbaiki rute Nearest Neighbor dengan membalik potongan rute selama total jarak turun. Karena matriks asimetris, biaya potongan yang dibalik dihitung ulang.
4. **Solusi eksak** memakai integer linear programming (`scipy.optimize.milp`, solver HiGHS) dengan larangan sub-siklus yang ditambahkan bertahap. Hasilnya dijamin optimal untuk matriks yang diberikan dan dipakai sebagai pembanding.

## Catatan data

- `data/matriks_jarak.csv` diambil dari OSRM. Untuk memakai matriks lain, ganti berkas ini atau berikan jalurnya lewat `--matriks`. Nama baris dan kolom harus sama, dan harus memuat `Semarang` serta `Jakarta`.
- `data/koordinat.csv` berisi titik pusat tiap kota di sekitar alun-alun. Koordinat ini dikirim ke OSRM saat memakai `--perbarui-matriks`, sehingga hasilnya ikut berubah jika koordinat diubah. Selama matriks dipakai apa adanya, koordinat hanya dipakai untuk menggambar peta.
- Tanpa opsi tambahan, ruas pada peta digambar sebagai garis lurus antarkota. Opsi `python main.py --geometri-osrm` mengambil bentuk jalan dari server OSRM publik (butuh internet, sekitar satu detik per ruas, hasilnya disimpan di `data/cache_osrm/`). Ruas yang gagal diambil tetap digambar sebagai garis lurus.

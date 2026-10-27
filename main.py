"""Optimasi rute Semarang - Jakarta melalui 35 ibu kota kabupaten/kota Jawa Tengah.

Contoh:
    python main.py
    python main.py --geometri-osrm
    python main.py --perbarui-matriks
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

import numpy as np

from rute.algoritma import (
    biaya_rute,
    dua_opt,
    jarak_terpendek,
    lintasan_lengkap,
    nearest_neighbor,
    periksa_rute,
    solusi_eksak,
    ukur_waktu,
)
from rute.data import (
    KOTA_AKHIR,
    KOTA_AWAL,
    baca_koordinat,
    muat_koordinat,
    muat_matriks,
    simpan_matriks,
)
from rute.osrm import PROFIL_BAWAAN, SERVER_PUBLIK, ambil_matriks_osrm
from rute.peta import ambil_geometri_osrm, buat_peta_html, format_angka, gambar_rute, susun_data_rute

WARNA = {"nn": "#e8590c", "nn_2opt": "#1c7ed6", "eksak": "#2f9e44"}
LABEL = {
    "nn": "Nearest Neighbor",
    "nn_2opt": "Nearest Neighbor + 2-opt",
    "eksak": "Optimal global (ILP)",
}


def baca_argumen() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--matriks", default="data/matriks_jarak.csv", help="CSV matriks jarak (km)")
    p.add_argument("--koordinat", default="data/koordinat.csv", help="CSV koordinat kota")
    p.add_argument("--keluaran", default="hasil", help="folder hasil")
    p.add_argument("--ulang", type=int, default=200, help="ulangan pengukuran waktu heuristik")
    p.add_argument("--ulang-eksak", type=int, default=3, help="ulangan pengukuran waktu solusi eksak")
    p.add_argument("--batas-waktu", type=float, default=600.0, help="batas waktu solusi eksak (detik)")
    p.add_argument("--geometri-osrm", action="store_true",
                   help="ambil bentuk jalan dari server OSRM publik (butuh internet)")
    p.add_argument("--perbarui-matriks", action="store_true",
                   help="ambil matriks jarak baru dari OSRM dan timpa berkas --matriks sebelum menghitung")
    p.add_argument("--osrm-server", default=SERVER_PUBLIK, help="alamat server OSRM untuk --perbarui-matriks")
    p.add_argument("--osrm-profil", default=PROFIL_BAWAAN, help="profil kendaraan OSRM")
    return p.parse_args()


def main() -> None:
    args = baca_argumen()
    keluaran = Path(args.keluaran)
    keluaran.mkdir(parents=True, exist_ok=True)

    if args.perbarui_matriks:
        perbarui_matriks(args)

    nama, matriks = muat_matriks(args.matriks)
    koordinat = muat_koordinat(args.koordinat, nama)
    n = len(nama)
    awal, akhir = nama.index(KOTA_AWAL), nama.index(KOTA_AKHIR)
    print(f"Matriks {n} x {n} dimuat. Awal: {KOTA_AWAL}, akhir: {KOTA_AKHIR}.")

    asimetri = np.abs(matriks - matriks.T)
    print(f"Asimetri A->B vs B->A: rata-rata {format_angka(asimetri.mean())} km, "
          f"maksimum {format_angka(asimetri.max())} km.")

    (D, pred), t_dijkstra = ukur_waktu(lambda: jarak_terpendek(matriks), args.ulang)
    membaik = D < matriks - 1e-9
    print(
        f"Dijkstra semua pasangan: {format_angka(t_dijkstra)} ms. "
        f"{int(membaik.sum())} dari {n * (n - 1)} pasangan lebih pendek lewat kota perantara "
        f"(penghematan maksimum {format_angka((matriks - D).max())} km)."
    )

    rute_nn, t_nn = ukur_waktu(lambda: nearest_neighbor(D, awal, akhir), args.ulang)
    (rute_2opt, putaran), t_2opt = ukur_waktu(lambda: dua_opt(D, rute_nn), args.ulang)
    eksak, t_eksak = ukur_waktu(
        lambda: solusi_eksak(D, awal, akhir, args.batas_waktu), args.ulang_eksak
    )
    rute = {"nn": rute_nn, "nn_2opt": rute_2opt, "eksak": eksak.rute}
    waktu = {"nn": t_nn, "nn_2opt": t_nn + t_2opt, "eksak": t_eksak}

    for r in rute.values():
        periksa_rute(r, n, awal, akhir)

    biaya = {k: biaya_rute(D, r) for k, r in rute.items()}
    pembanding = solusi_eksak(matriks, awal, akhir, args.batas_waktu)
    print(
        f"Pembanding: solusi eksak tanpa Dijkstra (hanya ruas langsung) = {format_angka(pembanding.biaya)} km."
    )

    geometri = None
    if args.geometri_osrm:
        pasangan = set()
        for r in rute.values():
            jalan = lintasan_lengkap(pred, r)
            pasangan.update(zip(jalan[:-1], jalan[1:]))
        print(f"Mengambil geometri {len(pasangan)} ruas dari OSRM ...")
        geometri = ambil_geometri_osrm(koordinat, pasangan, Path("data/cache_osrm/geometri.json"))

    data = {
        k: susun_data_rute(k, LABEL[k], WARNA[k], nama, koordinat, matriks, pred, r, geometri)
        for k, r in rute.items()
    }
    for k in rute:
        assert abs(data[k]["total_km"] - biaya[k]) < 1e-6, "Jumlah ruas tidak sama dengan biaya rute."

    tulis_ringkasan(keluaran / "ringkasan.csv", rute, biaya, waktu, data)
    for k in rute:
        tulis_rute_csv(keluaran / f"rute_{k}.csv", data[k])
        gambar_rute(keluaran / f"rute_{k}.png", data[k], KOTA_AWAL, KOTA_AKHIR)
    buat_peta_html(keluaran / "peta_rute.html", [data[k] for k in ("nn", "nn_2opt", "eksak")])

    cetak_ringkasan(rute, biaya, waktu, data, putaran, eksak)
    print(f"\nFile hasil ditulis ke folder '{keluaran}'.")


def perbarui_matriks(args: argparse.Namespace) -> None:
    """Ambil matriks dari OSRM, bandingkan dengan yang lama, lalu simpan beserta catatan sumbernya."""
    nama, koordinat = baca_koordinat(args.koordinat)
    for wajib in (KOTA_AWAL, KOTA_AKHIR):
        if wajib not in nama:
            raise SystemExit(f"{wajib} tidak ada di {args.koordinat}.")

    print(f"Mengambil matriks {len(nama)} x {len(nama)} dari {args.osrm_server} "
          f"(profil {args.osrm_profil}) memakai koordinat di {args.koordinat} ...")
    try:
        baru = ambil_matriks_osrm(koordinat, args.osrm_server, args.osrm_profil)
    except RuntimeError as galat:
        raise SystemExit(f"Matriks tidak diperbarui. {galat}")

    path = Path(args.matriks)
    if path.exists():
        nama_lama, lama = muat_matriks(path)
        if nama_lama == nama:
            selisih = np.abs(baru - lama)
            print(f"Dibanding matriks lama: {int((selisih > 0.005).sum())} sel berubah, "
                  f"selisih rata-rata {format_angka(selisih.mean())} km, "
                  f"maksimum {format_angka(selisih.max())} km.")
        else:
            print("Daftar atau urutan kota berbeda dari matriks lama, perbandingan dilewati.")

    simpan_matriks(path, nama, baru)
    catatan = path.with_suffix(".meta.json")
    catatan.write_text(json.dumps({
        "sumber": "OSRM Table API",
        "server": args.osrm_server,
        "profil": args.osrm_profil,
        "diambil_pada": datetime.now().astimezone().isoformat(timespec="seconds"),
        "berkas_koordinat": str(args.koordinat),
        "jumlah_kota": len(nama),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Matriks baru disimpan ke {path}, catatan sumber ke {catatan}.\n")


def tulis_ringkasan(path: Path, rute, biaya, waktu, data) -> None:
    dasar, optimal = biaya["nn"], biaya["eksak"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metode", "jarak_km", "penghematan_vs_nn_km", "penghematan_vs_nn_persen",
                    "selisih_vs_optimal_persen", "waktu_ms", "kota_perantara"])
        for k in rute:
            perantara = sum(len(s["dilewati"]) for s in data[k]["urutan"])
            w.writerow([LABEL[k], round(biaya[k], 2), round(dasar - biaya[k], 2),
                        round((dasar - biaya[k]) / dasar * 100, 2),
                        round((biaya[k] - optimal) / optimal * 100, 2),
                        round(waktu[k], 3), perantara])


def tulis_rute_csv(path: Path, data: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["no", "kota", "jarak_dari_sebelumnya_km", "kumulatif_km", "kota_dilewati"])
        for s in data["urutan"]:
            w.writerow([s["no"], s["kota"], s["jarak_km"], s["kumulatif_km"], "; ".join(s["dilewati"])])


def cetak_ringkasan(rute, biaya, waktu, data, putaran, eksak) -> None:
    dasar = biaya["nn"]
    print("\nRingkasan")
    print(f"{'Metode':28s}{'Jarak (km)':>14s}{'Hemat vs NN':>14s}{'Waktu (ms)':>13s}")
    for k in rute:
        hemat = (dasar - biaya[k]) / dasar * 100
        print(f"{LABEL[k]:28s}{format_angka(biaya[k]):>14s}{format_angka(hemat) + '%':>14s}"
              f"{format_angka(waktu[k], 3):>13s}")
    print(f"2-opt selesai dalam {putaran} putaran. Solver eksak: {eksak.iterasi} iterasi, "
          f"{eksak.jumlah_potongan} larangan sub-siklus.")
    for k in rute:
        print(f"\nUrutan kunjungan, {LABEL[k]}:")
        print(" -> ".join(s["kota"] for s in data[k]["urutan"]))
        lewat = [(s["kota"], s["dilewati"]) for s in data[k]["urutan"] if s["dilewati"]]
        for kota, daftar in lewat:
            print(f"  menuju {kota} melewati {', '.join(daftar)}")


if __name__ == "__main__":
    main()

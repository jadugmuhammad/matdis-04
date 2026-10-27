"""Simulasi untuk Soal F.

Tiga percobaan pada matriks jarak yang sama dengan main.py:
  1. Rute acak: seberapa jauh rute asal-asalan dibanding hasil algoritma.
  2. Multi-start: Nearest Neighbor acak + 2-opt diulang, seberapa sering mencapai optimal.
  3. Skala: waktu dan kualitas pada sub-masalah berukuran 8 sampai 36 simpul.

Contoh:
    python simulasi.py --seed 42
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from rute.algoritma import (
    biaya_rute,
    dua_opt,
    jarak_terpendek,
    nearest_neighbor,
    nearest_neighbor_acak,
    solusi_eksak,
    ukur_waktu,
)
from rute.data import KOTA_AKHIR, KOTA_AWAL, muat_matriks
from rute.peta import format_angka

UKURAN = (8, 12, 16, 20, 24, 28, 32, 36)
NAMA = {"nn": "Nearest Neighbor", "nn_2opt": "NN + 2-opt", "eksak": "Optimal (ILP)"}


def baca_argumen() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--matriks", default="data/matriks_jarak.csv")
    p.add_argument("--keluaran", default="hasil")
    p.add_argument("--seed", type=int, default=42, help="seed pengacak agar hasil bisa diulang")
    p.add_argument("--acak", type=int, default=10_000, help="jumlah rute acak")
    p.add_argument("--multistart", type=int, default=200, help="jumlah ulangan multi-start")
    p.add_argument("--sub", type=int, default=5, help="jumlah sub-masalah acak per ukuran")
    return p.parse_args()


def rute_acak(D, awal, akhir, jumlah, rng) -> np.ndarray:
    tengah = np.array([i for i in range(len(D)) if i not in (awal, akhir)])
    urutan = np.array([rng.permutation(tengah) for _ in range(jumlah)])
    penuh = np.hstack([np.full((jumlah, 1), awal), urutan, np.full((jumlah, 1), akhir)])
    return D[penuh[:, :-1], penuh[:, 1:]].sum(axis=1)


def percobaan_acak(D, awal, akhir, acuan, jumlah, rng, keluaran) -> dict:
    jarak = rute_acak(D, awal, akhir, jumlah, rng)
    hasil = {
        "rute_acak_min": jarak.min(), "rute_acak_median": float(np.median(jarak)),
        "rute_acak_rata2": jarak.mean(), "rute_acak_maks": jarak.max(),
        "rute_acak_lebih_baik_dari_nn": int((jarak < acuan["nn"]).sum()),
    }
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.hist(jarak, bins=50, color="#adb5bd")
    for kunci, warna in (("nn", "#e8590c"), ("nn_2opt", "#1c7ed6"), ("eksak", "#2f9e44")):
        ax.axvline(acuan[kunci], color=warna, lw=2,
                   label=f'{NAMA[kunci]}: {format_angka(acuan[kunci])} km')
    ax.set_xlabel("Total jarak (km)")
    ax.set_ylabel("Jumlah rute")
    ax.set_title(f"Distribusi {jumlah:,} rute acak".replace(",", "."))
    ax.legend()
    fig.tight_layout()
    fig.savefig(keluaran / "simulasi_acak.png", dpi=160)
    plt.close(fig)
    return hasil


def percobaan_multistart(D, awal, akhir, optimal, ulang, rng, keluaran) -> dict:
    jarak = np.array([
        biaya_rute(D, dua_opt(D, nearest_neighbor_acak(D, awal, akhir, rng))[0])
        for _ in range(ulang)
    ])
    capai = int((jarak < optimal + 1e-6).sum())
    hasil = {
        "multistart_min": jarak.min(), "multistart_median": float(np.median(jarak)),
        "multistart_maks": jarak.max(), "multistart_capai_optimal": capai,
        "multistart_ulang": ulang,
    }
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.hist(jarak, bins=30, color="#74c0fc")
    ax.axvline(optimal, color="#2f9e44", lw=2, label=f"Optimal: {format_angka(optimal)} km")
    ax.set_xlabel("Total jarak setelah 2-opt (km)")
    ax.set_ylabel("Jumlah ulangan")
    ax.set_title(f"Nearest Neighbor acak + 2-opt, {ulang} ulangan ({capai} mencapai optimal)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(keluaran / "simulasi_multistart.png", dpi=160)
    plt.close(fig)
    return hasil


def percobaan_skala(D, awal, akhir, jumlah_sub, rng, keluaran) -> list[dict]:
    lainnya = [i for i in range(len(D)) if i not in (awal, akhir)]
    baris = []
    for n in UKURAN:
        ulangan = 1 if n == len(D) else jumlah_sub
        waktu = {"nn": [], "nn_2opt": [], "eksak": []}
        celah = {"nn": [], "nn_2opt": []}
        for _ in range(ulangan):
            pilih = [awal, akhir, *rng.choice(lainnya, n - 2, replace=False)]
            Ds = D[np.ix_(pilih, pilih)]
            rute_nn, t_nn = ukur_waktu(lambda: nearest_neighbor(Ds, 0, 1), 20)
            (rute_2, _), t_2 = ukur_waktu(lambda: dua_opt(Ds, rute_nn), 20)
            eksak, t_e = ukur_waktu(lambda: solusi_eksak(Ds, 0, 1), 1)
            waktu["nn"].append(t_nn)
            waktu["nn_2opt"].append(t_nn + t_2)
            waktu["eksak"].append(t_e)
            celah["nn"].append((biaya_rute(Ds, rute_nn) - eksak.biaya) / eksak.biaya * 100)
            celah["nn_2opt"].append((biaya_rute(Ds, rute_2) - eksak.biaya) / eksak.biaya * 100)
        baris.append({
            "n": n,
            "waktu_nn_ms": float(np.median(waktu["nn"])),
            "waktu_nn_2opt_ms": float(np.median(waktu["nn_2opt"])),
            "waktu_eksak_ms": float(np.median(waktu["eksak"])),
            "celah_nn_persen": float(np.mean(celah["nn"])),
            "celah_nn_2opt_persen": float(np.mean(celah["nn_2opt"])),
            "keadaan_held_karp": (n - 2) * 2 ** (n - 2),
            "ulangan": ulangan,
        })

    fig, ax = plt.subplots(figsize=(9, 4.8))
    x = [b["n"] for b in baris]
    for kunci, warna in (("nn", "#e8590c"), ("nn_2opt", "#1c7ed6"), ("eksak", "#2f9e44")):
        ax.plot(x, [b[f"waktu_{kunci}_ms"] for b in baris], "o-", color=warna, label=NAMA[kunci])
    ax.set_yscale("log")
    ax.set_xlabel("Jumlah simpul (n)")
    ax.set_ylabel("Waktu median (ms, skala log)")
    ax.set_title("Waktu komputasi menurut ukuran masalah")
    ax.grid(alpha=0.3, which="both")
    ax.legend()
    fig.tight_layout()
    fig.savefig(keluaran / "simulasi_skala.png", dpi=160)
    plt.close(fig)
    return baris


def main() -> None:
    args = baca_argumen()
    keluaran = Path(args.keluaran)
    keluaran.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    nama, matriks = muat_matriks(args.matriks)
    awal, akhir = nama.index(KOTA_AWAL), nama.index(KOTA_AKHIR)
    D, _ = jarak_terpendek(matriks)

    rute_nn = nearest_neighbor(D, awal, akhir)
    acuan = {
        "nn": biaya_rute(D, rute_nn),
        "nn_2opt": biaya_rute(D, dua_opt(D, rute_nn)[0]),
        "eksak": solusi_eksak(D, awal, akhir).biaya,
    }

    print("1. Rute acak ...")
    ringkas = percobaan_acak(D, awal, akhir, acuan, args.acak, rng, keluaran)
    print("2. Multi-start ...")
    ringkas |= percobaan_multistart(D, awal, akhir, acuan["eksak"], args.multistart, rng, keluaran)
    print("3. Skala ...")
    skala = percobaan_skala(D, awal, akhir, args.sub, rng, keluaran)

    with (keluaran / "simulasi_ringkasan.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["besaran", "nilai"])
        w.writerow(["seed", args.seed])
        for k, v in (acuan | ringkas).items():
            w.writerow([k, round(float(v), 2)])
    with (keluaran / "simulasi_skala.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(skala[0]))
        w.writeheader()
        for b in skala:
            w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in b.items()})

    print("\nAcuan (km):", {k: round(v, 2) for k, v in acuan.items()})
    for k, v in ringkas.items():
        print(f"  {k}: {round(float(v), 2)}")
    print("\n   n  NN(ms)  NN+2opt(ms)  Eksak(ms)  celah NN(%)  celah NN+2opt(%)")
    for b in skala:
        print(f"{b['n']:4d}{b['waktu_nn_ms']:8.2f}{b['waktu_nn_2opt_ms']:13.2f}"
              f"{b['waktu_eksak_ms']:11.1f}{b['celah_nn_persen']:13.2f}{b['celah_nn_2opt_persen']:18.2f}")
    print(f"\nFile hasil ditulis ke folder '{keluaran}'.")


if __name__ == "__main__":
    main()

"""Algoritma pencarian rute Semarang-Jakarta.

Semua fungsi memakai matriks jarak `D` (n x n, km) dan rute berupa daftar indeks
simpul. Rute selalu diawali `awal` dan diakhiri `akhir`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from statistics import median
from typing import Callable

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, vstack
from scipy.sparse.csgraph import shortest_path

Rute = list[int]


def jarak_terpendek(matriks: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Jarak terpendek semua pasangan (Dijkstra dari setiap simpul) beserta predecessor-nya.

    Jarak OSRM diukur pada rute tercepat, sehingga A -> C -> B kadang lebih pendek dari A -> B.
    """
    return shortest_path(matriks, method="D", directed=True, return_predecessors=True)


def lintasan(pred: np.ndarray, a: int, b: int) -> Rute:
    """Simpul-simpul yang dilalui pada jalur terpendek dari a ke b, termasuk keduanya."""
    jalur = [b]
    while jalur[-1] != a:
        sebelumnya = int(pred[a, jalur[-1]])
        if sebelumnya < 0:
            raise ValueError(f"Tidak ada jalur dari simpul {a} ke {b}.")
        jalur.append(sebelumnya)
    return jalur[::-1]


def lintasan_lengkap(pred: np.ndarray, rute: Rute) -> Rute:
    """Rute kunjungan diperluas menjadi urutan semua kota yang benar-benar dilalui."""
    jalan = [rute[0]]
    for a, b in zip(rute[:-1], rute[1:]):
        jalan.extend(lintasan(pred, a, b)[1:])
    return jalan


def biaya_rute(D: np.ndarray, rute: Rute) -> float:
    r = np.asarray(rute)
    return float(D[r[:-1], r[1:]].sum())


def periksa_rute(rute: Rute, n: int, awal: int, akhir: int) -> None:
    """Pastikan rute memuat setiap simpul tepat satu kali dengan awal dan akhir yang benar."""
    if rute[0] != awal or rute[-1] != akhir:
        raise AssertionError("Rute tidak dimulai di titik awal atau tidak berakhir di titik akhir.")
    if sorted(rute) != list(range(n)):
        raise AssertionError("Rute tidak memuat setiap simpul tepat satu kali.")


def nearest_neighbor(D: np.ndarray, awal: int, akhir: int) -> Rute:
    """Dari kota saat ini, pindah ke kota terdekat yang belum dikunjungi. Jakarta selalu terakhir."""
    belum = sorted(set(range(len(D))) - {awal, akhir})
    rute = [awal]
    while belum:
        berikut = min(belum, key=lambda j: D[rute[-1], j])
        rute.append(berikut)
        belum.remove(berikut)
    rute.append(akhir)
    return rute


def nearest_neighbor_acak(
    D: np.ndarray, awal: int, akhir: int, rng: np.random.Generator, k: int = 3
) -> Rute:
    """Seperti Nearest Neighbor, tetapi memilih acak di antara k kota terdekat."""
    belum = sorted(set(range(len(D))) - {awal, akhir})
    rute = [awal]
    while belum:
        terdekat = sorted(belum, key=lambda j: D[rute[-1], j])[:k]
        berikut = int(rng.choice(terdekat))
        rute.append(berikut)
        belum.remove(berikut)
    rute.append(akhir)
    return rute


def dua_opt(D: np.ndarray, rute: Rute) -> tuple[Rute, int]:
    """Perbaikan 2-opt: balik potongan rute selama total jarak masih bisa turun.

    Karena matriks asimetris, biaya potongan yang dibalik dihitung ulang, bukan dianggap sama.
    Titik awal dan akhir tidak pernah dipindahkan. Mengembalikan rute dan jumlah putaran.
    """
    rute = list(rute)
    n = len(rute)
    putaran = 0
    ada_perbaikan = True
    while ada_perbaikan:
        ada_perbaikan = False
        putaran += 1
        for i in range(1, n - 2):
            for j in range(i + 1, n - 1):
                sebelum, sesudah = rute[i - 1], rute[j + 1]
                potongan = rute[i : j + 1]
                maju = D[potongan[:-1], potongan[1:]].sum()
                mundur = D[potongan[1:], potongan[:-1]].sum()
                lama = D[sebelum, potongan[0]] + maju + D[potongan[-1], sesudah]
                baru = D[sebelum, potongan[-1]] + mundur + D[potongan[0], sesudah]
                if baru < lama - 1e-9:
                    rute[i : j + 1] = potongan[::-1]
                    ada_perbaikan = True
    return rute, putaran


@dataclass
class HasilEksak:
    rute: Rute
    biaya: float
    iterasi: int
    jumlah_potongan: int


def solusi_eksak(
    D: np.ndarray, awal: int, akhir: int, batas_waktu: float = 600.0
) -> HasilEksak:
    """Solusi optimal global lewat integer linear programming (HiGHS).

    Jalur awal -> akhir diubah menjadi siklus dengan busur semu akhir -> awal berbiaya nol.
    Larangan sub-siklus ditambahkan bertahap hanya ketika solusi sementara memuatnya.
    """
    n = len(D)
    busur = [(i, j) for i in range(n) for j in range(n) if i != j]
    indeks = {b: k for k, b in enumerate(busur)}
    m = len(busur)

    biaya = np.array([D[i, j] for i, j in busur], dtype=float)
    semu = indeks[(akhir, awal)]
    biaya[semu] = 0.0

    # Setiap kota keluar satu kali dan masuk satu kali.
    baris = [x for k, (i, j) in enumerate(busur) for x in (i, n + j)]
    kolom = [k for k in range(m) for _ in range(2)]
    derajat = csr_matrix((np.ones(len(baris)), (baris, kolom)), shape=(2 * n, m))

    batas_bawah = np.zeros(m)
    batas_bawah[semu] = 1.0
    batas = Bounds(batas_bawah, np.ones(m))

    potongan: list[csr_matrix] = []
    ruas_kanan: list[float] = []
    mulai = time.perf_counter()
    iterasi = 0

    while True:
        iterasi += 1
        sisa = batas_waktu - (time.perf_counter() - mulai)
        if sisa <= 0:
            raise TimeoutError("Batas waktu solusi eksak terlampaui.")

        kendala = [LinearConstraint(derajat, 1, 1)]
        if potongan:
            kendala.append(
                LinearConstraint(vstack(potongan), -np.inf, np.array(ruas_kanan))
            )
        hasil = milp(
            biaya,
            constraints=kendala,
            integrality=np.ones(m),
            bounds=batas,
            options={"time_limit": sisa, "mip_rel_gap": 0.0},
        )
        if hasil.status != 0 or hasil.x is None:
            raise RuntimeError(f"Solver berhenti tanpa solusi optimal: {hasil.message}")

        penerus = {busur[k][0]: busur[k][1] for k in np.flatnonzero(hasil.x > 0.5)}
        siklus = _pisahkan_siklus(penerus, n)
        if len(siklus) == 1:
            break

        for himpunan in siklus:
            anggota = [indeks[(i, j)] for i in himpunan for j in himpunan if i != j]
            potongan.append(
                csr_matrix(
                    (np.ones(len(anggota)), ([0] * len(anggota), anggota)), shape=(1, m)
                )
            )
            ruas_kanan.append(len(himpunan) - 1)

    rute = [awal]
    while rute[-1] != akhir:
        rute.append(penerus[rute[-1]])
    return HasilEksak(rute, biaya_rute(D, rute), iterasi, len(potongan))


def _pisahkan_siklus(penerus: dict[int, int], n: int) -> list[list[int]]:
    terlihat: set[int] = set()
    semua = []
    for mulai in range(n):
        if mulai in terlihat:
            continue
        siklus = [mulai]
        terlihat.add(mulai)
        u = penerus[mulai]
        while u != mulai:
            siklus.append(u)
            terlihat.add(u)
            u = penerus[u]
        semua.append(siklus)
    return semua


def ukur_waktu(fungsi: Callable[[], object], ulang: int) -> tuple[object, float]:
    """Jalankan `fungsi` sebanyak `ulang` kali. Mengembalikan hasil terakhir dan median waktu (ms)."""
    durasi = []
    hasil = None
    for _ in range(ulang):
        t0 = time.perf_counter()
        hasil = fungsi()
        durasi.append((time.perf_counter() - t0) * 1000)
    return hasil, median(durasi)

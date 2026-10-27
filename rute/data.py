"""Pemuatan dan validasi matriks jarak serta koordinat kota."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

KOTA_AWAL = "Semarang"
KOTA_AKHIR = "Jakarta"


def periksa_matriks(matriks: np.ndarray) -> None:
    """Pastikan matriks jarak bisa dipakai: persegi, lengkap, diagonal nol, jarak lain positif."""
    if matriks.ndim != 2 or matriks.shape[0] != matriks.shape[1]:
        raise ValueError(f"Matriks harus persegi, ditemukan {matriks.shape}.")
    if np.isnan(matriks).any():
        raise ValueError("Matriks memuat sel kosong.")
    if (matriks < 0).any():
        raise ValueError("Matriks memuat jarak negatif.")
    if np.diag(matriks).any():
        raise ValueError("Diagonal matriks harus nol.")
    # Dijkstra pada matriks padat menganggap nol sebagai "tidak ada sisi".
    di_luar_diagonal = matriks[~np.eye(len(matriks), dtype=bool)]
    if (di_luar_diagonal <= 0).any():
        raise ValueError("Jarak antarkota yang berbeda harus bernilai positif.")


def muat_matriks(path: str | Path) -> tuple[list[str], np.ndarray]:
    """Baca matriks jarak (km). Baris adalah asal, kolom adalah tujuan."""
    df = pd.read_csv(path, index_col=0)
    df.index = df.index.str.strip()
    df.columns = df.columns.str.strip()

    if list(df.index) != list(df.columns):
        raise ValueError("Urutan nama baris dan kolom matriks harus sama.")
    matriks = df.to_numpy(dtype=float)
    periksa_matriks(matriks)
    return list(df.index), matriks


def simpan_matriks(path: str | Path, nama: list[str], matriks: np.ndarray) -> None:
    """Tulis matriks jarak dengan format yang sama seperti yang dibaca `muat_matriks`."""
    periksa_matriks(matriks)
    df = pd.DataFrame(matriks, index=nama, columns=nama)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, float_format="%.2f")


def baca_koordinat(path: str | Path) -> tuple[list[str], np.ndarray]:
    """Baca nama kota dan koordinatnya (lintang, bujur) sesuai urutan di berkas."""
    df = pd.read_csv(path, index_col=0)
    df.index = df.index.str.strip()
    return list(df.index), df[["lintang", "bujur"]].to_numpy(dtype=float)


def muat_koordinat(path: str | Path, nama: list[str]) -> np.ndarray:
    """Koordinat sebagai array (n, 2) berisi lintang dan bujur, urut sesuai `nama`."""
    daftar, koordinat = baca_koordinat(path)
    urutan = {k: i for i, k in enumerate(daftar)}
    hilang = [k for k in nama if k not in urutan]
    if hilang:
        raise ValueError(f"Koordinat tidak ditemukan untuk: {', '.join(hilang)}")
    return koordinat[[urutan[k] for k in nama]]

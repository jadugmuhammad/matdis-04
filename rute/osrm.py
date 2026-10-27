"""Pengambilan matriks jarak dari server OSRM lewat Table API. Butuh internet untuk server publik."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import numpy as np

SERVER_PUBLIK = "https://router.project-osrm.org"
PROFIL_BAWAAN = "driving"


def ambil_matriks_osrm(
    koordinat: np.ndarray,
    server: str = SERVER_PUBLIK,
    profil: str = PROFIL_BAWAAN,
    batas_waktu: float = 60.0,
) -> np.ndarray:
    """Matriks jarak berkendara (km, dibulatkan dua desimal) antar semua pasangan titik.

    `koordinat` berisi (lintang, bujur) per baris. Baris matriks adalah asal dan kolomnya tujuan.
    Satu permintaan memuat semua titik, jadi jumlah titik dibatasi `--max-table-size` server
    (bawaan OSRM: 100).
    """
    n = len(koordinat)
    titik = ";".join(f"{bujur:.6f},{lintang:.6f}" for lintang, bujur in koordinat)
    url = f"{server.rstrip('/')}/table/v1/{profil}/{titik}?annotations=distance"

    permintaan = urllib.request.Request(url, headers={"User-Agent": "rute-jateng-tugas-graf"})
    try:
        with urllib.request.urlopen(permintaan, timeout=batas_waktu) as respons:
            isi = json.load(respons)
    except urllib.error.HTTPError as galat:
        pesan = galat.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"Server OSRM membalas HTTP {galat.code}: {pesan}") from galat
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as galat:
        raise RuntimeError(f"Gagal mengambil matriks dari {server}: {galat}") from galat

    if isi.get("code") != "Ok":
        raise RuntimeError(f"OSRM menolak permintaan: {isi.get('code')} {isi.get('message', '')}")
    if isi.get("distances") is None:
        raise RuntimeError("Respons OSRM tidak memuat 'distances'. Pastikan server mendukung annotations=distance.")

    # Pasangan titik yang tidak terhubung dikembalikan sebagai null, dibaca NumPy sebagai NaN.
    meter = np.array(isi["distances"], dtype=float)
    if meter.shape != (n, n):
        raise RuntimeError(f"Ukuran matriks dari OSRM {meter.shape}, diharapkan {(n, n)}.")
    if np.isnan(meter).any():
        pasangan = int(np.isnan(meter).sum())
        raise RuntimeError(f"{pasangan} pasangan titik tidak terhubung di jaringan jalan OSRM.")
    return np.round(meter / 1000.0, 2)

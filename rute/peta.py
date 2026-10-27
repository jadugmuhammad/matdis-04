"""Visualisasi rute: gambar statis (matplotlib) dan peta interaktif berbasis Leaflet."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .algoritma import Rute, lintasan

OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"


def susun_data_rute(
    kode: str,
    label: str,
    warna: str,
    nama: list[str],
    koordinat: np.ndarray,
    matriks: np.ndarray,
    pred: np.ndarray,
    rute: Rute,
    geometri: dict[str, list[list[float]]] | None = None,
) -> dict:
    """Ringkas satu rute menjadi struktur yang dipakai peta HTML dan file CSV."""
    geometri = geometri or {}

    def titik(k: int) -> list[float]:
        return [float(x) for x in koordinat[k]]

    urutan = [
        {"no": 1, "kota": nama[rute[0]], "lintang": titik(rute[0])[0], "bujur": titik(rute[0])[1],
         "jarak_km": 0.0, "kumulatif_km": 0.0, "dilewati": []}
    ]
    langkah = []
    berjalan = 0.0
    for no, (a, b) in enumerate(zip(rute[:-1], rute[1:]), start=2):
        jalur = lintasan(pred, a, b)
        awal_ruas = berjalan
        for u, v in zip(jalur[:-1], jalur[1:]):
            km = float(matriks[u, v])
            berjalan += km
            langkah.append({
                "dari": nama[u], "ke": nama[v], "km": km, "kumulatif_km": berjalan,
                "garis": geometri.get(f"{u}-{v}") or [titik(u), titik(v)],
            })
        urutan.append({
            "no": no, "kota": nama[b], "lintang": titik(b)[0], "bujur": titik(b)[1],
            "jarak_km": round(berjalan - awal_ruas, 2), "kumulatif_km": round(berjalan, 2),
            "dilewati": [nama[x] for x in jalur[1:-1]],
        })
    return {
        "kode": kode, "label": label, "warna": warna,
        "total_km": berjalan, "urutan": urutan, "langkah": langkah,
    }


def format_angka(nilai: float, desimal: int = 2) -> str:
    """Format angka gaya Indonesia: titik untuk ribuan, koma untuk desimal."""
    return f"{nilai:,.{desimal}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def ambil_geometri_osrm(
    koordinat: np.ndarray,
    pasangan: set[tuple[int, int]],
    file_cache: Path,
    jeda: float = 1.0,
) -> dict[str, list[list[float]]]:
    """Ambil bentuk jalan tiap ruas dari server OSRM publik. Butuh internet.

    Hasil disimpan di `file_cache` agar pemanggilan berikutnya tidak mengulang permintaan.
    Ruas yang gagal diambil dilewati dan akan digambar sebagai garis lurus.
    """
    cache: dict[str, list[list[float]]] = {}
    if file_cache.exists():
        cache = json.loads(file_cache.read_text(encoding="utf-8"))

    baru = 0
    for a, b in sorted(pasangan):
        kunci = f"{a}-{b}"
        if kunci in cache:
            continue
        url = OSRM_URL.format(
            lon1=koordinat[a][1], lat1=koordinat[a][0], lon2=koordinat[b][1], lat2=koordinat[b][0]
        ) + "?overview=full&geometries=geojson"
        try:
            permintaan = urllib.request.Request(url, headers={"User-Agent": "rute-jateng-tugas-graf"})
            with urllib.request.urlopen(permintaan, timeout=30) as respons:
                isi = json.load(respons)
            titik = isi["routes"][0]["geometry"]["coordinates"]
            cache[kunci] = [[lat, lon] for lon, lat in titik]
            baru += 1
        except (urllib.error.URLError, KeyError, IndexError, TimeoutError, json.JSONDecodeError) as galat:
            print(f"  peringatan: geometri ruas {kunci} gagal diambil ({galat})", file=sys.stderr)
        time.sleep(jeda)

    if baru:
        file_cache.parent.mkdir(parents=True, exist_ok=True)
        file_cache.write_text(json.dumps(cache), encoding="utf-8")
    return cache


def gambar_rute(path: Path, data: dict, nama_awal: str, nama_akhir: str) -> None:
    """Gambar statis rute pada bidang lintang-bujur (tanpa peta dasar, tidak butuh internet)."""
    fig, ax = plt.subplots(figsize=(14, 6.5))
    titik = [(s["lintang"], s["bujur"]) for s in data["urutan"]]
    lintang_rata = float(np.mean([t[0] for t in titik]))
    ax.set_aspect(1 / np.cos(np.radians(lintang_rata)))

    for a, b in zip(data["urutan"][:-1], data["urutan"][1:]):
        ax.annotate(
            "",
            xy=(b["bujur"], b["lintang"]),
            xytext=(a["bujur"], a["lintang"]),
            arrowprops={"arrowstyle": "-|>", "color": data["warna"], "lw": 1.3, "alpha": 0.85,
                        "shrinkA": 4, "shrinkB": 4},
        )
    for s in data["urutan"]:
        if s["kota"] == nama_awal:
            warna = "#2f9e44"
        elif s["kota"] == nama_akhir:
            warna = "#e03131"
        else:
            warna = "white"
        ax.scatter(s["bujur"], s["lintang"], s=70, c=warna, edgecolors="black", zorder=3)
        ax.annotate(f'{s["no"]}. {s["kota"]}', (s["bujur"], s["lintang"]),
                    textcoords="offset points", xytext=(5, 5), fontsize=7.5)

    ax.set_xlabel("Bujur (°E)")
    ax.set_ylabel("Lintang (°)")
    ax.set_title(f'{data["label"]}: {format_angka(data["total_km"])} km')
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def buat_peta_html(path: Path, metode: list[dict]) -> None:
    """Tulis satu file HTML berisi peta Leaflet, pilihan metode, dan simulasi perjalanan."""
    muatan = json.dumps({"metode": metode}, ensure_ascii=False).replace("</", "<\\/")
    path.write_text(_TEMPLAT.replace("__DATA__", muatan), encoding="utf-8")


_TEMPLAT = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rute Semarang - Jakarta melalui 35 ibu kota Jawa Tengah</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css">
<style>
  html, body { height: 100%; margin: 0; font-family: system-ui, sans-serif; }
  body { display: flex; }
  #peta { flex: 1; min-width: 0; }
  #panel { width: 330px; padding: 12px; overflow-y: auto; border-left: 1px solid #ccc; box-sizing: border-box; }
  #panel h1 { font-size: 16px; margin: 0 0 8px; }
  #panel label { display: block; margin: 8px 0 4px; font-size: 13px; }
  #panel select, #panel button { width: 100%; padding: 6px; font-size: 14px; }
  #info { margin: 10px 0; padding: 8px; background: #f1f3f5; border-radius: 4px; font-size: 13px; min-height: 3.2em; }
  #daftar { padding-left: 22px; font-size: 12.5px; line-height: 1.5; }
  .nomor { background: none; border: none; box-shadow: none; color: #fff; font-weight: 700; font-size: 11px; padding: 0; }
  .nomor::before { display: none; }
  .mobil { font-size: 22px; line-height: 22px; }
  @media (max-width: 800px) { body { flex-direction: column; } #panel { width: auto; height: 40%; border-left: 0; border-top: 1px solid #ccc; } }
</style>
</head>
<body>
<div id="peta"></div>
<div id="panel">
  <h1>Rute Semarang - Jakarta</h1>
  <label for="metode">Metode</label>
  <select id="metode"></select>
  <label for="kecepatan">Kecepatan simulasi</label>
  <input id="kecepatan" type="range" min="1" max="10" value="4" style="width:100%">
  <button id="putar" style="margin-top:8px">Putar simulasi perjalanan</button>
  <div id="info"></div>
  <ol id="daftar"></ol>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
<script>
const DATA = __DATA__;
const fmt = new Intl.NumberFormat('id-ID', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const peta = L.map('peta');
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 18,
  attribution: '&copy; kontributor OpenStreetMap'
}).addTo(peta);

const lapisan = L.layerGroup().addTo(peta);
const elInfo = document.getElementById('info');
const elDaftar = document.getElementById('daftar');
const elPilih = document.getElementById('metode');
const elPutar = document.getElementById('putar');
const elKecepatan = document.getElementById('kecepatan');

let aktif = null;
let mobil = null;
let timer = null;
let titikAnim = [];
let posisi = 0;

DATA.metode.forEach((m, i) => {
  const o = document.createElement('option');
  o.value = i;
  o.textContent = m.label + ' (' + fmt.format(m.total_km) + ' km)';
  elPilih.appendChild(o);
});

function berhenti() {
  if (timer) { clearInterval(timer); timer = null; }
  elPutar.textContent = 'Putar simulasi perjalanan';
}

function tampilkan(i) {
  berhenti();
  lapisan.clearLayers();
  mobil = null;
  aktif = DATA.metode[i];

  aktif.langkah.forEach(l => {
    L.polyline(l.garis, { color: aktif.warna, weight: 4, opacity: 0.8 }).addTo(lapisan);
  });

  const batas = [];
  elDaftar.innerHTML = '';
  aktif.urutan.forEach(s => {
    batas.push([s.lintang, s.bujur]);
    const awal = s.no === 1;
    const akhir = s.no === aktif.urutan.length;
    const warna = awal ? '#2f9e44' : (akhir ? '#e03131' : aktif.warna);
    const pen = L.circleMarker([s.lintang, s.bujur], {
      radius: 11, color: '#fff', weight: 2, fillColor: warna, fillOpacity: 1
    }).addTo(lapisan);
    pen.bindTooltip(String(s.no), { permanent: true, direction: 'center', className: 'nomor' });
    pen.bindPopup('<b>' + s.no + '. ' + s.kota + '</b><br>Dari kota sebelumnya: ' +
      fmt.format(s.jarak_km) + ' km<br>Kumulatif: ' + fmt.format(s.kumulatif_km) + ' km' +
      (s.dilewati.length ? '<br>Melewati: ' + s.dilewati.join(', ') : ''));

    const li = document.createElement('li');
    li.textContent = s.kota + ' (' + fmt.format(s.kumulatif_km) + ' km)';
    elDaftar.appendChild(li);
  });
  peta.fitBounds(L.latLngBounds(batas).pad(0.08));

  titikAnim = siapkanAnimasi(aktif);
  posisi = 0;
  elInfo.textContent = aktif.label + ': total ' + fmt.format(aktif.total_km) + ' km, ' +
    aktif.langkah.length + ' ruas jalan.';
}

function siapkanAnimasi(m) {
  const hasil = [];
  let awalKm = 0;
  m.langkah.forEach((l, idx) => {
    const sub = [];
    for (let k = 0; k < l.garis.length - 1; k++) {
      const p = l.garis[k], q = l.garis[k + 1];
      const langkahKecil = Math.max(1, Math.ceil(Math.hypot(q[0] - p[0], q[1] - p[1]) / 0.01));
      for (let s = 0; s < langkahKecil; s++) {
        sub.push([p[0] + (q[0] - p[0]) * s / langkahKecil, p[1] + (q[1] - p[1]) * s / langkahKecil]);
      }
    }
    sub.push(l.garis[l.garis.length - 1]);
    sub.forEach((t, s) => {
      hasil.push({ lat: t[0], lon: t[1], ruas: idx, km: awalKm + l.km * s / (sub.length - 1) });
    });
    awalKm += l.km;
  });
  return hasil;
}

function majuSatuTick() {
  const laju = parseInt(elKecepatan.value, 10) * 2;
  posisi = Math.min(posisi + laju, titikAnim.length - 1);
  const t = titikAnim[posisi];
  if (!mobil) {
    mobil = L.marker([t.lat, t.lon], {
      icon: L.divIcon({ className: 'mobil', html: '&#128663;', iconSize: [24, 24], iconAnchor: [12, 12] }),
      zIndexOffset: 1000
    }).addTo(lapisan);
  } else {
    mobil.setLatLng([t.lat, t.lon]);
  }
  const l = aktif.langkah[t.ruas];
  elInfo.textContent = 'Ruas ' + (t.ruas + 1) + '/' + aktif.langkah.length + ': ' + l.dari + ' \\u2192 ' + l.ke +
    '. Ditempuh ' + fmt.format(t.km) + ' dari ' + fmt.format(aktif.total_km) + ' km.';
  if (posisi >= titikAnim.length - 1) { berhenti(); }
}

elPutar.addEventListener('click', () => {
  if (timer) { berhenti(); return; }
  if (posisi >= titikAnim.length - 1) { posisi = 0; }
  elPutar.textContent = 'Jeda';
  timer = setInterval(majuSatuTick, 30);
});
elPilih.addEventListener('change', () => tampilkan(parseInt(elPilih.value, 10)));

tampilkan(DATA.metode.length - 1);
elPilih.value = String(DATA.metode.length - 1);
</script>
</body>
</html>
"""

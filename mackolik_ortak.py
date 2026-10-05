"""
Ortak modül: HTTP oturumu, günün programını çekme, veritabanı ve Excel işlemleri.
acilis_tara.py ve kapanis_tara.py bu modülü kullanır.
"""

import re
import json
import sqlite3
from datetime import datetime, timedelta

import cloudscraper
import pandas as pd

DB_DOSYASI = "mackolik_oran.db"
EXCEL_YAKLASAN_DOSYASI = "oranlar_yaklasan.xlsx"
EXCEL_TAMAMLANAN_DOSYASI = "oranlar_tamamlanan.xlsx"

# ---------------------------------------------------------------------------
# HTTP oturumu
# ---------------------------------------------------------------------------
scraper = cloudscraper.create_scraper()
scraper.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "tr,en-US;q=0.9,en;q=0.8",
})
_OTURUM_HAZIR = False


def _oturumu_hazirla():
    global _OTURUM_HAZIR
    if _OTURUM_HAZIR:
        return
    scraper.get("https://arsiv.mackolik.com/Genis-Iddaa-Programi", timeout=15)
    _OTURUM_HAZIR = True


def _js_to_python(raw: str):
    converted = re.sub(r'([{,])(\w+):', r'\1"\2":', raw)
    converted = converted.replace("'", '"')
    return json.loads(converted)


# ---------------------------------------------------------------------------
# Alan haritası (İtalya-Belçika maçıyla birebir doğrulandı)
# ---------------------------------------------------------------------------
ODDS_ALANLARI = [
    "ms1", "msx", "ms2", "cs_1x", "cs_12", "cs_x2", "au25_alt", "au25_ust",
    "tga_0_1", "tga_2_3", "tga_4_5", "tga_6_plus", "iy1", "iyx", "iy2",
    "kg_var", "kg_yok", "iy15_alt", "iy15_ust", "au15_alt", "au15_ust",
    "au35_alt", "au35_ust",
]

BASLIKLAR = {
    "ms1": "MS 1", "msx": "MS X", "ms2": "MS 2",
    "cs_1x": "ÇŞ 1-X", "cs_12": "ÇŞ 1-2", "cs_x2": "ÇŞ X-2",
    "au25_alt": "2,5 Alt", "au25_ust": "2,5 Üst",
    "tga_0_1": "Gol Aralığı 0-1", "tga_2_3": "Gol Aralığı 2-3",
    "tga_4_5": "Gol Aralığı 4-5", "tga_6_plus": "Gol Aralığı 6+",
    "iy1": "İY 1", "iyx": "İY X", "iy2": "İY 2",
    "kg_var": "KG Var", "kg_yok": "KG Yok",
    "iy15_alt": "İY 1,5 Alt", "iy15_ust": "İY 1,5 Üst",
    "au15_alt": "1,5 Alt", "au15_ust": "1,5 Üst",
    "au35_alt": "3,5 Alt", "au35_ust": "3,5 Üst",
}


def gunun_programini_cek(tarih_str: str) -> list:
    """tarih_str: 'GG.AA.YYYY'. O günün tüm maçlarını, doğrulanmış alan haritasıyla döner."""
    _oturumu_hazirla()
    url = "https://arsiv.mackolik.com/AjaxHandlers/ProgramDataHandler.ashx"
    params = {
        "type": 6, "sortValue": "DATE", "day": tarih_str,
        "sort": -1, "sortDir": -1, "groupId": -1, "np": 1, "sport": 1,
    }
    headers = {
        "Referer": "https://arsiv.mackolik.com/Genis-Iddaa-Programi",
        "X-Requested-With": "XMLHttpRequest",
    }
    r = scraper.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    veri = _js_to_python(r.text)

    sonuc = []
    for gun_grubu in veri.get("m", []):
        tarih = gun_grubu.get("d")
        for m in gun_grubu.get("m", []):
            try:
                sonuc.append({
                    "mac_id": m[0], "ev_sahibi": m[1], "misafir": m[3],
                    "saat": m[6], "tarih": m[7] or tarih,
                    "skor_ev": m[8], "skor_dep": m[9], "lig_kodu": m[26],
                    "ms1": m[16], "msx": m[17], "ms2": m[18],
                    "cs_1x": m[19], "cs_12": m[20], "cs_x2": m[21],
                    "au25_alt": m[22], "au25_ust": m[23],
                    "tga_0_1": m[29], "tga_2_3": m[30], "tga_4_5": m[31], "tga_6_plus": m[32],
                    "iy1": m[33], "iyx": m[34], "iy2": m[35],
                    "kg_var": m[39], "kg_yok": m[40],
                    "iy15_alt": m[42], "iy15_ust": m[43],
                    "au15_alt": m[44], "au15_ust": m[45],
                    "au35_alt": m[46], "au35_ust": m[47],
                })
            except (IndexError, TypeError):
                continue
    return sonuc


def mac_kickoff_zamani(kayit: dict):
    """'tarih' (GG.AA.YYYY) + 'saat' (SS:DD) alanlarından datetime üretir."""
    try:
        return datetime.strptime(f"{kayit['tarih']} {kayit['saat']}", "%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Veritabanı
# ---------------------------------------------------------------------------
def veritabani_hazirla():
    conn = sqlite3.connect(DB_DOSYASI, timeout=30)
    cursor = conn.cursor()
    sutun_tanimlari = ",\n            ".join(f"{a} TEXT" for a in ODDS_ALANLARI)
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS mac_oranlari (
            mac_id INTEGER NOT NULL,
            asama TEXT NOT NULL CHECK(asama IN ('acilis', 'kapanis')),
            tarih TEXT, saat TEXT, lig_kodu TEXT,
            ev_sahibi TEXT, misafir TEXT,
            skor_ev TEXT, skor_dep TEXT,
            {sutun_tanimlari},
            kaydedilme_zamani TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (mac_id, asama)
        )
    """)
    conn.commit()
    conn.close()


def kayitlari_kaydet(kayitlar: list, asama: str) -> int:
    """asama='acilis' veya 'kapanis'. Zaten kaydedilmiş olan (mac_id, asama) çiftleri
    ASLA üzerine yazılmaz (INSERT OR IGNORE) - açılış/kapanış bir kez sabitlenir."""
    if not kayitlar:
        return 0
    conn = sqlite3.connect(DB_DOSYASI, timeout=30)
    cursor = conn.cursor()
    tum_sutunlar = ["mac_id", "tarih", "saat", "lig_kodu", "ev_sahibi", "misafir",
                    "skor_ev", "skor_dep"] + ODDS_ALANLARI
    yer_tutucu = ", ".join("?" for _ in tum_sutunlar + ["asama"])
    sutun_isimleri = ", ".join(tum_sutunlar + ["asama"])
    sorgu = f"INSERT OR IGNORE INTO mac_oranlari ({sutun_isimleri}) VALUES ({yer_tutucu})"

    eklenen = 0
    for kayit in kayitlar:
        cursor.execute(sorgu, [kayit[s] for s in tum_sutunlar] + [asama])
        eklenen += cursor.rowcount
    conn.commit()
    conn.close()
    return eklenen


def kapanissiz_yaklasan_maclari_getir(dakika_min: int, dakika_max: int) -> list:
    """Açılışı kaydedilmiş ama kapanışı henüz alınmamış, kickoff'a dakika_min-dakika_max
    dakika kalmış maçları döner. [{'mac_id':.., 'tarih':.., ...}, ...]"""
    conn = sqlite3.connect(DB_DOSYASI, timeout=30)
    conn.row_factory = sqlite3.Row
    satirlar = conn.execute("""
        SELECT a.mac_id, a.tarih, a.saat, a.ev_sahibi, a.misafir
        FROM mac_oranlari a
        WHERE a.asama = 'acilis'
          AND NOT EXISTS (
              SELECT 1 FROM mac_oranlari k
              WHERE k.mac_id = a.mac_id AND k.asama = 'kapanis'
          )
    """).fetchall()
    conn.close()

    simdi = datetime.now()
    sonuc = []
    for satir in satirlar:
        kickoff = mac_kickoff_zamani(dict(satir))
        if kickoff is None:
            continue
        kalan_dk = (kickoff - simdi).total_seconds() / 60
        if dakika_min <= kalan_dk <= dakika_max:
            sonuc.append(dict(satir))
    return sonuc


# ---------------------------------------------------------------------------
# Excel'e otomatik aktarım (açılış/kapanış karşılaştırmalı)
# ---------------------------------------------------------------------------
def _oran_sayiya(seri):
    sayi = pd.to_numeric(seri.astype(str).str.replace(",", ".", regex=False), errors="coerce")
    return sayi.where(sayi > 0)


def excele_aktar():
    conn = sqlite3.connect(DB_DOSYASI, timeout=30)
    try:
        acilis = pd.read_sql_query("SELECT * FROM mac_oranlari WHERE asama='acilis'", conn)
        kapanis = pd.read_sql_query("SELECT * FROM mac_oranlari WHERE asama='kapanis'", conn)
    finally:
        conn.close()

    if acilis.empty:
        print("[EXCEL] Henüz açılış verisi yok, Excel oluşturulmadı.")
        return

    for df in (acilis, kapanis):
        for alan in ODDS_ALANLARI:
            if alan in df.columns:
                df[alan] = _oran_sayiya(df[alan])

    temel = acilis[["mac_id", "tarih", "saat", "lig_kodu", "ev_sahibi", "misafir"]]
    karsilastirma = temel.copy()
    for alan in ODDS_ALANLARI:
        karsilastirma[f"{BASLIKLAR[alan]} (Açılış)"] = acilis[alan]
    if not kapanis.empty:
        kapanis_indeksli = kapanis.set_index("mac_id")
        for alan in ODDS_ALANLARI:
            karsilastirma[f"{BASLIKLAR[alan]} (Kapanış)"] = (
                karsilastirma["mac_id"].map(kapanis_indeksli[alan]))
        karsilastirma["Skor"] = (
            karsilastirma["mac_id"].map(kapanis_indeksli["skor_ev"]).astype(str) + "-" +
            karsilastirma["mac_id"].map(kapanis_indeksli["skor_dep"]).astype(str))
    else:
        for alan in ODDS_ALANLARI:
            karsilastirma[f"{BASLIKLAR[alan]} (Kapanış)"] = None

    # Kronolojik sıralama için gerçek tarih/saat anahtarı (metin sıralaması "01.10" ile
    # "29.09"u yanlış sıraya koyardı, çünkü '0' < '2')
    siralama_anahtari = pd.to_datetime(
        karsilastirma["tarih"] + " " + karsilastirma["saat"],
        format="%d.%m.%Y %H:%M", errors="coerce")

    karsilastirma = karsilastirma.rename(columns={
        "mac_id": "Maç ID", "tarih": "Tarih", "saat": "Saat", "lig_kodu": "Lig",
        "ev_sahibi": "Ev Sahibi", "misafir": "Misafir",
    })
    karsilastirma = (karsilastirma.assign(_sira=siralama_anahtari)
                      .sort_values("_sira", kind="stable", na_position="last"))

    # Kickoff saati şu ana göre geçmiş mi gelecek mi -> iki ayrı sayfa, karışıklığı önler
    simdi = pd.Timestamp.now()
    gecmis_mi = karsilastirma["_sira"] < simdi
    yaklasan = karsilastirma[~gecmis_mi].drop(columns="_sira")

    # Tamamlananları en YENİDEN en ESKİYE göster (en üstte en son biten maç)
    tamamlanan_sira = siralama_anahtari[gecmis_mi]
    tamamlanan = (karsilastirma[gecmis_mi]
                  .assign(_s2=tamamlanan_sira)
                  .sort_values("_s2", ascending=False, kind="stable")
                  .drop(columns=["_sira", "_s2"]))

    _dosyaya_yaz(yaklasan, EXCEL_YAKLASAN_DOSYASI, "Yaklaşan Maçlar")
    _dosyaya_yaz(tamamlanan, EXCEL_TAMAMLANAN_DOSYASI, "Tamamlanan Maçlar")


def _dosyaya_yaz(df: pd.DataFrame, dosya_adi: str, sayfa_adi: str):
    try:
        with pd.ExcelWriter(dosya_adi, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=sayfa_adi, index=False)
        print(f"[EXCEL] '{dosya_adi}' güncellendi ({len(df)} maç).")
    except PermissionError:
        print(f"[UYARI] [EXCEL] '{dosya_adi}' açık olabilir, güncellenemedi. "
              f"Dosyayı kapatıp scripti tekrar çalıştırın.")
"""
Excel'e Aktarma
---------------
Kullanım:
  python excel_aktar.py               -> veritabanındaki TÜM veriyi aktarır (oranlar_tumu.xlsx)
  python excel_aktar.py 27.09.2026    -> sadece o günün verisini aktarır (oranlar_27.09.2026.xlsx)

Sayfalar:
  Bülten          : her maç için ana oranlar (1 satır = 1 maç)
  Detay Oranlar   : her maç için tüm bahis türleri (1 satır = 1 oran)
  Oran Geçmişi    : oranların zaman içindeki değişimi

Oranlar Excel'de sayı olarak yazılır (virgül/nokta farkı düzeltilir).
Eksik/sunulmayan oranlar (0,00 veya -) boş hücre olur.
Bir sayfa 1.000.000 satırı geçerse otomatik olarak yeni sayfaya bölünür.
"""

import re
import sqlite3
import sys

import pandas as pd

DB_DOSYASI = "mackolik_oran.db"
SAYFA_SATIR_LIMITI = 1_000_000  # Excel sınırı 1.048.576

TARIH_ANAHTARI = "substr(b.tarih,7,4)||substr(b.tarih,4,2)||substr(b.tarih,1,2)"

BASLIKLAR = {
    "mac_id": "Maç ID", "tarih": "Tarih", "saat": "Saat", "lig_kodu": "Lig",
    "ev_sahibi": "Ev Sahibi", "misafir": "Misafir",
    "skor_ev": "Skor Ev", "skor_dep": "Skor Dep",
    "ms1": "MS 1", "msx": "MS X", "ms2": "MS 2",
    "cs_1x": "ÇŞ 1-X", "cs_12": "ÇŞ 1-2", "cs_x2": "ÇŞ X-2",
    "au25_alt": "2,5 Alt", "au25_ust": "2,5 Üst",
    "hnd_h": "Handikap h", "hnd_1": "Handikap 1", "hnd_x": "Handikap X", "hnd_2": "Handikap 2",
    "iy1": "İY 1", "iyx": "İY X", "iy2": "İY 2",
    "kg_var": "KG Var", "kg_yok": "KG Yok",
    "iy15_alt": "İY 1,5 Alt", "iy15_ust": "İY 1,5 Üst",
    "au15_alt": "1,5 Alt", "au15_ust": "1,5 Üst",
    "au35_alt": "3,5 Alt", "au35_ust": "3,5 Üst",
    "ilk_gorulme": "İlk Görülme", "son_guncelleme": "Son Güncelleme",
}

# Bültende oran olan sütunlar (handikap 'h' değeri bir oran değil, metin olarak kalır)
BULTEN_METIN_SUTUNLARI = {"mac_id", "tarih", "saat", "lig_kodu", "ev_sahibi", "misafir",
                          "skor_ev", "skor_dep", "hnd_h", "ilk_gorulme", "son_guncelleme"}


def oran_sayiya(seri):
    """'1,50' / '1.98' / '-' / '0,00' -> 1.5 / 1.98 / boş / boş"""
    sayi = pd.to_numeric(seri.astype(str).str.replace(",", ".", regex=False), errors="coerce")
    return sayi.where(sayi > 0)


def yerel_saate_cevir(seri):
    """Veritabanındaki UTC zamanı İstanbul saatine çevirir (Excel saat dilimi desteklemez)."""
    zaman = pd.to_datetime(seri, errors="coerce", utc=True)
    return zaman.dt.tz_convert("Europe/Istanbul").dt.tz_localize(None)


def parcali_yaz(writer, df, sayfa_adi):
    if df.empty:
        print(f"  - {sayfa_adi}: veri yok, sayfa oluşturulmadı.")
        return
    parca_sayisi = (len(df) - 1) // SAYFA_SATIR_LIMITI + 1
    for i in range(parca_sayisi):
        parca = df.iloc[i * SAYFA_SATIR_LIMITI:(i + 1) * SAYFA_SATIR_LIMITI]
        ad = sayfa_adi if parca_sayisi == 1 else f"{sayfa_adi} {i + 1}"
        parca.to_excel(writer, sheet_name=ad[:31], index=False)
    print(f"  - {sayfa_adi}: {len(df)} satır ({parca_sayisi} sayfa)")


def main():
    tarih = sys.argv[1] if len(sys.argv) > 1 else None
    if tarih and not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", tarih):
        print("Tarih 'GG.AA.YYYY' biçiminde olmalı, örn: python excel_aktar.py 27.09.2026")
        return

    excel_dosyasi = f"oranlar_{tarih}.xlsx" if tarih else "oranlar_tumu.xlsx"
    filtre = "WHERE b.tarih = ?" if tarih else ""
    parametre = (tarih,) if tarih else ()

    conn = sqlite3.connect(DB_DOSYASI, timeout=30)
    try:
        tablolar = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "bulten" not in tablolar:
            print("'bulten' tablosu yok. Önce canli_takip_v3.py dosyasını çalıştırın.")
            return

        # --- Bülten ---
        bulten = pd.read_sql_query(
            f"SELECT * FROM bulten b {filtre} ORDER BY {TARIH_ANAHTARI}, b.saat",
            conn, params=parametre)
        for sutun in bulten.columns:
            if sutun in ("ilk_gorulme", "son_guncelleme"):
                bulten[sutun] = yerel_saate_cevir(bulten[sutun])
            elif sutun not in BULTEN_METIN_SUTUNLARI:
                bulten[sutun] = oran_sayiya(bulten[sutun])
        bulten = bulten.rename(columns=BASLIKLAR)

        # --- Detay oranlar (uzun biçim: 1 satır = 1 oran) ---
        detay = pd.DataFrame()
        if "detay_oranlar" in tablolar:
            detay = pd.read_sql_query(f"""
                SELECT b.tarih AS "Tarih", b.saat AS "Saat",
                       b.ev_sahibi || ' - ' || b.misafir AS "Maç",
                       b.skor_ev || '-' || b.skor_dep AS "Skor",
                       d.market_kod AS "Market Kodu", d.bahis_turu AS "Bahis Türü",
                       d.secenek AS "Seçenek", d.oran AS "Oran",
                       d.guncelleme_tarihi AS "Son Güncelleme"
                FROM detay_oranlar d JOIN bulten b ON b.mac_id = d.mac_id
                {filtre}
                ORDER BY {TARIH_ANAHTARI}, b.saat, d.mac_id, d.market_kod
            """, conn, params=parametre)
            if not detay.empty:
                detay["Oran"] = oran_sayiya(detay["Oran"])
                detay["Son Güncelleme"] = yerel_saate_cevir(detay["Son Güncelleme"])

        # --- Oran geçmişi ---
        gecmis = pd.DataFrame()
        if "oran_gecmisi" in tablolar:
            gecmis = pd.read_sql_query(f"""
                SELECT b.tarih AS "Tarih", b.saat AS "Saat",
                       b.ev_sahibi || ' - ' || b.misafir AS "Maç",
                       g.kaynak AS "Kaynak", g.alan AS "Alan", g.oran AS "Oran",
                       g.zaman AS "Zaman"
                FROM oran_gecmisi g JOIN bulten b ON b.mac_id = g.mac_id
                {filtre}
                ORDER BY {TARIH_ANAHTARI}, b.saat, g.mac_id, g.id
            """, conn, params=parametre)
            if not gecmis.empty:
                gecmis["Alan"] = gecmis["Alan"].map(lambda a: BASLIKLAR.get(a, a.replace("|", " | ")))
                gecmis["Oran"] = oran_sayiya(gecmis["Oran"])
                gecmis["Zaman"] = yerel_saate_cevir(gecmis["Zaman"])
    finally:
        conn.close()

    if bulten.empty:
        print(f"{tarih or 'Veritabanı'} için bültende maç bulunamadı, Excel oluşturulmadı.")
        return

    print(f"'{excel_dosyasi}' yazılıyor...")
    try:
        with pd.ExcelWriter(excel_dosyasi, engine="openpyxl") as writer:
            parcali_yaz(writer, bulten, "Bülten")
            parcali_yaz(writer, detay, "Detay Oranlar")
            parcali_yaz(writer, gecmis, "Oran Geçmişi")
    except PermissionError:
        print(f"HATA: '{excel_dosyasi}' Excel'de açık olabilir. Dosyayı kapatıp tekrar deneyin.")
        return

    print(f"Tamamlandı: {excel_dosyasi}")


if __name__ == "__main__":
    main()

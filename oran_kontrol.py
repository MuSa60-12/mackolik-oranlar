"""
Oran Kontrol Aracı
------------------
Kullanım:
  python oran_kontrol.py                  -> özet + en son günün maçları
  python oran_kontrol.py galatasaray      -> takım adına göre maç ara
  python oran_kontrol.py 4444917          -> maç ID'sine göre oran hareketini göster
  python oran_kontrol.py 4444917 --detay  -> detaylı marketlerin (korner, kart...) hareketini de göster

canli_takip_v3.py çalışırken de kullanılabilir (ikinci bir terminalde).
"""

import sqlite3
import sys

DB_DOSYASI = "mackolik_oran.db"

# Tarih 'GG.AA.YYYY' metni olarak saklandığı için doğru sıralama anahtarı gerekir
TARIH_ANAHTARI = "substr(tarih,7,4)||substr(tarih,4,2)||substr(tarih,1,2)"

ADLAR = {
    "ms1": "MS 1", "msx": "MS X", "ms2": "MS 2",
    "cs_1x": "Cifte Sans 1-X", "cs_12": "Cifte Sans 1-2", "cs_x2": "Cifte Sans X-2",
    "au25_alt": "2,5 Alt", "au25_ust": "2,5 Ust",
    "hnd_h": "Handikap h", "hnd_1": "Handikap 1", "hnd_x": "Handikap X", "hnd_2": "Handikap 2",
    "iy1": "IY 1", "iyx": "IY X", "iy2": "IY 2",
    "kg_var": "KG Var", "kg_yok": "KG Yok",
    "iy15_alt": "IY 1,5 Alt", "iy15_ust": "IY 1,5 Ust",
    "au15_alt": "1,5 Alt", "au15_ust": "1,5 Ust",
    "au35_alt": "3,5 Alt", "au35_ust": "3,5 Ust",
}

_TR = str.maketrans("çÇğĞıİöÖşŞüÜ", "cCgGiIoOsSuU")


def normalize(metin):
    """Türkçe karakterleri sadeleştirip küçük harfe çevirir (arama için)."""
    return (metin or "").translate(_TR).lower()


def baglan():
    return sqlite3.connect(DB_DOSYASI, timeout=30)


def tablo_var_mi(conn, ad):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (ad,)).fetchone() is not None


def ozet(conn):
    if not tablo_var_mi(conn, "bulten"):
        print("Henüz 'bulten' tablosu yok. Önce canli_takip_v3.py dosyasını çalıştırın.")
        return

    n_bulten = conn.execute("SELECT COUNT(*) FROM bulten").fetchone()[0]
    n_detay = conn.execute("SELECT COUNT(*) FROM detay_oranlar").fetchone()[0] \
        if tablo_var_mi(conn, "detay_oranlar") else 0
    n_mac_detay = conn.execute("SELECT COUNT(DISTINCT mac_id) FROM detay_oranlar").fetchone()[0] \
        if tablo_var_mi(conn, "detay_oranlar") else 0
    n_gecmis = conn.execute("SELECT COUNT(*) FROM oran_gecmisi").fetchone()[0] \
        if tablo_var_mi(conn, "oran_gecmisi") else 0
    son = conn.execute("SELECT datetime(MAX(son_guncelleme),'localtime') FROM bulten").fetchone()[0]

    print("=== ÖZET ===")
    print(f"Bültendeki maç sayısı        : {n_bulten}")
    print(f"Detay oranı çekilen maç      : {n_mac_detay}  ({n_detay} market satırı)")
    print(f"Oran geçmişi kayıt sayısı    : {n_gecmis}")
    print(f"Bültenin son güncellenme     : {son}")

    gun = conn.execute(
        f"SELECT tarih FROM bulten ORDER BY {TARIH_ANAHTARI} DESC LIMIT 1").fetchone()
    if not gun:
        return
    gun = gun[0]
    satirlar = conn.execute(
        "SELECT saat, ev_sahibi, misafir, ms1, msx, ms2, au25_alt, au25_ust, kg_var, kg_yok, "
        "skor_ev, skor_dep FROM bulten WHERE tarih=? ORDER BY saat LIMIT 15", (gun,)).fetchall()

    print(f"\n=== {gun} - ilk {len(satirlar)} maç ===")
    print(f"{'Saat':<6}{'Ev':<20}{'Dep':<20}{'1':<7}{'X':<7}{'2':<7}"
          f"{'2.5A':<7}{'2.5U':<7}{'KGV':<7}{'KGY':<7}{'Skor':<6}")
    for r in satirlar:
        saat, ev, dep, ms1, msx, ms2, a, u, kv, ky, se, sd = r
        print(f"{str(saat):<6}{str(ev)[:19]:<20}{str(dep)[:19]:<20}{str(ms1):<7}{str(msx):<7}"
              f"{str(ms2):<7}{str(a):<7}{str(u):<7}{str(kv):<7}{str(ky):<7}{str(se)}-{str(sd)}")

    print("\nBir maçın oran hareketi için:  python oran_kontrol.py takim_adi")


def ara(conn, sorgu, detay):
    satirlar = conn.execute(
        f"SELECT mac_id, tarih, saat, ev_sahibi, misafir FROM bulten "
        f"ORDER BY {TARIH_ANAHTARI} DESC, saat").fetchall()
    n = normalize(sorgu)
    bulunan = [r for r in satirlar if n in normalize(r[3]) or n in normalize(r[4])]

    if not bulunan:
        print(f"'{sorgu}' ile eşleşen maç bulunamadı.")
        return
    if len(bulunan) == 1:
        hareket(conn, bulunan[0][0], detay)
        return

    print(f"'{sorgu}' ile {len(bulunan)} maç eşleşti (en yeniden eskiye):\n")
    for mac_id, tarih, saat, ev, dep in bulunan[:30]:
        print(f"  {mac_id:<10} {tarih} {saat}  {ev} - {dep}")
    if len(bulunan) > 30:
        print(f"  ... ve {len(bulunan) - 30} maç daha")
    print("\nİstediğiniz maçın ID'siyle tekrar çalıştırın, örn:  python oran_kontrol.py "
          f"{bulunan[0][0]}")


def _gruplari_al(conn, mac_id, kaynak):
    satirlar = conn.execute(
        "SELECT alan, oran, datetime(zaman,'localtime') FROM oran_gecmisi "
        "WHERE mac_id=? AND kaynak=? ORDER BY id", (mac_id, kaynak)).fetchall()
    gruplar = {}
    for alan, oran, zaman in satirlar:
        gruplar.setdefault(alan, []).append((oran, zaman))
    return gruplar


def _zincir(kayitlar):
    # zaman 'YYYY-AA-GG SS:DD:ss' -> 'AA-GG SS:DD'
    return " -> ".join(f"{oran} ({zaman[5:16]})" for oran, zaman in kayitlar)


def hareket(conn, mac_id, detay):
    m = conn.execute(
        "SELECT tarih, saat, ev_sahibi, misafir, ms1, msx, ms2, au25_alt, au25_ust, "
        "kg_var, kg_yok, skor_ev, skor_dep FROM bulten WHERE mac_id=?", (mac_id,)).fetchone()
    if not m:
        print(f"{mac_id} numaralı maç bulunamadı.")
        return

    tarih, saat, ev, dep, ms1, msx, ms2, a, u, kv, ky, se, sd = m
    print(f"=== {ev} - {dep}  ({tarih} {saat})  [ID: {mac_id}] ===")
    print(f"Şu anki oranlar: MS {ms1} / {msx} / {ms2}   2,5 A/Ü {a} / {u}   KG V/Y {kv} / {ky}   Skor {se}-{sd}")

    if not tablo_var_mi(conn, "oran_gecmisi"):
        print("Oran geçmişi tablosu yok. canli_takip_v3.py dosyasını çalıştırın.")
        return

    print("\n--- Ana oranlardaki değişimler (bülten) ---")
    gruplar = _gruplari_al(conn, mac_id, "bulten")
    if not gruplar:
        print("Bu maç için geçmiş kaydı yok.")
    else:
        degisenler = {a_: v for a_, v in gruplar.items() if len(v) > 1}
        if not degisenler:
            ilk_zaman = next(iter(gruplar.values()))[0][1]
            print(f"Henüz değişim yok (takip başlangıcı: {ilk_zaman[5:16]}).")
        else:
            for alan in ADLAR:
                if alan in degisenler:
                    print(f"{ADLAR[alan]:<16}: {_zincir(degisenler[alan])}")

    if tablo_var_mi(conn, "detay_oranlar"):
        n_market = conn.execute(
            "SELECT COUNT(*) FROM detay_oranlar WHERE mac_id=?", (mac_id,)).fetchone()[0]
        detay_gruplar = _gruplari_al(conn, mac_id, "detay")
        degisen_detay = {a_: v for a_, v in detay_gruplar.items() if len(v) > 1}
        print(f"\n--- Detaylı marketler: {n_market} oran takipte, {len(degisen_detay)} tanesi değişti ---")
        if detay and degisen_detay:
            for alan in sorted(degisen_detay):
                _kod, tur, secenek = alan.split("|", 2)
                print(f"{tur} [{secenek}]: {_zincir(degisen_detay[alan])}")
        elif degisen_detay:
            print("Değişenleri görmek için komuta --detay ekleyin.")


def main():
    argumanlar = [a for a in sys.argv[1:] if not a.startswith("--")]
    detay = "--detay" in sys.argv

    conn = baglan()
    try:
        if not argumanlar:
            ozet(conn)
        elif argumanlar[0].isdigit():
            hareket(conn, int(argumanlar[0]), detay)
        else:
            ara(conn, " ".join(argumanlar), detay)
    except sqlite3.OperationalError as e:
        print(f"Veritabanı hatası: {e}")
        print("canli_takip_v3.py en az bir kez çalıştırılmış mı? Klasör doğru mu?")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

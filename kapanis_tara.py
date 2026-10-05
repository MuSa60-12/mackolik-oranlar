"""
Kapanış Oranları Tarayıcı
-------------------------
Açılışı kaydedilmiş ama başlamasına PENCERE_MIN-PENCERE_MAX dakika kalmış ve
henüz kapanışı alınmamış maçları bulur, SADECE onların güncel oranlarını çekip
"kapanış" olarak kaydeder. Bulacak maç yoksa hiçbir şey yapmadan çıkar.

Bu script KISA SÜRELİ çalışır ve biter (sürekli döngü YOKTUR). Otomatik olması
için Windows Görev Zamanlayıcı'ya her 5-10 dakikada bir çalışacak şekilde
eklenmesi gerekir (kurulum adımları sohbette anlatıldı).
"""

from datetime import datetime

import mackolik_ortak as ort

PENCERE_MIN_DK = 10   # maça en az bu kadar dakika kalmış olmalı
PENCERE_MAX_DK = 20   # maça en fazla bu kadar dakika kalmış olmalı


def main():
    ort.veritabani_hazirla()
    yaklasanlar = ort.kapanissiz_yaklasan_maclari_getir(PENCERE_MIN_DK, PENCERE_MAX_DK)

    if not yaklasanlar:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Kapanış penceresinde maç yok, çıkılıyor.")
        return

    print(f"[{datetime.now().strftime('%H:%M:%S')}] {len(yaklasanlar)} maç kapanış penceresinde:")
    for m in yaklasanlar:
        print(f"    {m['tarih']} {m['saat']}  {m['ev_sahibi']} - {m['misafir']}")

    # Aynı günün bültenini bir kez çekip içinden ilgili maçları süzüyoruz (tasarruflu)
    gerekli_gunler = {m["tarih"] for m in yaklasanlar}
    hedef_id_seti = {m["mac_id"] for m in yaklasanlar}

    kapanis_kayitlari = []
    for gun_str in gerekli_gunler:
        try:
            gunun_kayitlari = ort.gunun_programini_cek(gun_str)
        except Exception as e:
            print(f"[HATA] {gun_str} çekilemedi: {e}")
            continue
        kapanis_kayitlari.extend(k for k in gunun_kayitlari if k["mac_id"] in hedef_id_seti)

    eklenen = ort.kayitlari_kaydet(kapanis_kayitlari, "kapanis")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {eklenen} maçın kapanışı kaydedildi.")

    ort.excele_aktar()


if __name__ == "__main__":
    main()

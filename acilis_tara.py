"""
Açılış Oranları Tarayıcı
------------------------
Ulaşılabilen günleri (bugün + GUN_SAYISI-1 gün ileri) tarar. Daha önce hiç
görülmemiş her maç için o anki oranları "açılış" olarak veritabanına kaydeder.
Zaten açılışı kaydedilmiş bir maça ASLA tekrar dokunmaz.

Ne zaman çalıştırılır: günde bir kez yeterli (yeni yayınlanan maçları yakalamak
için). Elle çalıştırabilir ya da Windows Görev Zamanlayıcı'ya günde 1 kez
eklenebilir.
"""

from datetime import datetime, timedelta

import mackolik_ortak as ort

GUN_SAYISI = 7  # bugünden itibaren kaç gün ileriye bakılsın


def main():
    ort.veritabani_hazirla()
    toplam_eklenen = 0
    toplam_gorulen = 0

    for i in range(GUN_SAYISI):
        gun = datetime.now() + timedelta(days=i)
        gun_str = gun.strftime("%d.%m.%Y")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {gun_str} taranıyor...")
        try:
            kayitlar = ort.gunun_programini_cek(gun_str)
        except Exception as e:
            print(f"[HATA] {gun_str} çekilemedi: {e}")
            continue

        eklenen = ort.kayitlari_kaydet(kayitlar, "acilis")
        toplam_gorulen += len(kayitlar)
        toplam_eklenen += eklenen
        print(f"    {len(kayitlar)} maç görüldü, {eklenen} tanesi YENİ (açılış kaydedildi).")

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Tamamlandı. "
          f"Toplam {toplam_gorulen} maç görüldü, {toplam_eklenen} yeni açılış kaydı eklendi.")

    ort.excele_aktar()


if __name__ == "__main__":
    main()

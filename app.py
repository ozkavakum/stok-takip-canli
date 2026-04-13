from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
import pymysql
from datetime import datetime
import json
import pandas as pd
import io
import base64

app = Flask(__name__)
app.secret_key = "stok_takip_gizli_anahtar"


# --- VERİTABANI BAĞLANTISI ---
def get_db_connection():
    try:
        connection = pymysql.connect(
            host='mysql-baa3831-ozkavakumfinans-7da4.l.aivencloud.com',
            user='avnadmin',
            password=r'AVNS_AMj2EWle4W9yxJCGfAi', # Şifreni buraya yaz
            database='defaultdb',
            port=13396, # Portu eklemeyi unutma
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            ssl={'ssl': {}} # Aiven için SSL bağlantısını zorunlu kılar
        )
        return connection
    except Exception as e:
        print(f"BAĞLANTI HATASI DETAYI: {e}")
        return None

# --- TABLO OLUŞTURMA KODU (PROGRAM AÇILDIĞINDA ÇALIŞIR) ---
conn = get_db_connection()
if conn:
    try:
        with conn.cursor() as cursor:
            # Senin index fonksiyonun 'stoklar' tablosunu istediği için onu oluşturuyoruz
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stoklar (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    urun_adi VARCHAR(255) NOT NULL,
                    miktar INT DEFAULT 0,
                    birim VARCHAR(50)
                )
            """)
        print(">>> TABLO KONTROLÜ BAŞARILI: 'stoklar' tablosu hazır.")
    finally:
        conn.close()
# -------------------------------------------------------

# --- YARDIMCI FONKSİYONLAR ---
def generate_order_no(cursor):
    current_year = datetime.now().year
    prefix = f"SP-{current_year}-"
    cursor.execute("SELECT siparis_no FROM siparisler WHERE siparis_no LIKE %s ORDER BY id DESC LIMIT 1", (prefix + '%',))
    last_record = cursor.fetchone()
    if last_record and last_record['siparis_no']:
        try:
            last_num = int(last_record['siparis_no'].split('-')[-1])
            new_num = last_num + 1
        except: new_num = 1
    else: new_num = 1
    return f"{prefix}{new_num:04d}"


def format_currency_tl(value):
    try:
        num = float(value)
    except (TypeError, ValueError):
        return value if value is not None else ""
    formatted = "{:,.2f}".format(num)
    return formatted.replace(',', 'X').replace('.', ',').replace('X', '.')

app.jinja_env.filters['format_tl'] = format_currency_tl


# --- GİRİŞ / ÇIKIŞ ---
@app.route('/')
def index():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    return render_template('login.html')



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_input = request.form.get('username')
        password_input = request.form.get('password')
        db = get_db_connection()
        if not db: return "DB Bağlantı Hatası"
        cursor = db.cursor()
        cursor.execute("SELECT * FROM kullanicilar WHERE kullanici_adi = %s", (username_input,))
        user = cursor.fetchone()
        db.close()
        if user and user['sifre'] == password_input:
            session.clear()
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['user_name'] = user.get('kullanici_adi', 'Kullanıcı')
            session['user_role'] = user.get('rol', 'Personel')
            session['user_permissions'] = {
                'siparis': user.get('yetki_siparis', 0),
                'isemri': user.get('yetki_isemri', 0),
                'uretim': user.get('yetki_uretim', 0),
                'yukleme': user.get('yetki_yukleme', 0),
                'sevkiyat': user.get('yetki_sevkiyat', 0),
                'depo': user.get('yetki_depo', 0),
                'musteri': user.get('yetki_musteri', 0),
                'urun': user.get('yetki_urun', 0),
                'personel': user.get('yetki_personel', 0),
                'operator': user.get('yetki_operator', 0)
            }
            flash("Giriş başarılı.", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Kullanıcı adı veya şifre hatalı!", "danger")
    return render_template('login.html')



@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))






# --- DASHBOARD ---
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    db = get_db_connection()
    if not db: return "Veritabanı bağlantısı kurulamadı."
    
    cursor = db.cursor()
    kritik_urunler = []
    try:
        # Veritabanında stok sütununun adını dinamik olarak buluyoruz
        cursor.execute("DESCRIBE urunler")
        columns = [row['Field'] for row in cursor.fetchall()]
        
        stok_col = None
        for col in ['stok_miktari', 'stok', 'miktar', 'toplam_stok', 'adet']:
            if col in columns:
                stok_col = col
                break
        
        if stok_col:
            query = f"SELECT urun_adi, {stok_col} AS stok_miktari FROM urunler WHERE {stok_col} < 100 ORDER BY {stok_col} ASC"
            cursor.execute(query)
            kritik_urunler = cursor.fetchall()
            
    except Exception as e:
        print(f"Kritik stok sorgulama hatası: {e}")
    finally:
        db.close()
        
    return render_template('dashboard.html', kritik_urunler=kritik_urunler)

# --- MOBIL BARKOD TARAMA ---
@app.route('/mobil_barkod')
def mobil_barkod():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('mobil_barkod.html')

# --- KULLANICI YÖNETİMİ ---
@app.route('/kullanicilar')
def kullanicilar():
    if session.get('user_role') != 'Admin': 
        flash("Bu sayfaya sadece Admin erişebilir.", "danger")
        return redirect(url_for('dashboard'))
    
    db = get_db_connection()
    if not db: return "Veritabanı bağlantı hatası"
    
    cursor = db.cursor()
    cursor.execute("SELECT * FROM kullanicilar ORDER BY id DESC")
    users = cursor.fetchall()
    db.close()
    return render_template('kullanicilar.html', users=users)

@app.route('/kullanici_ekle', methods=['POST'])
def kullanici_ekle():
    if session.get('user_role') != 'Admin': return "Yetkisiz Erişim", 403
        
    ad_soyad = request.form.get('ad_soyad')
    k_adi = request.form.get('kadi')
    sifre = request.form.get('sifre')
    rol = request.form.get('rol')
    
    db = get_db_connection()
    cursor = db.cursor()
    try:
        # VALUES kısmındaki eksik %s'ler tamamlandı (10 adet yetki sütunu için 10 tane %s)
        cursor.execute("""
            INSERT INTO kullanicilar (
                ad_soyad, kullanici_adi, sifre, rol,
                yetki_siparis, yetki_isemri, yetki_uretim, yetki_yukleme, yetki_sevkiyat,
                yetki_depo, yetki_musteri, yetki_urun, yetki_personel, yetki_operator
            ) VALUES (%s, %s, %s, %s, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        """, (ad_soyad, k_adi, sifre, rol))
        db.commit()
        flash(f"{ad_soyad} kullanıcısı sıfır yetkiyle oluşturuldu.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Hata: {str(e)}", "danger")
    finally:
        db.close()
    return redirect(url_for('kullanicilar'))

@app.route('/yetki_guncelle', methods=['POST'])
def yetki_guncelle():
    if session.get('user_role') != 'Admin':
        flash("Bu işlem için Admin yetkisi gerekiyor.", "danger")
        return redirect(url_for('index'))
    
    uid = request.form.get('user_id')
    # Select'ten gelen 0-4 arası sayısal değerleri doğru okuyoruz
    yetkiler = (
        int(request.form.get('yetki_siparis') or 0),
        int(request.form.get('yetki_isemri') or 0),
        int(request.form.get('yetki_uretim') or 0),
        int(request.form.get('yetki_yukleme') or 0),
        int(request.form.get('yetki_sevkiyat') or 0),
        int(request.form.get('yetki_depo') or 0),
        int(request.form.get('yetki_musteri') or 0),
        int(request.form.get('yetki_urun') or 0),
        int(request.form.get('yetki_personel') or 0),
        int(request.form.get('yetki_operator') or 0),
        uid
    )

    db = get_db_connection()
    cursor = db.cursor()
    try:
        sql = """UPDATE kullanicilar SET 
                 yetki_siparis = %s, yetki_isemri = %s, yetki_uretim = %s, 
                 yetki_yukleme = %s, yetki_sevkiyat = %s, yetki_depo = %s, 
                 yetki_musteri = %s, yetki_urun = %s, yetki_personel = %s, yetki_operator = %s 
                 WHERE id = %s"""
        cursor.execute(sql, yetkiler)
        db.commit()
        flash("Kullanıcı yetkileri başarıyla güncellendi.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Güncelleme Hatası: {str(e)}", "danger")
    finally:
        db.close()
    return redirect(url_for('kullanicilar'))

@app.route('/kullanici_sil/<int:id>')
def kullanici_sil(id):
    if session.get('user_role') != 'Admin': return "Yetkisiz İşlem", 403
    if id == session.get('user_id'):
        flash("Kendi kullanıcı hesabınızı silemezsiniz!", "danger")
        return redirect(url_for('kullanicilar'))

    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM kullanicilar WHERE id = %s", (id,))
        db.commit()
        flash("Kullanıcı sistemden silindi.", "warning")
    except Exception as e:
        db.rollback()
        flash(f"Silme Hatası: {str(e)}", "danger")
    finally:
        db.close()
    return redirect(url_for('kullanicilar'))



# --- SİPARİŞLER ---
@app.route('/siparisler')
def siparisler():
    if 'user_id' not in session: 
        return redirect(url_for('index'))
    
    perms = session.get('user_permissions', {})
    if session.get('user_role') != 'Admin' and int(perms.get('siparis', 0)) < 1:
        flash("Bu sayfaya erişim yetkiniz yok!", "danger")
        return redirect(url_for('dashboard'))
    
    db = get_db_connection()
    if not db:
        flash("Veritabanı bağlantı hatası!", "danger")
        return redirect(url_for('dashboard'))
        
    cursor = db.cursor()
    try:
        # Siparişleri getir
        cursor.execute("SELECT s.*, m.musteri_adi FROM siparisler s JOIN musteriler m ON s.musteri_id = m.id ORDER BY s.id DESC")
        ana_siparisler = cursor.fetchall()
        order_ids = [s['id'] for s in ana_siparisler]

        is_emirleri = []
        if order_ids:
            placeholders = ','.join(['%s'] * len(order_ids))
            cursor.execute(f"SELECT * FROM is_emirleri WHERE siparis_id IN ({placeholders})", order_ids)
            is_emirleri = cursor.fetchall()

        is_emir_map = {}
        for ie in is_emirleri:
            key = (ie['siparis_id'], ie['urun_id'])
            is_emir_map.setdefault(key, []).append(ie)

        product_ids = set()
        
        for s in ana_siparisler:
            # Tarih formatlama (PyMySQL'den gelen date nesnesini stringe çevirir)
            if s.get('teslim_tarihi') and hasattr(s['teslim_tarihi'], 'strftime'):
                s['teslim_tarihi'] = s['teslim_tarihi'].strftime('%Y-%m-%d')
            
            # Her siparişin detayını (ürünlerini) getir
            cursor.execute("""
                SELECT sd.*, u.urun_adi 
                FROM siparis_detay sd 
                JOIN urunler u ON sd.urun_id = u.id 
                WHERE sd.siparis_id = %s""", (s['id'],))
            s['detaylar'] = cursor.fetchall()
            for detay in s['detaylar']:
                product_ids.add(detay['urun_id'])

        stock_map = {}
        if product_ids:
            placeholders = ','.join(['%s'] * len(product_ids))
            cursor.execute(f"SELECT id, paket_ici_adet FROM urunler WHERE id IN ({placeholders})", list(product_ids))
            paket_ici_map = {row['id']: int(row['paket_ici_adet'] or 0) for row in cursor.fetchall()}

            for pid in product_ids:
                cursor.execute("SELECT paket_sayisi FROM sayimlar WHERE urun_id = %s ORDER BY id DESC LIMIT 1", (pid,))
                s_res = cursor.fetchone()
                sayim = int(s_res['paket_sayisi']) if s_res and s_res['paket_sayisi'] is not None else 0

                cursor.execute("SELECT SUM(paket_sayisi) as toplam FROM uretimler WHERE urun_id = %s", (pid,))
                ur_res = cursor.fetchone()
                uretim = int(ur_res['toplam']) if ur_res and ur_res['toplam'] is not None else 0

                cursor.execute("SELECT SUM(paket) as toplam FROM sevkiyat_detaylari WHERE urun_id = %s", (pid,))
                sv_res = cursor.fetchone()
                sevk = int(sv_res['toplam']) if sv_res and sv_res['toplam'] is not None else 0

                paket_ici = paket_ici_map.get(pid, 0)
                kalan_paket = max(sayim + uretim - sevk, 0)
                stock_map[pid] = kalan_paket * paket_ici

        total_demand = {}
        for s in ana_siparisler:
            for detay in s['detaylar']:
                urun_id = detay['urun_id']
                total_demand[urun_id] = total_demand.get(urun_id, 0) + int(detay.get('miktar') or 0)

        for s in ana_siparisler:
            all_green = True
            any_production = False
            for detay in s['detaylar']:
                urun_id = detay['urun_id']
                stock = stock_map.get(urun_id, 0)

                # Sevkiyat bilgilerini getir - bu müşteri+ürün kombinasyonu için toplam sevkiyat
                musteri_id = s['musteri_id']
                cursor.execute("""
                    SELECT COALESCE(SUM(paket * paket_ici), 0) as toplam_gonderilen
                    FROM sevkiyat_detaylari 
                    WHERE urun_id = %s AND musteri_id = %s
                """, (urun_id, musteri_id))
                sev_res = cursor.fetchone()
                toplam_gonderilen = int(sev_res['toplam_gonderilen']) if sev_res else 0
                
                detay['siparis_miktari'] = int(detay.get('miktar') or 0)
                detay['gonderilen_miktari'] = toplam_gonderilen
                detay['kalan_miktari'] = max(detay['siparis_miktari'] - toplam_gonderilen, 0)

                if stock <= 0:
                    detay['stok_uyari'] = 'Yok'
                    detay['stok_renk'] = 'danger'
                    all_green = False
                elif total_demand.get(urun_id, 0) > stock:
                    detay['stok_uyari'] = 'Eksik'
                    detay['stok_renk'] = 'warning'
                    all_green = False
                else:
                    detay['stok_uyari'] = 'Tamam'
                    detay['stok_renk'] = 'success'

                emirs = is_emir_map.get((s['id'], urun_id), [])
                if emirs:
                    if any(emir.get('durum') == 'Üretimde' for emir in emirs):
                        detay['durum_aciklama'] = 'Üretiliyor'
                        detay['durum_renk'] = 'info'
                        any_production = True
                    else:
                        detay['durum_aciklama'] = 'İş emri açıldı'
                        detay['durum_renk'] = 'secondary'
                else:
                    detay['durum_aciklama'] = None

                detay['stok_kalan_adet'] = stock

            if any_production:
                s['siparis_uretim_durumu'] = 'Üretiliyor'
                s['siparis_uretim_renk'] = 'info'
            elif all_green and s['detaylar']:
                s['siparis_uretim_durumu'] = 'Üretildi'
                s['siparis_uretim_renk'] = 'success'
            else:
                s['siparis_uretim_durumu'] = None
                s['siparis_uretim_renk'] = None

            s['siparis_toplami'] = round(sum(
                float(detay.get('miktar') or 0) * float(detay.get('birim_fiyat') or 0)
                for detay in s['detaylar']
            ), 2)

        # Modal formlar için müşteri ve ürün listelerini getir
        cursor.execute("SELECT id, musteri_adi FROM musteriler ORDER BY musteri_adi ASC")
        m_liste = cursor.fetchall()
        
        cursor.execute("SELECT id, urun_adi, paket_ici_adet FROM urunler ORDER BY urun_adi ASC")
        u_liste = cursor.fetchall()
        
    finally:
        db.close() 

    return render_template('siparisler.html', siparisler=ana_siparisler, musteriler=m_liste, urunler=u_liste)

# --- ÜRÜN STOK BİLGİSİNİ GETİREN API ---
@app.route('/get_urun_stok/<int:urun_id>')
def get_urun_stok(urun_id):
    if 'user_id' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db_connection()
    if not db: return jsonify({'error': 'DB Connection Error'}), 500
    cursor = db.cursor()
    try:
        # 1. Son Sayım Miktarı
        cursor.execute("SELECT paket_sayisi FROM sayimlar WHERE urun_id = %s ORDER BY id DESC LIMIT 1", (urun_id,))
        s_res = cursor.fetchone()
        sayim = s_res['paket_sayisi'] if s_res else 0

        # 2. Toplam Üretim
        cursor.execute("SELECT SUM(miktar) as toplam FROM uretim WHERE urun_id = %s", (urun_id,))
        ur_res = cursor.fetchone()
        uretim = ur_res['toplam'] if ur_res and ur_res['toplam'] else 0

        # 3. Toplam Sevkiyat
        # Not: paket_takip tablosundaki 'durum = 1' olan (sevk edilmiş) paketleri sayıyoruz
        cursor.execute("""
            SELECT COUNT(*) as toplam FROM paket_takip pt 
            JOIN uretim u ON pt.uretim_id = u.id 
            WHERE u.urun_id = %s AND pt.durum = 1
        """, (urun_id,))
        sv_res = cursor.fetchone()
        sevkiyat = sv_res['toplam'] if sv_res and sv_res['toplam'] else 0

        stok = (sayim + uretim) - sevkiyat
        # Ürünün paket içi adet'ini de döndür
        cursor.execute("SELECT paket_ici_adet FROM urunler WHERE id = %s", (urun_id,))
        p_res = cursor.fetchone()
        paket_ici = p_res['paket_ici_adet'] if p_res else 1
        return jsonify({'stok': int(stok), 'paket_ici_adet': paket_ici})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/siparis_ekle', methods=['POST'])
def siparis_ekle():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    db = get_db_connection()
    cursor = db.cursor()
    try:
        yeni_sip_no = generate_order_no(cursor)
        cursor.execute("""
            INSERT INTO siparisler (siparis_no, musteri_id, teslim_tarihi, siparis_notu, ekleyen_kullanici, durum) 
            VALUES (%s, %s, %s, %s, %s, 'Bekliyor')
        """, (yeni_sip_no, request.form.get('musteri_id'), request.form.get('teslim_tarihi'), 
              request.form.get('notlar'), session.get('user_name')))
        
        sip_id = cursor.lastrowid
        uids = request.form.getlist('urun_id[]')
        pkts = request.form.getlist('paket_sayisi[]')
        icis = request.form.getlist('paket_ici_adet[]')
        adets = request.form.getlist('adet[]') # Toplam miktar
        fiyats = request.form.getlist('birim_fiyat[]')
        
        for i in range(len(uids)):
            if uids[i] and uids[i] != "":
                cursor.execute("""
                    INSERT INTO siparis_detay (siparis_id, urun_id, paket_sayisi, paket_ici_adet, miktar, birim_fiyat) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (sip_id, uids[i], pkts[i], icis[i] if i < len(icis) else 0, adets[i], fiyats[i]))
        
        db.commit()
        flash(f"{yeni_sip_no} nolu sipariş başarıyla oluşturuldu.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Hata: {str(e)}", "danger")
    finally:
        db.close()
    return redirect(url_for('siparisler'))

# (Guncelleme, Durum ve Silme işlemleri mevcut yapısıyla stabil çalışacaktır)



@app.route('/siparis_guncelle', methods=['POST'])
def siparis_guncelle():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    sip_id = request.form.get('siparis_id')
    db = get_db_connection()
    if not db: return "DB Bağlantı Hatası"
    
    cursor = db.cursor()
    try:
        # Ana sipariş bilgilerini güncelle
        cursor.execute("""
            UPDATE siparisler 
            SET musteri_id=%s, teslim_tarihi=%s, siparis_notu=%s, guncelleyen_kullanici=%s 
            WHERE id=%s
        """, (request.form.get('musteri_id'), request.form.get('teslim_tarihi'), 
              request.form.get('notlar'), session.get('user_name'), sip_id))
        
        # Eski detayları silip yenilerini ekleyelim (Sipariş detay yönetimi için en temiz yöntemdir)
        cursor.execute("DELETE FROM siparis_detay WHERE siparis_id=%s", (sip_id,))
        
        uids = request.form.getlist('urun_id[]')
        pkts = request.form.getlist('paket_sayisi[]')
        icis = request.form.getlist('paket_ici_adet[]')
        adets = request.form.getlist('adet[]')
        fiyats = request.form.getlist('birim_fiyat[]')
        
        for i in range(len(uids)):
            if uids[i] and uids[i] != "":
                # HATA ÇÖZÜMÜ: Boş gelen sayısal değerleri 0'a çeviriyoruz
                p_sayisi = pkts[i] if pkts[i] != "" else 0
                p_ici = icis[i] if icis[i] != "" else 0
                m_miktar = adets[i] if adets[i] != "" else 0
                b_fiyat = fiyats[i] if fiyats[i] != "" else 0
                
                cursor.execute("""
                    INSERT INTO siparis_detay (siparis_id, urun_id, paket_sayisi, paket_ici_adet, miktar, birim_fiyat) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (sip_id, uids[i], p_sayisi, p_ici, m_miktar, b_fiyat))
                
        db.commit()
        flash("Sipariş ve ürün detayları başarıyla güncellendi.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Güncelleme Hatası: {str(e)}", "danger")
    finally:
        db.close()
    return redirect(url_for('siparisler'))



@app.route('/siparis_durum_guncelle/<int:id>', methods=['POST'])
def siparis_durum_guncelle(id):
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("UPDATE siparisler SET durum = %s WHERE id = %s", (request.form.get('durum'), id))
    db.commit()
    db.close()
    return redirect(url_for('siparisler'))

@app.route('/siparis_sil/<int:id>')
def siparis_sil(id):
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("DELETE FROM siparis_detay WHERE siparis_id=%s", (id,))
    cursor.execute("DELETE FROM siparisler WHERE id=%s", (id,))
    db.commit()
    db.close()
    flash("Sipariş silindi.", "warning")
    return redirect(url_for('siparisler'))


# --- İŞ EMİRLERİ LİSTESİ ---
@app.route('/is_emirleri')
def is_emirleri():
    # ADIM 1: OTURUM VE YETKİ KONTROLÜ (EN BAŞTA)
    if 'user_id' not in session: 
        return redirect(url_for('index'))
    
    perms = session.get('user_permissions', {})
    if session.get('user_role') != 'Admin' and int(perms.get('isemri', 0)) < 1:
        flash("İş emirlerini görme yetkiniz yok!")
        return redirect(url_for('dashboard'))

    # ADIM 2: VERİTABANI İŞLEMLERİ
    db = get_db_connection()
    if not db:
        flash("Veritabanı bağlantı hatası!")
        return redirect(url_for('dashboard'))
        
    cursor = db.cursor()
    
    try:
        # İş emirlerini getir
        cursor.execute("""
            SELECT ie.*, s.siparis_no, u.urun_adi 
            FROM is_emirleri ie
            LEFT JOIN siparisler s ON ie.siparis_id = s.id
            LEFT JOIN urunler u ON ie.urun_id = u.id
            ORDER BY ie.id DESC
        """)
        emirler = cursor.fetchall()
        
        # Seçim listeleri
        cursor.execute("SELECT id, siparis_no FROM siparisler WHERE durum != 'Tamamlandı'")
        siparisler_liste = cursor.fetchall()

        cursor.execute("SELECT id, urun_adi FROM urunler")
        urunler_liste = cursor.fetchall()
    finally:
        db.close() # Hata olsa bile bağlantıyı kapatır
    
    return render_template('is_emirleri.html', 
                           emirler=emirler, 
                           siparisler=siparisler_liste, 
                           urunler=urunler_liste, 
                           now=datetime.now().strftime('%Y-%m-%d'))

# --- SİPARİŞE GÖRE ÜRÜNLERİ GETİREN API ---
@app.route('/get_siparis_urunler/<int:siparis_id>')
def get_siparis_urunler(siparis_id):
    db = get_db_connection()
    if not db:
        return json.dumps([])
    
    # dictionary=True: JavaScript'in u.urun_adi şeklinde okuyabilmesi için ŞART.
    cursor = db.cursor()
    
    # Not: Tablo isimlerinizi (siparis_detaylari, urunler) veritabanınıza göre kontrol edin.
    query = """
        SELECT 
            u.id, 
            u.urun_adi, 
            sd.miktar as siparis_adet,
            sd.paket_sayisi,
            sd.paket_ici_adet
        FROM siparis_detay sd
        INNER JOIN urunler u ON sd.urun_id = u.id
        WHERE sd.siparis_id = %s
    """
    try:
        cursor.execute(query, (siparis_id,))
        urunler = cursor.fetchall()
        print(f"Sipariş {siparis_id} için bulunan ürünler: {urunler}") # Terminalden kontrol için
        return json.dumps(urunler)
    except Exception as e:
        print(f"Veritabanı Hatası: {e}")
        return json.dumps([])
    finally:
        db.close()

# --- İŞ EMRİ EKLEME (YENİ SÜTUNLARLA) ---
@app.route('/is_emri_ekle', methods=['POST'])
def is_emri_ekle():
    if 'user_id' not in session: return redirect(url_for('index'))

    perms = session.get('user_permissions', {})
    if session.get('user_role') != 'Admin' and int(perms.get('isemri', 0)) < 2:
        flash("İş emri ekleme yetkiniz yok!")
        return redirect(url_for('is_emirleri')) # Yetki yoksa burada kes

    db = get_db_connection()
    cursor = db.cursor()
    try:
        is_emri_no = f"IE-{datetime.now().strftime('%y%m%d%H%M%S')}"
        
        # Form verilerini alırken yeni isimleri kullanıyoruz
        siparis_id = request.form.get('siparis_id') or None
        urun_id = request.form.get('urun_id')
        paket_sayisi = request.form.get('paket_sayisi') or 0
        paket_ici_adet = request.form.get('paket_ici_adet') or 0
        toplam_adet = request.form.get('miktar') or 0
        makine = request.form.get('makine')
        tarih = request.form.get('tarih')
        notlar = request.form.get('notlar')

        sql = """INSERT INTO is_emirleri 
             (is_emri_no, siparis_id, urun_id, planlanan_miktar, makine_no, 
              baslangic_tarihi, durum, paket_sayisi, paket_ici_adet, toplam_adet, notlar, ekleyen_kullanici) 
             VALUES (%s, %s, %s, %s, %s, %s, 'Bekliyor', %s, %s, %s, %s, %s)"""
        
        cursor.execute(sql, (is_emri_no, siparis_id, urun_id, toplam_adet, makine, 
                     tarih, paket_sayisi, paket_ici_adet, toplam_adet, notlar, session.get('user_name')))
        db.commit()
        flash("İş emri oluşturuldu.")
    except Exception as e:
        db.rollback()
        flash(f"Hata: {str(e)}")
    finally:
        db.close()
    return redirect(url_for('is_emirleri'))


@app.route('/is_emri_guncelle', methods=['POST'])
def is_emri_guncelle():
    yetki = session.get('user_permissions', {}).get('isemri', 0)
    if session.get('user_role') != 'Admin' and int(yetki) < 3:
        flash("Bu işlem için yetkiniz yok!")
        return redirect(url_for('is_emirleri'))

    db = get_db_connection()
    cursor = db.cursor()
    try:
        ie_id = request.form.get('is_emri_id')
        urun_id = request.form.get('urun_id')
        durum = request.form.get('durum')
        makine = request.form.get('makine')
        
        # Yeni eklenen paket bilgileri
        paket_sayisi = request.form.get('paket_sayisi') or 0
        paket_ici_adet = request.form.get('paket_ici_adet') or 0
        # Toplam adet genelde (paket * paket_ici) olarak hesaplanır
        toplam_adet = int(paket_sayisi) * int(paket_ici_adet)

        sql = """UPDATE is_emirleri SET 
                 urun_id = %s, 
                 durum = %s, 
                 planlanan_miktar = %s, 
                 toplam_adet = %s, 
                 paket_sayisi = %s, 
                 paket_ici_adet = %s, 
                 makine_no = %s, 
                 guncelleyen_kullanici = %s 
                 WHERE id = %s"""
        
        # planlanan_miktar yerine toplam_adet'i gönderiyoruz
        cursor.execute(sql, (urun_id, durum, toplam_adet, toplam_adet, 
                             paket_sayisi, paket_ici_adet, makine, 
                             session.get('user_name'), ie_id))
        
        db.commit()
        flash("İş emri ve paket bilgileri güncellendi.")
    except Exception as e:
        flash(f"Hata: {str(e)}")
    finally:
        db.close()
    return redirect(url_for('is_emirleri'))


@app.route('/is_emri_sil/<int:id>')
def is_emri_sil(id):
    yetki = session.get('user_permissions', {}).get('isemri', 0)
    if session.get('user_role') != 'Admin' and int(yetki) < 4:
        flash("İş emri silme yetkiniz yok!")
        return redirect(url_for('is_emirleri'))

    db = get_db_connection()
    cursor = db.cursor()
    try:
        # Silen kullanıcıyı kaydet
        cursor.execute("UPDATE is_emirleri SET silen_kullanici=%s WHERE id=%s", (session.get('user_name'), id))
        cursor.execute("DELETE FROM is_emirleri WHERE id = %s", (id,))
        db.commit()
        flash("İş emri başarıyla silindi.")
    except Exception as e:
        flash(f"Hata: {str(e)}")
    finally:
        db.close()
    return redirect(url_for('is_emirleri'))


# --- ÜRETİM ANA SAYFASI VE LİSTELEME ---
@app.route('/uretim')
def uretim():
    if 'user_id' not in session: 
        return redirect(url_for('index'))
    
    perms = session.get('user_permissions', {})
    if session.get('user_role') != 'Admin' and int(perms.get('uretim', 0)) < 1:
        flash("Üretim ekranına erişim yetkiniz yok!", "danger")
        return redirect(url_for('dashboard'))
    
    db = get_db_connection()
    if not db:
        flash("Veritabanı bağlantısı kurulamadı.", "danger")
        return redirect(url_for('dashboard'))
        
    cursor = db.cursor()
    bugun = datetime.now().strftime('%y%m%d')
    
    try:
        # 1. Otomatik Üretim No Oluştur
        cursor.execute("SELECT COUNT(id) as sayi FROM uretimler WHERE uretim_no LIKE %s", (f"UR-{bugun}%",))
        result = cursor.fetchone()
        count = (result['sayi'] + 1) if result and result['sayi'] else 1
        yeni_uretim_no = f"UR-{bugun}-{count:03d}"

        # 2. Aktif İş Emirlerini Getir (Üretimde görünmesi sağlandı)
        cursor.execute("""
            SELECT ie.id, ie.is_emri_no, u.urun_adi 
            FROM is_emirleri ie 
            JOIN urunler u ON ie.urun_id = u.id 
            WHERE (ie.durum != 'Tamamlandı' OR ie.durum IS NULL)
            ORDER BY ie.id DESC
        """)
        is_emirleri = cursor.fetchall()
        
        # 3. Üretim toplamlarını ve ilişkiyi sipariş bazında çek
        cursor.execute("""
            SELECT s.id AS siparis_id,
                   IFNULL(SUM(u.toplam_adet), 0) AS uretim_toplam
            FROM siparisler s
            LEFT JOIN is_emirleri ie ON ie.siparis_id = s.id
            LEFT JOIN uretimler u ON u.is_emri_id = ie.id
            GROUP BY s.id
        """)
        siparis_uretim_map = {row['siparis_id']: row['uretim_toplam'] or 0 for row in cursor.fetchall()}

        # 4. Ürünler ve Operatörler
        cursor.execute("SELECT id, urun_adi FROM urunler ORDER BY urun_adi ASC")
        tum_urunler = cursor.fetchall()
        
        cursor.execute("SELECT id, CONCAT(ad, ' ', soyadi) as ad_soyad FROM operatorler WHERE aktif_mi = 1")
        operatorler_listesi = cursor.fetchall() 
        
        # 4. Üretim Geçmişi
        cursor.execute("""
            SELECT ur.*, u.urun_adi,
                   COALESCE(ur.operator_adi, CONCAT(op.ad, ' ', op.soyadi)) as operator_adi
            FROM uretimler ur
            JOIN urunler u ON ur.urun_id = u.id
            LEFT JOIN operatorler op ON ur.operator_id = op.id
            ORDER BY ur.id DESC LIMIT 50
        """)
        uretim_gecmisi = cursor.fetchall()
        
    except Exception as e:
        flash(f"Sistem Hatası: {str(e)}", "danger")
        is_emirleri, tum_urunler, operatorler_listesi, uretim_gecmisi = [], [], [], []
        yeni_uretim_no = f"UR-{bugun}-ERR"
    finally:
        db.close()

    return render_template('uretim.html', 
                           uretim_no=yeni_uretim_no, 
                           is_emirleri=is_emirleri, 
                           urunler=tum_urunler,
                           operatorler=operatorler_listesi, 
                           uretim_gecmisi=uretim_gecmisi,
                           now=datetime.now().strftime('%Y-%m-%d'))




# --- YENİ ÜRETİM EKLEME (BARKODSUZ MANUEL SİSTEM) ---
@app.route('/uretim_ekle', methods=['POST'])
def uretim_ekle():
    if 'user_id' not in session:
        return redirect(url_for('index'))
        
    perms = session.get('user_permissions', {})
    if session.get('user_role') != 'Admin' and int(perms.get('uretim', 0)) < 2:
        flash("Bu işlem için yetkiniz yok.", "danger")
        return redirect(url_for('uretim'))

    db = get_db_connection()
    if not db:
        flash("Veritabanı bağlantısı kurulamadı.", "danger")
        return redirect(url_for('uretim'))

    cursor = db.cursor()
    try:
        # Form verilerini al
        urun_id = request.form.get('urun_id')
        makine_val = request.form.get('makine') 
        operator_val = request.form.get('operator_id')
        is_emri_id = request.form.get('is_emri_id')
        operator_adi = None
        if operator_val:
            cursor.execute("SELECT CONCAT(ad, ' ', soyadi) AS ad_soyad FROM operatorler WHERE id = %s", (operator_val,))
            op = cursor.fetchone()
            operator_adi = op['ad_soyad'] if op else None
        if not is_emri_id or is_emri_id in ["", "0"]: is_emri_id = None
            
        paket_sayisi = int(request.form.get('paket_sayisi') or 0)
        paket_ici_adet = int(request.form.get('paket_ici_adet') or 0)
        toplam_adet = paket_sayisi * paket_ici_adet # Toplam üretilen miktar
        
        devir_val = request.form.get('devir') or 0
        tarih_form = request.form.get('tarih') or datetime.now().strftime('%Y-%m-%d')
        uretim_no = request.form.get('uretim_no')
        vardiya_val = request.form.get('vardiya')
        ekleyen = session.get('user_name', 'Bilinmeyen')

        if not urun_id or paket_sayisi <= 0:
            flash("Lütfen ürün seçin ve paket sayısı girin.", "warning")
            return redirect(url_for('uretim'))

    except ValueError:
        db.close()
        flash("Hatalı sayı girişi yapıldı.", "danger")
        return redirect(url_for('uretim'))

    try:
        # Sadece Üretim Tablosuna Kayıt Atıyoruz (Barkod oluşturma döngüsü silindi)
        sql_uretim = """INSERT INTO uretimler 
                     (uretim_no, urun_id, makine_no, operator_id, operator_adi, is_emri_id, paket_sayisi, 
                      paket_ici_adet, toplam_adet, makine_devri, vardiya, tarih, ekleyen_kullanici) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        
        cursor.execute(sql_uretim, (uretim_no, urun_id, makine_val, operator_val, operator_adi, is_emri_id, 
                                   paket_sayisi, paket_ici_adet, toplam_adet, devir_val, 
                                   vardiya_val, tarih_form, ekleyen))
        
        db.commit()
        flash(f"{uretim_no} No'lu Üretim ({toplam_adet} Adet) Başarıyla Kaydedildi.", "success")
        
    except Exception as e:
        db.rollback()
        flash(f"Hata: {str(e)}", "danger")
    finally:
        db.close()

    return redirect(url_for('uretim'))


# --- ÜRETİM SİLME ---
@app.route('/uretim_sil/<int:id>')
def uretim_sil(id):
    if session.get('user_role') != 'Admin' and int(session.get('user_permissions', {}).get('uretim', 0)) < 3:
        flash("Silme yetkiniz yok.", "danger")
        return redirect(url_for('uretim'))

    db = get_db_connection()
    cursor = db.cursor()
    try:
        # Önce miktar bilgisini al
        cursor.execute("SELECT urun_id, toplam_adet FROM uretimler WHERE id = %s", (id,))
        kayit = cursor.fetchone()
        
        if kayit:
            # 1. Stok sütununu dinamik bul
            cursor.execute("DESCRIBE urunler")
            cols = [row['Field'].lower() for row in cursor.fetchall()]
            stok_sutun = next((s for s in ['stok', 'stok_miktari', 'depo_guncelle', 'miktar'] if s in cols), None)
            
            if stok_sutun:
                cursor.execute(f"UPDATE urunler SET {stok_sutun} = {stok_sutun} - %s WHERE id = %s", 
                               (kayit['toplam_adet'], kayit['urun_id']))
            
            # Üretim kaydını sil
            cursor.execute("DELETE FROM uretimler WHERE id = %s", (id,))
            
            db.commit()
            flash("Üretim kaydı başarıyla silindi.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Hata: {str(e)}", "danger")
    finally:
        db.close()
    return redirect(url_for('uretim'))


# --- ÜRETİM DÜZENLEME SAYFASI (GET) ---
@app.route('/uretim_duzenle/<int:id>')
def uretim_duzenle(id):
    if 'user_id' not in session:
        return redirect(url_for('index'))

    perms = session.get('user_permissions', {})
    if session.get('user_role') != 'Admin' and int(perms.get('uretim', 0)) < 3:
        flash("Düzenleme yetkiniz yok.", "danger")
        return redirect(url_for('uretim'))

    db = get_db_connection()
    if not db:
        flash("Veritabanı bağlantı hatası.", "danger")
        return redirect(url_for('uretim'))

    cursor = db.cursor()
    try:
        # Üretim kaydını getir
        cursor.execute("SELECT * FROM uretimler WHERE id = %s", (id,))
        u = cursor.fetchone()

        if not u:
            flash("Kayıt bulunamadı.", "danger")
            return redirect(url_for('uretim'))

        # Ürün listesi
        cursor.execute("SELECT id, urun_adi FROM urunler ORDER BY urun_adi ASC")
        urunler = cursor.fetchall()

        # Operatör listesi
        cursor.execute("SELECT id, CONCAT(ad, ' ', soyadi) as ad_soyad FROM operatorler WHERE aktif_mi = 1")
        operatorler = cursor.fetchall()

    except Exception as e:
        flash(f"Hata: {str(e)}", "danger")
        return redirect(url_for('uretim'))
    finally:
        db.close()

    return render_template('uretim_duzenle.html', u=u, urunler=urunler, operatorler=operatorler)

@app.route('/uretim_guncelle/<int:id>', methods=['POST'])
def uretim_guncelle(id):
    if 'user_id' not in session: return redirect(url_for('index'))
    
    db = get_db_connection()
    cursor = db.cursor()

    try:
        # Form verilerini topluyoruz
        tarih = request.form.get('tarih')
        makine_no = request.form.get('makine_id')
        operator_id = request.form.get('operator_id')
        operator_adi = None
        if operator_id:
            cursor.execute("SELECT CONCAT(ad, ' ', soyadi) AS ad_soyad FROM operatorler WHERE id = %s", (operator_id,))
            op = cursor.fetchone()
            operator_adi = op['ad_soyad'] if op else None
        makine_devri = request.form.get('makine_devri') or 0
        paket_sayisi = int(request.form.get('paket_sayisi') or 0)
        paket_ici_adet = int(request.form.get('paket_ici_adet') or 0)
        yeni_toplam = paket_sayisi * paket_ici_adet
        notlar = request.form.get('notlar')
        urun_id = request.form.get('urun_id')
        vardiya = request.form.get('vardiya')

        # 1. Stok farkı için eski kaydı al
        cursor.execute("SELECT urun_id, toplam_adet FROM uretimler WHERE id = %s", (id,))
        eski = cursor.fetchone()
        
        if eski:
            # 2. Üretim kaydını güncelle
            cursor.execute("""
                UPDATE uretimler SET 
                tarih=%s, makine_no=%s, operator_id=%s, operator_adi=%s, makine_devri=%s, urun_id=%s,
                paket_sayisi=%s, paket_ici_adet=%s, toplam_adet=%s, notlar=%s, vardiya=%s,
                guncelleyen_kullanici=%s
                WHERE id=%s
            """, (tarih, makine_no, operator_id, operator_adi, makine_devri, urun_id, 
                  paket_sayisi, paket_ici_adet, yeni_toplam, notlar, vardiya, 
                  session.get('user_name'), id))

            # 3. Stok sütununu dinamik bul (Unknown Column hatasını çözer)
            cursor.execute("DESCRIBE urunler")
            cols = [row['Field'].lower() for row in cursor.fetchall()]
            stok_sutun = next((s for s in ['stok', 'stok_miktari', 'depo_guncelle', 'miktar'] if s in cols), None)

            if stok_sutun:
                # Eski miktarı düş, yeni miktarı ekle
                cursor.execute(f"UPDATE urunler SET {stok_sutun} = {stok_sutun} - %s WHERE id = %s", (eski['toplam_adet'], eski['urun_id']))
                cursor.execute(f"UPDATE urunler SET {stok_sutun} = {stok_sutun} + %s WHERE id = %s", (yeni_toplam, urun_id))

            db.commit()
            flash("Kayıt güncellendi ve stoklar düzenlendi.", "success")
        else:
            flash("Kayıt bulunamadı.", "danger")

    except Exception as e:
        db.rollback()
        flash(f"Hata: {str(e)}", "danger")
    finally:
        db.close()
    
    return redirect(url_for('uretim'))



@app.route('/get_is_emri_detay/<int:id>')
def get_is_emri_detay(id):
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("SELECT urun_id, makine_no, paket_sayisi, paket_ici_adet FROM is_emirleri WHERE id = %s", (id,))
    detay = cursor.fetchone()
    db.close()
    return json.dumps(detay)

# --- MÜŞTERİ YÖNETİMİ ---
@app.route('/musteriler')
def musteriler():
    if 'user_id' not in session: return redirect(url_for('index'))
    # Yetki kontrolü: Görüntüleme (1) veya üstü
    if session.get('user_permissions', {}).get('musteri', 0) < 1 and session.get('user_role') != 'Admin':
        flash('Müşteri sayfasını görüntüleme yetkiniz yok.', 'danger')
        return redirect(url_for('dashboard'))
    db = get_db_connection(); cursor = db.cursor()
    cursor.execute("SELECT * FROM musteriler ORDER BY id DESC")
    liste = cursor.fetchall(); db.close()
    return render_template('musteriler.html', musteriler=liste)

@app.route('/musteri_ekle', methods=['POST'])
def musteri_ekle():
    # Yetki kontrolü: Ekleme/İşlem (2) veya üstü
    if session.get('user_permissions', {}).get('musteri', 0) < 2 and session.get('user_role') != 'Admin':
        flash('Müşteri ekleme yetkiniz yok.', 'danger')
        return redirect(url_for('musteriler'))
    vals = (request.form.get('ad'), request.form.get('ilgili'), request.form.get('tel'))
    db = get_db_connection(); cursor = db.cursor()
    cursor.execute("INSERT INTO musteriler (musteri_adi, ilgili_kisi, telefon) VALUES (%s, %s, %s)", vals)
    db.commit(); db.close()
    flash("Müşteri eklendi.")
    return redirect(url_for('musteriler'))

# --- MÜŞTERİ GÜNCELLEME ---
@app.route('/musteri_guncelle', methods=['POST'])
def musteri_guncelle():
    # Yetki kontrolü: Düzenleme (3) veya üstü
    if session.get('user_permissions', {}).get('musteri', 0) < 3 and session.get('user_role') != 'Admin':
        flash('Müşteri güncelleme yetkiniz yok.', 'danger')
        return redirect(url_for('musteriler'))
    mid = request.form.get('id')
    ad = request.form.get('ad')
    ilgili = request.form.get('ilgili')
    tel = request.form.get('tel')
    db = get_db_connection(); cursor = db.cursor()
    cursor.execute("UPDATE musteriler SET musteri_adi=%s, ilgili_kisi=%s, telefon=%s WHERE id=%s", (ad, ilgili, tel, mid))
    db.commit(); db.close()
    flash("Müşteri güncellendi.")
    return redirect(url_for('musteriler'))

# --- MÜŞTERİ SİLME ---
@app.route('/musteri_sil/<int:id>')
def musteri_sil(id):
    # Yetki kontrolü: Silme (4) veya üstü
    if session.get('user_permissions', {}).get('musteri', 0) < 4 and session.get('user_role') != 'Admin':
        flash('Müşteri silme yetkiniz yok.', 'danger')
        return redirect(url_for('musteriler'))
    db = get_db_connection(); cursor = db.cursor()
    cursor.execute("DELETE FROM musteriler WHERE id=%s", (id,))
    db.commit(); db.close()
    flash("Müşteri silindi.")
    return redirect(url_for('musteriler'))

# --- ÜRÜN YÖNETİMİ ---
@app.route('/urunler')
def urunler():
    if 'user_id' not in session: return redirect(url_for('index'))
    # Yetki kontrolü: Görüntüleme (1) veya üstü
    if session.get('user_permissions', {}).get('urun', 0) < 1 and session.get('user_role') != 'Admin':
        flash('Ürün sayfasını görüntüleme yetkiniz yok.', 'danger')
        return redirect(url_for('dashboard'))
    db = get_db_connection(); cursor = db.cursor()
    cursor.execute("SELECT * FROM urunler ORDER BY id DESC")
    liste = cursor.fetchall(); db.close()
    return render_template('urunler.html', urunler=liste)

@app.route('/urun_ekle', methods=['POST'])
def urun_ekle():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    # 1. YETKİ KONTROLÜ (Orijinal kodunuzdaki yetki kontrolünü koruyoruz)
    if session.get('user_permissions', {}).get('urun', 0) < 2 and session.get('user_role') != 'Admin':
        flash('Ürün ekleme yetkiniz yok.', 'danger')
        return redirect(url_for('urunler'))
    
    kod = request.form.get('kod')
    ad = request.form.get('ad')
    gr = request.form.get('gr')
    paket_ici_adet = request.form.get('paket_ici_adet', 1)
    vals = (kod, ad, gr, paket_ici_adet)

    db = get_db_connection()
    if not db: return "Veritabanı bağlantı hatası", 500
    
    try:
        cursor = db.cursor()
        # 2. İŞLEM (Lock hatasını önlemek için try bloğu içinde)
        cursor.execute("INSERT INTO urunler (urun_kodu, urun_adi, urun_gr, paket_ici_adet) VALUES (%s, %s, %s, %s)", vals)
        db.commit() 
        flash("Ürün başarıyla eklendi.", "success")
    except Exception as e:
        if db: db.rollback() # Hata olursa kilitleri serbest bırak
        flash(f"Hata oluştu: {str(e)}", "danger")
    finally:
        if db: db.close() # BAĞLANTIYI HER KOŞULDA KAPAT
        
    return redirect(url_for('urunler'))

# --- ÜRÜN GÜNCELLEME ---
@app.route('/urun_guncelle', methods=['POST'])
def urun_guncelle():
    # Yetki kontrolü: Düzenleme (3) veya üstü
    if session.get('user_permissions', {}).get('urun', 0) < 3 and session.get('user_role') != 'Admin':
        flash('Ürün güncelleme yetkiniz yok.', 'danger')
        return redirect(url_for('urunler'))
    uid = request.form.get('id')
    kod = request.form.get('kod')
    ad = request.form.get('ad')
    gr = request.form.get('gr')
    paket_ici_adet = request.form.get('paket_ici_adet', 1)
    db = get_db_connection(); cursor = db.cursor()
    cursor.execute("UPDATE urunler SET urun_kodu=%s, urun_adi=%s, urun_gr=%s, paket_ici_adet=%s WHERE id=%s", (kod, ad, gr, paket_ici_adet, uid))
    db.commit(); db.close()
    flash("Ürün güncellendi.")
    return redirect(url_for('urunler'))

# --- ÜRÜN SİLME ---
@app.route('/urun_sil/<int:id>')
def urun_sil(id):
    # 1. Yetki kontrolü: Silme (4) veya Admin
    perms = session.get('user_permissions', {})
    if session.get('user_role') != 'Admin' and int(perms.get('urun', 0)) < 4:
        flash('Ürün silme yetkiniz yok.', 'danger')
        return redirect(url_for('urunler'))

    db = get_db_connection()
    if not db:
        flash("Veritabanı bağlantı hatası!", "danger")
        return redirect(url_for('urunler'))
        
    cursor = db.cursor()
    try:
        # 2. Ürüne bağlı alt kayıtları temizle (Foreign Key hatalarını önlemek için)
        # Not: Tablo isimlerinizin veritabanı ile tam eşleştiğinden emin olun.
        
        # Sayımlar tablosundaki kayıtları sil
        cursor.execute("DELETE FROM sayimlar WHERE urun_id = %s", (id,))
        
        # Üretimler tablosundaki kayıtları sil
        cursor.execute("DELETE FROM uretimler WHERE urun_id = %s", (id,))
        
        # Sipariş detaylarındaki kayıtları sil
        cursor.execute("DELETE FROM siparis_detay WHERE urun_id = %s", (id,))
        
        # Sevkiyat detaylarındaki kayıtları sil
        cursor.execute("DELETE FROM sevkiyat_detaylari WHERE urun_id = %s", (id,))
        
        # İş emri veya diğer tablolarınız varsa onları da buraya eklemelisiniz
        # cursor.execute("DELETE FROM is_emirleri WHERE urun_id = %s", (id,))

        # 3. Tüm bağımlılıklar temizlendikten sonra ana ürünü sil
        cursor.execute("DELETE FROM urunler WHERE id = %s", (id,))
        
        db.commit()
        flash("Ürün ve ürüne bağlı tüm geçmiş kayıtlar (sayım, üretim vb.) başarıyla silindi.", "warning")
        
    except Exception as e:
        db.rollback()
        flash(f"Ürün silinirken bir hata oluştu: {str(e)}", "danger")
    finally:
        db.close()
        
    return redirect(url_for('urunler'))


# --- OPERATÖR LİSTESİ ---
@app.route('/operatorler')
def operatorler():
    if 'user_id' not in session: return redirect(url_for('index'))
    # Yetki kontrolü: Görüntüleme (1) veya üstü
    if session.get('user_permissions', {}).get('operator', 0) < 1 and session.get('user_role') != 'Admin':
        flash('Operatör sayfasını görüntüleme yetkiniz yok.', 'danger')
        return redirect(url_for('dashboard'))
    db = get_db_connection()
    cursor = db.cursor()
    # Aktif olanları getiriyoruz
    cursor.execute("SELECT * FROM operatorler WHERE aktif_mi = 1 ORDER BY ad ASC")
    liste = cursor.fetchall()
    db.close()
    return render_template('operatorler.html', operatorler=liste)

# --- YENİ OPERATÖR EKLEME ---
@app.route('/operator_ekle', methods=['POST'])
def operator_ekle():
    if 'user_id' not in session: return redirect(url_for('index'))
    ad = request.form.get('ad')
    soyadi = request.form.get('soyadi')
    tel = request.form.get('telefon_no')
    
    db = get_db_connection()
    cursor = db.cursor()
    # aktif_mi sütununu manuel 1 olarak ekliyoruz ki listede hemen görünsün
    cursor.execute("""
        INSERT INTO operatorler (ad, soyadi, telefon_no, aktif_mi, kayit_tarihi) 
        VALUES (%s, %s, %s, 1, NOW())
    """, (ad, soyadi, tel))
    db.commit()
    db.close()
    flash(f"Operatör {ad} {soyadi} başarıyla eklendi.")
    return redirect(url_for('operatorler'))

# --- OPERATÖR SİLME (PASİFE ÇEKME) ---
@app.route('/operator_sil/<int:id>')
def operator_sil(id):
    if 'user_id' not in session: return redirect(url_for('index'))
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("UPDATE operatorler SET aktif_mi = 0 WHERE id = %s", (id,))
    db.commit()
    db.close()
    flash("Operatör sistemden kaldırıldı.")
    return redirect(url_for('operatorler'))



    if 'user_id' not in session: return redirect(url_for('index'))
    
    db = get_db_connection()
    cursor = db.cursor()
    
    # Tüm yüklemeleri, müşteri ve ürün isimleriyle birlikte getiriyoruz
    query = """
        SELECT y.*, 
               m.musteri_adi, 
               u.urun_adi, 
               s.siparis_no
        FROM yuklemeler y
        LEFT JOIN musteriler m ON y.musteri_id = m.id
        LEFT JOIN urunler u ON y.urun_id = u.id
        LEFT JOIN siparisler s ON y.siparis_id = s.id
        ORDER BY y.id DESC
    """
    cursor.execute(query)
    yuklemeler = cursor.fetchall()
    
    # Formdaki seçim kutuları için verileri tekrar çekiyoruz
    cursor.execute("SELECT id, musteri_adi FROM musteriler")
    musteriler = cursor.fetchall()
    
    cursor.execute("SELECT id, urun_adi FROM urunler")
    urunler = cursor.fetchall()
    
    cursor.execute("SELECT id, siparis_no FROM siparisler")
    siparisler = cursor.fetchall()
    
    db.close()
    
    return render_template('yukleme.html', 
                           yuklemeler=yuklemeler, 
                           musteriler=musteriler, 
                           urunler=urunler, 
                           siparisler=siparisler,
                           now_date=datetime.now().strftime('%Y-%m-%d'))

# --- API: SİPARİŞ SEÇİNCE MÜŞTERİ VE ÜRÜN BİLGİSİ GETİRME ---
@app.route('/get_siparis_detay/<int:siparis_id>')
def get_siparis_detay(siparis_id):
    db = get_db_connection()
    cursor = db.cursor()
    try:
        # Siparişe ait tüm ürünleri ve müşteri bilgisini çekiyoruz
        query = """
            SELECT sd.urun_id, u.urun_adi, s.musteri_id, m.musteri_adi,
                   sd.paket_sayisi, sd.paket_ici_adet
            FROM siparis_detay sd
            JOIN urunler u ON sd.urun_id = u.id
            JOIN siparisler s ON sd.siparis_id = s.id
            JOIN musteriler m ON s.musteri_id = m.id
            WHERE sd.siparis_id = %s
        """
        cursor.execute(query, (siparis_id,))
        urunler = cursor.fetchall()
        # DictCursor sonuçlarını listeye dönüştür
        result = []
        for row in urunler:
            result.append({
                'urun_id': row.get('urun_id'),
                'urun_adi': row.get('urun_adi'),
                'musteri_id': row.get('musteri_id'),
                'musteri_adi': row.get('musteri_adi'),
                'paket_sayisi': row.get('paket_sayisi'),
                'paket_ici_adet': row.get('paket_ici_adet')
            })
        return jsonify(result)
    except Exception as e:
        print(f"API Hatası: {e}")
        return jsonify([])
    finally:
        db.close()



# --- YÜKLEME SAYFASI GÖRÜNTÜLEME ---
@app.route('/yukleme')
def yukleme():
    # 1. Oturum Kontrolü
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    db = get_db_connection()
    if not db:
        return "Veritabanı bağlantı hatası!", 500

    try:
        cursor = db.cursor()
        
        # 2. Seçim Listelerini Çekme (Dropdown menüler için)
        cursor.execute("SELECT id, musteri_adi FROM musteriler ORDER BY musteri_adi ASC")
        musteriler = cursor.fetchall()
        
        cursor.execute("SELECT id, urun_adi FROM urunler ORDER BY urun_adi ASC")
        urunler = cursor.fetchall()
        
        cursor.execute("SELECT id, siparis_no FROM siparisler WHERE durum != 'Tamamlandı'")
        siparisler = cursor.fetchall()

        # 3. Ana Yükleme Kayıtlarını Çekme (İlişkili Tablolarla Birlikte)
        # DISTINCT kullanımı yerine JOIN yapısını optimize ettik
        query = """
            SELECT 
                y.id, 
                y.tarih, 
                y.arac_plakasi, 
                y.durum, 
                s.siparis_no,
                m.musteri_adi
            FROM yuklemeler y
            LEFT JOIN siparisler s ON y.siparis_id = s.id
            LEFT JOIN musteriler m ON s.musteri_id = m.id
            ORDER BY y.tarih DESC, y.id DESC
        """
        cursor.execute(query)
        yuklemeler = cursor.fetchall()

    except Exception as e:
        print(f"Hata oluştu: {e}")
        return "Veri çekme sırasında bir hata oluştu.", 500
    
    finally:
        # 4. Bağlantıyı her durumda kapat
        cursor.close()
        db.close()

    # 5. Sayfayı Render Et
    return render_template(
        'yukleme.html', 
        musteriler=musteriler, 
        urunler=urunler, 
        siparisler=siparisler, 
        yuklemeler=yuklemeler,
        now_date=datetime.now().strftime('%Y-%m-%d')
    )

# --- MANUEL SEVKİYAT / YÜKLEME KAYDI (HATA DÜZELTİLMİŞ) ---
@app.route('/yukleme_ekle', methods=['POST'])
def yukleme_ekle():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    tarih = request.form.get('tarih') or datetime.now().strftime('%Y-%m-%d')
    siparis_id = request.form.get('siparis_id')
    if not siparis_id or siparis_id == "0": siparis_id = None
    plaka = request.form.get('plaka')
    durum = request.form.get('durum', 'Tamamlandı')

    musteri_ids = request.form.getlist('musteri_id[]')
    urun_ids = request.form.getlist('urun_id[]')
    paketler = request.form.getlist('paket[]') 

    db = get_db_connection()
    cursor = db.cursor()
    try:
        # 1. Ana Yükleme Kaydı
        cursor.execute("""
            INSERT INTO yuklemeler (tarih, siparis_id, arac_plakasi, durum) 
            VALUES (%s, %s, %s, %s)
        """, (tarih, siparis_id, plaka, durum))
        yeni_id = cursor.lastrowid

        # Eğer form'dan ürün verisi yoksa, siparis_detay'dan çek
        if siparis_id and not urun_ids:
            cursor.execute("""
                SELECT sd.urun_id, u.urun_adi, u.paket_ici_adet, s.musteri_id
                FROM siparis_detay sd
                JOIN urunler u ON sd.urun_id = u.id
                JOIN siparisler s ON sd.siparis_id = s.id
                WHERE sd.siparis_id = %s
            """, (siparis_id,))
            siparis_urunler = cursor.fetchall()
            for row in siparis_urunler:
                urun_ids.append(str(row['urun_id']))
                musteri_ids.append(str(row['musteri_id']) if row['musteri_id'] else '')
                paketler.append('1')  # Default 1 paket
            print(f"DEBUG: Siparis {siparis_id}'den {len(siparis_urunler)} ürün çekildi")

        # 2. Detay Tablosuna Kayıt
        detay_sayisi = 0
        for i in range(len(urun_ids)):
            u_id = urun_ids[i]
            m_id = musteri_ids[i] if i < len(musteri_ids) and musteri_ids[i] else None
            p_sayisi = int(paketler[i] or 0)

            if u_id and u_id != "":
                # Ürünün paket içi adetini çekelim
                cursor.execute("SELECT paket_ici_adet FROM urunler WHERE id = %s", (u_id,))
                urun_bilgi = cursor.fetchone()
                p_ici = urun_bilgi['paket_ici_adet'] if urun_bilgi and urun_bilgi['paket_ici_adet'] else 1
                
                # Paket sayısı 0 olsa da kaydet (çünkü sevkiyat'ta düzenlenebilir)
                toplam_adet = p_sayisi * p_ici

                # musteri_id'yi de kaydedelim
                try:
                    u_id = int(u_id)
                    if m_id:
                        m_id = int(m_id)
                    cursor.execute("""
                        INSERT INTO yukleme_detaylari (yukleme_id, musteri_id, urun_id, paket, paket_ici, toplam_adet) 
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (yeni_id, m_id, u_id, p_sayisi, p_ici, toplam_adet))
                    detay_sayisi += 1
                    print(f"DEBUG: Yükleme {yeni_id} - Detay eklendi: urun_id={u_id}, musteri_id={m_id}, paket={p_sayisi}")
                except (ValueError, TypeError) as e:
                    print(f"DEBUG: Detay ekleme hatası: {e}")
                    continue

        print(f"DEBUG: Toplam {detay_sayisi} detay eklendi")

        db.commit()
        flash(f"Sevkiyat başarıyla kaydedildi. (No: {yeni_id})", "success")
    except Exception as e:
        db.rollback()
        flash(f"Sevkiyat Hatası: {str(e)}", "danger")
    finally:
        db.close()
    
    return redirect(url_for('yukleme'))

# --- YÜKLEME SİLME ---
@app.route('/yukleme_sil/<int:id>')
def yukleme_sil(id):
    if 'user_id' not in session: return redirect(url_for('index'))
    
    db = get_db_connection()
    cursor = db.cursor()
    try:
        # Önce detayları sil (Foreign Key kısıtlaması varsa hata almamak için)
        cursor.execute("DELETE FROM yukleme_detaylari WHERE yukleme_id = %s", (id,))
        # Sonra ana kaydı sil
        cursor.execute("DELETE FROM yuklemeler WHERE id = %s", (id,))
        db.commit()
        flash(f"Yükleme #{id} ve bağlı tüm detaylar başarıyla silindi.", "warning")
    except Exception as e:
        db.rollback()
        flash(f"Silme hatası: {str(e)}", "danger")
    finally:
        db.close()
    return redirect(url_for('yukleme'))

@app.route('/get_yukleme_detay/<int:id>')
def get_yukleme_detay(id):
    db = get_db_connection()
    if not db:
        return jsonify([])
    cursor = db.cursor()
    try:
        query = """
            SELECT 
                yd.id,
                yd.musteri_id,
                m.musteri_adi, 
                yd.urun_id,
                u.urun_adi, 
                yd.paket, 
                yd.paket_ici, 
                yd.toplam_adet
            FROM yukleme_detaylari yd
            LEFT JOIN musteriler m ON yd.musteri_id = m.id
            LEFT JOIN urunler u ON yd.urun_id = u.id
            WHERE yd.yukleme_id = %s
        """
        cursor.execute(query, (id,))
        detaylar = cursor.fetchall()
        print(f"DEBUG: Yukleme {id} için {len(detaylar)} detay bulundu")
        for row in detaylar:
            print(f"DEBUG: {row}")
        # DictCursor sonuçlarını listeye dönüştür
        result = []
        for row in detaylar:
            result.append({
                'id': row.get('id'),
                'musteri_id': row.get('musteri_id'),
                'musteri_adi': row.get('musteri_adi'),
                'urun_id': row.get('urun_id'),
                'urun_adi': row.get('urun_adi'),
                'paket': row.get('paket'),
                'paket_ici': row.get('paket_ici'),
                'toplam_adet': row.get('toplam_adet')
            })
        print(f"DEBUG: Returning {len(result)} items")
        return jsonify(result) 
    except Exception as e:
        print(f"DETAY GETİRME HATASI: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify([])
    finally:
        db.close()

# --- YÜKLEME DÜZENLEME SAYFASI ---
@app.route('/yukleme_duzenle/<int:id>')
def yukleme_duzenle(id):

    if 'user_id' not in session:
        return redirect(url_for('index'))
    db = get_db_connection()
    cursor = db.cursor()

    # Ana bilgiyi al
    cursor.execute("SELECT * FROM yuklemeler WHERE id = %s", (id,))
    yukleme = cursor.fetchone()

    # Detayları al
    cursor.execute("""
        SELECT yd.*, m.musteri_adi, u.urun_adi 
        FROM yukleme_detaylari yd
        LEFT JOIN musteriler m ON yd.musteri_id = m.id
        LEFT JOIN urunler u ON yd.urun_id = u.id
        WHERE yd.yukleme_id = %s
    """, (id,))
    detaylar = cursor.fetchall()

    # Form listeleri
    cursor.execute("SELECT id, musteri_adi FROM musteriler")
    musteriler = cursor.fetchall()
    cursor.execute("SELECT id, urun_adi FROM urunler")
    urunler = cursor.fetchall()

    db.close()
    return render_template('yukleme_duzenle.html', 
                           y=yukleme, detaylar=detaylar, 
                           musteriler=musteriler, urunler=urunler)


# --- YÜKLEME GÜNCELLEME (POST) ---
@app.route('/yukleme_guncelle/<int:id>', methods=['POST'])
def yukleme_guncelle(id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    tarih = request.form.get('tarih')
    siparis_id = request.form.get('siparis_id') or None
    plaka = request.form.get('plaka')
    durum = request.form.get('durum', 'Hazırlanıyor')

    musteri_ids = request.form.getlist('musteri_id[]')
    urun_ids = request.form.getlist('urun_id[]')
    paketler = request.form.getlist('paket[]')
    paket_iciler = request.form.getlist('paket_ici[]')

    db = get_db_connection()
    cursor = db.cursor()
    try:
        # Ana tabloyu güncelle
        cursor.execute("UPDATE yuklemeler SET tarih=%s, siparis_id=%s, arac_plakasi=%s, durum=%s WHERE id=%s", 
                       (tarih, siparis_id, plaka, durum, id))

        # Eski detayları sil
        cursor.execute("DELETE FROM yukleme_detaylari WHERE yukleme_id = %s", (id,))

        # Yeni detayları ekle
        for i in range(len(urun_ids)):
            mid = musteri_ids[i] if i < len(musteri_ids) and musteri_ids[i] else None
            uid = urun_ids[i]
            p = int(paketler[i] or 0)
            pi = int(paket_iciler[i] or 0)
            toplam = p * pi
            
            # Ürün ID zorunlu (boş değil ve sayısal), paket sayısı 0'dan büyük olmalı
            if uid and uid != "" and toplam > 0:
                try:
                    uid = int(uid)
                    if mid:
                        mid = int(mid)
                    cursor.execute("""INSERT INTO yukleme_detaylari 
                                     (yukleme_id, musteri_id, urun_id, paket, paket_ici, toplam_adet) 
                                     VALUES (%s, %s, %s, %s, %s, %s)""", 
                                   (id, mid, uid, p, pi, toplam))
                except (ValueError, TypeError):
                    # Geçersiz ID formatı, satırı atla
                    continue
        db.commit()
        flash(f"Yükleme #{id} başarıyla güncellendi.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Hata: {str(e)}", "danger")
    finally:
        db.close()
    return redirect(url_for('yukleme'))


@app.route('/get_barkod_bilgi/<barkod_no>')
def get_barkod_bilgi(barkod_no):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db_connection()
    if not db:
        return jsonify({'error': 'DB Bağlantı Hatası'}), 500

    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT pt.barkod_no, pt.urun_id, pt.urun_adi, pt.paket_ici_adet,
                   pt.vardiya, pt.operator, pt.durum
            FROM paket_takip pt
            WHERE pt.barkod_no = %s
        """, (barkod_no,))
        paket = cursor.fetchone()

        if not paket:
            return jsonify({'error': 'Barkod bulunamadı'}), 404

        return jsonify({
            'barkod_no': paket['barkod_no'],
            'urun_id': paket['urun_id'],
            'urun_adi': paket['urun_adi'],
            'paket_ici_adet': paket['paket_ici_adet'],
            'vardiya': paket['vardiya'],
            'operator': paket['operator'],
            'musteri_id': None
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/yukleme_detay/<int:id>')
def yukleme_detay(id):
    if 'user_id' not in session: return redirect(url_for('index'))
    
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        # Ana yükleme bilgisi
        cursor.execute("SELECT * FROM yuklemeler WHERE id = %s", (id,))
        yukleme = cursor.fetchone()
        
        # Detaylar (Sütun isimlerini veritabanına göre eşitledik)
        query = """
            SELECT 
                yd.id,
                u.urun_adi,
                yd.paket AS miktar_paket, -- Veritabanında 'paket', arayüzde 'miktar_paket' olarak kullanılıyor olabilir
                yd.paket_ici,
                yd.toplam_adet
            FROM yukleme_detaylari yd
            JOIN urunler u ON yd.urun_id = u.id
            WHERE yd.yukleme_id = %s
        """
        cursor.execute(query, (id,))
        detaylar = cursor.fetchall()
        
        return render_template('yukleme_detay.html', yukleme=yukleme, detaylar=detaylar)
    except Exception as e:
        flash(f"Detay hatası: {str(e)}", "danger")
        return redirect(url_for('yukleme'))
    finally:
        db.close()

# --- SEVKİYAT SAYFASI GÖRÜNTÜLEME ---
@app.route('/sevkiyat')
def sevkiyat():
    if 'user_id' not in session: return redirect(url_for('index'))
    # Yetki kontrolü: Görüntüleme (1) veya üstü
    if session.get('user_permissions', {}).get('sevkiyat', 0) < 1 and session.get('user_role') != 'Admin':
        flash('Sevkiyat sayfasını görüntüleme yetkiniz yok.', 'danger')
        return redirect(url_for('dashboard'))
    db = get_db_connection()
    cursor = db.cursor()
    
    cursor.execute("SELECT id, musteri_adi FROM musteriler")
    musteriler = cursor.fetchall()
    cursor.execute("SELECT id, urun_adi FROM urunler")
    urunler = cursor.fetchall()
    cursor.execute("SELECT id, arac_plakasi FROM yuklemeler ORDER BY id DESC")
    yuklemeler = cursor.fetchall()
    cursor.execute("SELECT * FROM sevkiyatlar ORDER BY id DESC")
    sevkiyatlar = cursor.fetchall()
    
    db.close()
    return render_template('sevkiyat.html', 
                           musteriler=musteriler, 
                           urunler=urunler, 
                           yuklemeler=yuklemeler,
                           sevkiyatlar=sevkiyatlar,
                           now_date=datetime.now().strftime('%Y-%m-%d'))

@app.route('/sevkiyat_ekle', methods=['POST'])
def sevkiyat_ekle():
    if 'user_id' not in session: return redirect(url_for('index'))
    if session.get('user_permissions', {}).get('sevkiyat', 0) < 2 and session.get('user_role') != 'Admin':
        flash('Sevkiyat ekleme yetkiniz yok.', 'danger')
        return redirect(url_for('sevkiyat'))

    tarih = request.form.get('tarih')
    y_id = request.form.get('yukleme_id') or None
    plaka = request.form.get('plaka')
    toplam_kilo = float(request.form.get('toplam_kilo_input') or 0)

    musteri_ids   = request.form.getlist('musteri_id[]')
    urun_ids      = request.form.getlist('urun_id[]')
    paketler      = request.form.getlist('paket[]')
    paket_iciler  = request.form.getlist('paket_ici[]')

    db = get_db_connection()
    cursor = db.cursor()

    try:
        # Eğer yükleme seçilmiş ama ürün verisi yoksa, yüklemedeki ürünleri detaya al
        if y_id and not urun_ids:
            cursor.execute("SELECT musteri_id, urun_id, paket, paket_ici FROM yukleme_detaylari WHERE yukleme_id = %s", (y_id,))
            yukleme_detaylari = cursor.fetchall()
            for row in yukleme_detaylari:
                urun_ids.append(row['urun_id'])
                musteri_ids.append(row['musteri_id'] if row['musteri_id'] else '')
                paketler.append(str(row['paket']))
                paket_iciler.append(str(row['paket_ici']))

        if not urun_ids:
            flash('Sevkiyat için en az bir ürün olmalıdır.', 'warning')
            return redirect(url_for('sevkiyat'))

        # Ana sevkiyat kaydı
        cursor.execute(
            "INSERT INTO sevkiyatlar (tarih, yukleme_id, arac_plakasi, toplam_kilo) VALUES (%s,%s,%s,%s)",
            (tarih, y_id, plaka, toplam_kilo)
        )
        s_id = cursor.lastrowid

        # Stok sütununu bul
        cursor.execute("DESCRIBE urunler")
        cols = [row['Field'].lower() for row in cursor.fetchall()]
        stok_sutun = next((s for s in ['stok_miktari','stok','depo_guncelle','miktar'] if s in cols), None)

        # Müşteri+Ürün bazında grupla
        gruplar = {}
        for i in range(len(urun_ids)):
            if not urun_ids[i]:
                continue
            mid = musteri_ids[i] if i < len(musteri_ids) and musteri_ids[i] else None
            # Aynı ürün+müşteri kombinasyonu için grupla (musteri None ise sadece urun_id ile)
            key = (mid or 'none', urun_ids[i])
            p   = int(paketler[i] or 0)
            pi  = int(paket_iciler[i] or 0)

            if key not in gruplar:
                gruplar[key] = {'musteri_id': mid, 'urun_id': urun_ids[i],
                                'paket': 0, 'paket_ici': pi}
            gruplar[key]['paket'] += p
            if pi > gruplar[key]['paket_ici']:
                gruplar[key]['paket_ici'] = pi

        for g in gruplar.values():
            cursor.execute(
                "INSERT INTO sevkiyat_detaylari (sevkiyat_id, musteri_id, urun_id, paket, paket_ici, kilo) VALUES (%s,%s,%s,%s,%s,%s)",
                (s_id, g['musteri_id'], g['urun_id'], g['paket'], g['paket_ici'], 0)
            )

            # Stoktan düş
            if stok_sutun:
                toplam_adet = g['paket'] * g['paket_ici']
                cursor.execute(
                    f"UPDATE urunler SET {stok_sutun} = {stok_sutun} - %s WHERE id = %s",
                    (toplam_adet, g['urun_id'])
                )

        db.commit()
        flash("Sevkiyat kaydedildi. Stoklar güncellendi.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Hata: {str(e)}", "danger")
    finally:
        db.close()
    return redirect(url_for('sevkiyat'))

@app.route('/sevkiyat_sil/<int:id>')
def sevkiyat_sil(id):
    # Yetki kontrolü: Silme (4) veya üstü
    if session.get('user_permissions', {}).get('sevkiyat', 0) < 4 and session.get('user_role') != 'Admin':
        flash('Sevkiyat silme yetkiniz yok.', 'danger')
        return redirect(url_for('sevkiyat'))
    db = get_db_connection()
    cursor = db.cursor()
    # Önce detayları sonra ana kaydı silmelisiniz (Foreign Key varsa)
    cursor.execute("DELETE FROM sevkiyat_detaylari WHERE sevkiyat_id = %s", (id,))
    cursor.execute("DELETE FROM sevkiyatlar WHERE id = %s", (id,))
    db.commit()
    db.close()
    flash("Sevkiyat kaydı başarıyla silindi.", "warning")
    return redirect(url_for('sevkiyat'))


# --- SEVKİYAT DÜZENLEME SAYFASI ---
@app.route('/sevkiyat_duzenle/<int:id>')
def sevkiyat_duzenle(id):
    if 'user_id' not in session: return redirect(url_for('index'))
    # Yetki kontrolü: Düzenleme (3) veya üstü
    if session.get('user_permissions', {}).get('sevkiyat', 0) < 3 and session.get('user_role') != 'Admin':
        flash('Sevkiyat düzenleme yetkiniz yok.', 'danger')
        return redirect(url_for('sevkiyat'))
    db = get_db_connection()
    cursor = db.cursor()
    
    cursor.execute("SELECT * FROM sevkiyatlar WHERE id = %s", (id,))
    sevkiyat = cursor.fetchone()
    
    cursor.execute("""
        SELECT sd.*, m.musteri_adi, u.urun_adi 
        FROM sevkiyat_detaylari sd
        JOIN musteriler m ON sd.musteri_id = m.id
        JOIN urunler u ON sd.urun_id = u.id
        WHERE sd.sevkiyat_id = %s
    """, (id,))
    detaylar = cursor.fetchall()
    
    cursor.execute("SELECT id, musteri_adi FROM musteriler")
    musteriler = cursor.fetchall()
    cursor.execute("SELECT id, urun_adi FROM urunler")
    urunler = cursor.fetchall()
    db.close()
    
    return render_template('sevkiyat_duzenle.html', sevkiyat=sevkiyat, detaylar=detaylar, musteriler=musteriler, urunler=urunler)


# --- SEVKİYAT GÜNCELLEME İŞLEMİ (POST) ---
@app.route('/sevkiyat_guncelle/<int:id>', methods=['POST'])
def sevkiyat_guncelle(id):
    if 'user_id' not in session: return redirect(url_for('index'))
    # Yetki kontrolü: Düzenleme (3) veya üstü
    if session.get('user_permissions', {}).get('sevkiyat', 0) < 3 and session.get('user_role') != 'Admin':
        flash('Sevkiyat güncelleme yetkiniz yok.', 'danger')
        return redirect(url_for('sevkiyat'))
    
    tarih = request.form.get('tarih')
    plaka = request.form.get('plaka')
    m_ids = request.form.getlist('musteri_id[]')
    u_ids = request.form.getlist('urun_id[]')
    paketler = request.form.getlist('paket[]')
    iciler = request.form.getlist('paket_ici[]')
    kilolar = request.form.getlist('urun_kilo[]')
    
    toplam_kilo = sum([float(k) for k in kilolar if k])

    db = get_db_connection()
    cursor = db.cursor()
    try:
        # Ana tabloyu güncelle
        cursor.execute("UPDATE sevkiyatlar SET tarih=%s, arac_plakasi=%s, toplam_kilo=%s WHERE id=%s", 
                       (tarih, plaka, toplam_kilo, id))
        
        # Önce eski detayları siliyoruz (Veri kirliliğini önlemek için en güvenli yol)
        cursor.execute("DELETE FROM sevkiyat_detaylari WHERE sevkiyat_id = %s", (id,))
        
        # Yeni/Güncellenmiş detayları ekliyoruz
        for i in range(len(u_ids)):
            cursor.execute("""
                INSERT INTO sevkiyat_detaylari (sevkiyat_id, musteri_id, urun_id, paket, paket_ici, kilo) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (id, m_ids[i], u_ids[i], paketler[i], iciler[i], kilolar[i]))
            
        db.commit()
        flash("Sevkiyat kaydı başarıyla güncellendi.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Hata oluştu: {str(e)}", "danger")
    finally:
        db.close()
    return redirect(url_for('sevkiyat'))


# --- API: SEVKİYAT DETAYLARINI GETİR (MODAL İÇİN) ---
@app.route('/get_sevkiyat_detaylari/<int:sid>')
def get_sevkiyat_detaylari(sid):
    if 'user_id' not in session: return json.dumps([])
    
    db = get_db_connection()
    if not db: return json.dumps([])
    
    cursor = db.cursor()
    # Sevkiyat detaylarını müşteri ve ürün isimleriyle birlikte getirir
    query = """
        SELECT sd.*, 
               COALESCE(m.musteri_adi, '—') as musteri_adi, 
               u.urun_adi 
        FROM sevkiyat_detaylari sd
        LEFT JOIN musteriler m ON sd.musteri_id = m.id
        JOIN urunler u ON sd.urun_id = u.id
        WHERE sd.sevkiyat_id = %s
    """
    try:
        cursor.execute(query, (sid,))
        detaylar = cursor.fetchall()
    except Exception as e:
        print(f"Hata: {e}")
        detaylar = []
    finally:
        db.close()
    
    return json.dumps(detaylar, default=str)



@app.route('/depo')
def depo():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    db = get_db_connection()
    if not db: return "Bağlantı Hatası"
    cursor = db.cursor()
    
    try:
        # 1. Ürün listesini al
        cursor.execute("SELECT id, urun_adi, urun_gr, paket_ici_adet FROM urunler")
        urunler = cursor.fetchall()
        
        for u in urunler:
            u_id = u['id']
            
            # --- SAYIM ---
            # En son yapılan depo sayım miktarını getirir
            cursor.execute("SELECT paket_sayisi FROM sayimlar WHERE urun_id = %s ORDER BY id DESC LIMIT 1", (u_id,))
            s_res = cursor.fetchone()
            u['depo_sayimi'] = float(s_res['paket_sayisi']) if s_res and s_res['paket_sayisi'] is not None else 0.0

            # --- ÜRETİM ---
            # Üretimler tablosundaki ilgili ürüne ait toplam paket sayısı
            cursor.execute("SELECT SUM(paket_sayisi) as toplam FROM uretimler WHERE urun_id = %s", (u_id,))
            ur_res = cursor.fetchone()
            u['uretim_paketi'] = float(ur_res['toplam']) if ur_res and ur_res['toplam'] is not None else 0.0
            
            # --- SEVKİYAT (DÜZELTİLDİ) ---
            # Sevkiyat detayları tablosundan (sevkiyat_detaylari) paket sayılarını topluyoruz
            u['sevk_edilen_paket'] = 0.0
            try:
                # Ürün bazlı sevkiyat detaylarını topluyoruz
                cursor.execute("""
                    SELECT SUM(paket) as toplam 
                    FROM sevkiyat_detaylari 
                    WHERE urun_id = %s
                """, (u_id,))
                sv_res = cursor.fetchone()
                u['sevk_edilen_paket'] = float(sv_res['toplam']) if sv_res and sv_res['toplam'] is not None else 0.0
            except Exception as e:
                print(f"Sevkiyat detayı çekilirken hata: {e}")
                u['sevk_edilen_paket'] = 0.0
            
            # --- KALAN HESABI ---
            # Formül: (Son Sayım + Sayımdan Sonraki Üretimler) - Sevkiyatlar
            # Not: Eğer sayım sistemi "Sıfırlayıcı" çalışıyorsa üretimleri tarihe göre filtrelemek gerekebilir.
            # Ancak genel mantık: Mevcut Stok + Üretim - Sevkiyat
            u['kalan_paket'] = float(u['depo_sayimi'] + u['uretim_paketi'] - u['sevk_edilen_paket'])
            
            p_ici = u['paket_ici_adet'] or 0
            g = float(u['urun_gr']) if u['urun_gr'] else 0
            u['paket_ici'] = p_ici
            u['toplam_adet'] = u['kalan_paket'] * p_ici
            u['gramaj'] = int(g) if g == int(g) else g
            
            # Gramaj hesaplaması (Kalan Paket * Paket İçi * Gramaj / 1000 = KG)
            u['toplam_kilo'] = (u['toplam_adet'] * g) / 1000

        db.close()
        return render_template('depo.html', urunler=urunler)
    
    except Exception as e:
        if db: db.close()
        print(f"HATA: {str(e)}")
        return f"Sistem Hatası: {str(e)}"

@app.route('/depo_sayim_guncelle', methods=['POST'])
def depo_sayim_guncelle():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    urun_id = request.form.get('urun_id')
    sayim_miktari = request.form.get('sayim_miktari')
    kullanici = session.get('user_name', 'Sistem')

    db = get_db_connection()
    if not db: return "Bağlantı Hatası"
    cursor = db.cursor()
    
    try:
        # Sayım kaydı ekle
        cursor.execute("""
            INSERT INTO sayimlar (urun_id, paket_sayisi, ekleyen_kullanici, tarih) 
            VALUES (%s, %s, %s, NOW())
        """, (urun_id, sayim_miktari, kullanici))
        db.commit()
        flash("Depo sayımı başarıyla güncellendi.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Hata: {str(e)}", "danger")
    finally:
        db.close()
    
    return redirect(url_for('depo'))

# --- PAKET GÜNCELLEME (HATASIZ) ---
@app.route('/paket_guncelle', methods=['POST']) # 'method' değil 'methods' olarak düzeltildi
def paket_guncelle():
    if 'user_id' not in session: return "Yetkisiz", 401
    
    urun_id = request.form.get('urun_id')
    yeni_paket_miktari = request.form.get('uretim_paketi')
    
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        # Bu işlem 'yukleme_detaylari' tablosundaki miktarları revize eder
        # Not: Gerçek senaryoda burası daha detaylı bir log tutmalıdır.
        cursor.execute("""
            UPDATE yukleme_detaylari 
            SET paket = %s 
            WHERE urun_id = %s 
            ORDER BY id DESC LIMIT 1
        """, (yeni_paket_miktari, urun_id))
        
        db.commit()
        flash("Stok bilgisi başarıyla güncellendi.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Hata: {str(e)}", "danger")
    finally:
        db.close()
        
    return redirect(url_for('depo'))

@app.route('/vardiyalar')
def vardiyalar():
    if 'user_id' not in session: return redirect(url_for('index'))
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM vardiyalar ORDER BY id DESC")
    liste = cursor.fetchall()
    db.close()
    return render_template('vardiyalar.html', vardiyalar=liste)

@app.route('/haftalik_uretim_raporu')
def haftalik_uretim_raporu():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    db = get_db_connection()
    cursor = db.cursor()
    
    # 1. Operatörler tablosundaki sütun ismini bulalım (ad mı ad_soyad mı?)
    cursor.execute("DESCRIBE operatorler")
    op_cols = [row['Field'] for row in cursor.fetchall()]
    op_name_field = 'ad_soyad' if 'ad_soyad' in op_cols else 'ad'
    
    # 2. Üretimler tablosunda vardiya sütunu var mı kontrol edelim (hata almamak için)
    cursor.execute("DESCRIBE uretimler")
    u_cols = [row['Field'] for row in cursor.fetchall()]
    
    # Veritabanında varsa o sütunu kullan, yoksa 'Belirtilmedi' yaz
    vardiya_sql = "u.vardiya" if 'vardiya' in u_cols else "'Belirtilmedi'"
    
    # 3. İstediğin sıralama ile güncel sorgu
    query = f"""
        SELECT 
            u.tarih AS 'Tarih', 
            p.urun_adi AS 'Ürün Bilgisi', 
            u.paket_sayisi AS 'Paket', 
            u.paket_ici_adet AS 'Paket İçi Adet', 
            u.toplam_adet AS 'Toplam Adet', 
            {vardiya_sql} AS 'Vardiya',
            o.{op_name_field} AS 'Operatör'
        FROM uretimler u
        LEFT JOIN urunler p ON u.urun_id = p.id
        LEFT JOIN operatorler o ON u.operator_id = o.id
        ORDER BY u.tarih DESC, u.id DESC
    """
    
    try:
        cursor.execute(query)
        veriler = cursor.fetchall()
        db.close()
    except Exception as e:
        if db: db.close()
        return f"Sorgu Hatası: {str(e)}"

    if not veriler:
        flash("Üretim verisi bulunamadı.", "warning")
        return redirect(url_for('uretim'))

    # Pandas ile Excel dosyası oluştur
    df = pd.DataFrame(veriler)
    
    # Sütunları istediğin sıraya zorla (Her ihtimale karşı)
    istenen_sira = ['Tarih', 'Ürün Bilgisi', 'Paket', 'Paket İçi Adet', 'Toplam Adet', 'Vardiya', 'Operatör']
    df = df[istenen_sira]
    
    # Dosya ismini oluştur
    dosya_adi = f"uretim_raporu_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    # Excel'e yaz ve gönder
    df.to_excel(dosya_adi, index=False)
    return send_file(dosya_adi, as_attachment=True, download_name=dosya_adi)

@app.route('/sevkiyat_raporu_indir')
def sevkiyat_raporu_indir():

    if 'user_id' not in session: return redirect(url_for('login'))
    
    # Yetki Kontrolü
    yetki = int(session.get('user_permissions', {}).get('sevkiyat', 0))
    if session.get('user_role') != 'Admin' and yetki < 4:
        flash("Bu raporu indirmek için yetkiniz yok.", "danger")
        return redirect(url_for('index'))
    
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        # 1. ADIM: MySQL'den yukleme_detaylari tablosunun gerçek sütunlarını öğreniyoruz
        cursor.execute("DESCRIBE yukleme_detaylari")
        columns = [row['Field'] for row in cursor.fetchall()]
        
        # Sayısal veri olabilecek tüm ihtimalleri kontrol et
        adet_col = None
        for col in ['miktar', 'adet', 'toplam_adet', 'paket_sayisi']:
            if col in columns:
                adet_col = f"yd.{col}"
                break
        
        if not adet_col:
            # Eğer yukarıdakiler yoksa tabloda id, yukleme_id, urun_id haricindeki ilk sütunu al
            adet_col = f"yd.{columns[3]}" if len(columns) > 3 else f"yd.{columns[-1]}"

        # 2. ADIM: Gerçek sütunla sorguyu çalıştır
        query = f"""
            SELECT 
                s.tarih AS 'Tarih', 
                m.musteri_adi AS 'Müşteri Adı', 
                p.urun_adi AS 'Ürün Adı', 
                {adet_col} AS 'Toplam Adet',
                s.arac_plakasi AS 'Plaka'
            FROM yukleme_detaylari yd
            JOIN sevkiyatlar s ON yd.yukleme_id = s.yukleme_id
            LEFT JOIN musteriler m ON yd.musteri_id = m.id
            LEFT JOIN urunler p ON yd.urun_id = p.id
            ORDER BY s.id DESC
        """
        
        cursor.execute(query)
        veriler = cursor.fetchall()
        db.close()
        
    except Exception as e:
        if db: db.close()
        return f"MySQL Bilgi Hatası: {str(e)}. Mevcut Sütunlar: {columns if 'columns' in locals() else 'Okunamadı'}"

    if not veriler:
        flash("Sevkiyat detayı bulunamadı.", "warning")
        return redirect(url_for('index'))

    # Excel oluşturma
    df = pd.DataFrame(veriler)
    dosya_adi = f"sevkiyat_raporu_{datetime.now().strftime('%Y%m%d')}.xlsx"
    df.to_excel(dosya_adi, index=False)

    return send_file(dosya_adi, as_attachment=True, download_name=dosya_adi)



@app.route('/depo_raporu_indir')
def depo_raporu_indir():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        # Sizin veritabanı yapınıza (app.py satır 450-500 arası) en uygun sorgu:
        query = """
            SELECT 
                u.urun_adi AS 'Ürün Adı',
                u.birim_kilo AS 'birim_kilo',
                (SELECT COALESCE(SUM(paket_sayisi), 0) FROM sayimlar WHERE urun_id = u.id) AS 'FİİLİ SAYIM',
                (SELECT COALESCE(SUM(paket_sayisi), 0) FROM uretimler WHERE urun_id = u.id) AS 'ÜRETİM',
                (SELECT COALESCE(SUM(paket), 0) FROM yukleme_detaylari WHERE urun_id = u.id) AS 'SEVKİYAT',
                (SELECT paket_ici_adet FROM uretimler WHERE urun_id = u.id ORDER BY olusturma_tarihi DESC LIMIT 1) AS 'PAKET İÇİ ADET'
            FROM urunler u
        """
        
        cursor.execute(query)
        veriler = cursor.fetchall()
        
        if not veriler:
            flash("Raporlanacak veri bulunamadı.", "warning")
            return redirect(url_for('depo'))

        # Veriyi işle
        df = pd.DataFrame(veriler)

        # Sayısal alanları temizle (Hata almamak için)
        for col in ['FİİLİ SAYIM', 'ÜRETİM', 'SEVKİYAT', 'birim_kilo', 'PAKET İÇİ ADET']:
            df[col] = pd.to_numeric(df[col]).fillna(0)

        # DEPO FORMÜLÜNÜ UYGULA: (Sayım + Üretim) - Sevkiyat
        df['KALAN (PKT)'] = (df['FİİLİ SAYIM'] + df['ÜRETİM']) - df['SEVKİYAT']
        
        # TOPLAM ADET HESABI: KALAN PAKET * PAKET İÇİ ADET
        df['TOPLAM ADET'] = df['KALAN (PKT)'] * df['PAKET İÇİ ADET']
        
        # TOPLAM KİLO HESABI: TOPLAM ADET * (BİRİM KİLO / PAKET İÇİ ADET)
        df['KİLO'] = df['TOPLAM ADET'] * (df['birim_kilo'] / df['PAKET İÇİ ADET'])

        # Excel Sütunlarını Düzenle
        final_cols = ['Ürün Adı', 'FİİLİ SAYIM', 'ÜRETİM', 'SEVKİYAT', 'KALAN (PKT)', 'PAKET İÇİ ADET', 'TOPLAM ADET', 'KİLO']
        rapor_df = df[final_cols]

        # Bellekte Excel oluştur
        from io import BytesIO
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            rapor_df.to_excel(writer, index=False, sheet_name='Depo_Stok_Raporu')
            
            # Sütunları genişlet (Okunabilirlik için)
            ws = writer.sheets['Depo_Stok_Raporu']
            for i, col in enumerate(final_cols):
                ws.column_dimensions[chr(65+i)].width = 20

        output.seek(0)
        return send_file(
            output, 
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
            as_attachment=True, 
            download_name=f"Depo_Stok_Raporu_{datetime.now().strftime('%Y%m%d')}.xlsx"
        )

    except Exception as e:
        flash(f"Rapor hatası: {str(e)}", "danger")
        return redirect(url_for('depo'))
    finally:
        db.close()


    if not veriler:
        flash("Depo hareketi bulunamadı.", "warning")
        return redirect(url_for('index'))

    # Excel oluşturma
    df = pd.DataFrame(veriler)
    dosya_adi = f"depo_stok_raporu_{datetime.now().strftime('%Y%m%d')}.xlsx"
    df.to_excel(dosya_adi, index=False)

    return send_file(dosya_adi, as_attachment=True, download_name=dosya_adi)
    


@app.route('/get_stok_durumu/<int:urun_id>')
def get_stok_durumu(urun_id):
    db = get_db_connection()
    cursor = db.cursor()
    
    # Veritabanındaki gerçek sütun ismini bulma (Dashboard'daki mantığın aynısı)
    cursor.execute("DESCRIBE urunler")
    columns = [row['Field'] for row in cursor.fetchall()]
    stok_col = next((col for col in ['stok_miktari', 'stok', 'miktar', 'toplam_stok', 'adet'] if col in columns), None)
    
    if stok_col:
        cursor.execute(f"SELECT {stok_col} FROM urunler WHERE id = %s", (urun_id,))
        urun = cursor.fetchone()
        db.close()
        if urun:
            return jsonify({'stok': urun[stok_col]})
    
    db.close()
    return jsonify({'stok': 0})

   
@app.route('/siparis_excel_aktar')
def siparis_excel_aktar():
    # 1. Oturum ve Yetki Kontrolü
    if 'user_id' not in session: 
        return redirect(url_for('login'))
    
    perms = session.get('user_permissions', {})
    if session.get('user_role') != 'Admin' and int(perms.get('siparis', 0)) < 1:
        flash("Bu işlem için yetkiniz yok!", "danger")
        return redirect(url_for('dashboard'))

    db = get_db_connection()
    if not db:
        flash("Veritabanı bağlantı hatası!", "danger")
        return redirect(url_for('siparisler'))
        
    cursor = db.cursor()
    
    try:
        # 2. İstediğin sütunları (Tarih, Müşteri, Ürün, Paket, Adet, Fiyat, Toplam) getiren SQL
        query = """
            SELECT 
                s.siparis_tarihi AS 'Tarih',
                m.musteri_adi AS 'Müşteri Adı',
                u.urun_adi AS 'Ürün Adı',
                sd.paket_sayisi AS 'Paket',
                sd.paket_ici_adet AS 'Paket İçi Adet',
                sd.miktar AS 'Toplam Adet',
                sd.birim_fiyat AS 'Birim Fiyatı',
                (sd.miktar * sd.birim_fiyat) AS 'Toplam Tutar'
            FROM siparis_detay sd
            JOIN siparisler s ON sd.siparis_id = s.id
            JOIN musteriler m ON s.musteri_id = m.id
            JOIN urunler u ON sd.urun_id = u.id
            ORDER BY s.id DESC
        """
        cursor.execute(query)
        veriler = cursor.fetchall()
        
        if not veriler:
            flash("Aktarılacak sipariş verisi bulunamadı.", "warning")
            return redirect(url_for('siparisler'))

        # 3. Pandas ile Excel oluşturma
        df = pd.DataFrame(veriler)
        
        # Tarih formatını Excel'de düzgün görünmesi için ayarlıyoruz
        if 'Tarih' in df.columns:
            df['Tarih'] = pd.to_datetime(df['Tarih']).dt.strftime('%Y-%m-%d')
        
        # Excel dosyasını bellekte (RAM) oluşturup kullanıcıya gönderiyoruz
        from io import BytesIO
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Siparis_Listesi')
        
        output.seek(0)
        
        dosya_adi = f"Siparis_Listesi_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=dosya_adi
        )
        
    except Exception as e:
        flash(f"Excel oluşturulurken bir hata oluştu: {str(e)}", "danger")
        return redirect(url_for('siparisler'))
    finally:
        db.close()


@app.route('/tablolar')
def tablolar():
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("SHOW TABLES")
    tablolar = cursor.fetchall()
    db.close()
    return str(tablolar) # Ekranda [{'Tables_in_stok_takip': 'urunler'}, ...] gibi bir liste görürsün.


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)





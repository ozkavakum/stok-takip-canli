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
            password=r'AVNS_AMj2EWle4W9yxJCGfAi', 
            database='defaultdb',
            port=13396,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            ssl={'ssl': {}} 
        )
        return connection
    except Exception as e:
        print(f"BAĞLANTI HATASI DETAYI: {e}")
        return None

# --- TABLO OLUŞTURMA VE BAŞLANGIÇ AYARLARI ---
conn = get_db_connection()
if conn:
    try:
        with conn.cursor() as cursor:
            # 1. Kullanıcılar Tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS kullanicilar (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    kullanici_adi VARCHAR(50) NOT NULL UNIQUE,
                    sifre VARCHAR(255) NOT NULL
                )
            """)
            
            # 2. Stoklar Tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stoklar (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    urun_adi VARCHAR(100) NOT NULL,
                    miktar INT DEFAULT 0,
                    birim VARCHAR(20),
                    kritik_seviye INT DEFAULT 5,
                    barkod VARCHAR(50) UNIQUE,
                    resim_yolu VARCHAR(255),
                    guncelleme_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)

            # 3. Siparişler Tablosu (Hata almamak için bunu da ekledik)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS siparisler (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    urun_adi VARCHAR(100),
                    adet INT,
                    musteri_adi VARCHAR(100),
                    durum VARCHAR(50) DEFAULT 'Beklemede',
                    tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 4. Varsayılan Admin Kullanıcısı Ekleme
            cursor.execute("INSERT IGNORE INTO kullanicilar (kullanici_adi, sifre) VALUES ('admin', '123456')")
            
            print(">>> VERİTABANI VE TABLOLAR HAZIR.")
    except Exception as e:
        print(f"Tablo oluşturma hatası: {e}")
    finally:
        conn.close()

# --- ROTALAR (ROUTES) ---

@app.route('/')
def index():
    if 'user' in session:
        return render_template('index.html')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_input = request.form.get('username')
        password_input = request.form.get('password')
        
        db = get_db_connection()
        if db:
            try:
                with db.cursor() as cursor:
                    cursor.execute("SELECT * FROM kullanicilar WHERE kullanici_adi = %s", (username_input,))
                    user = cursor.fetchone()
                    
                    if user and user['sifre'] == password_input:
                        session['user'] = username_input
                        return redirect(url_for('index'))
                    else:
                        flash("Hatalı kullanıcı adı veya şifre!", "danger")
            finally:
                db.close()
        else:
            flash("Veritabanı bağlantısı kurulamadı!", "danger")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/stoklar')
def stok_listesi():
    if 'user' not in session: return redirect(url_for('login'))
    
    db = get_db_connection()
    stoklar = []
    if db:
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT * FROM stoklar")
                stoklar = cursor.fetchall()
        finally:
            db.close()
    return render_template('stok_listesi.html', stoklar=stoklar)

@app.route('/stok_ekle', methods=['POST'])
def stok_ekle():
    if 'user' not in session: return redirect(url_for('login'))
    
    urun_adi = request.form.get('urun_adi')
    miktar = request.form.get('miktar')
    birim = request.form.get('birim')
    barkod = request.form.get('barkod')
    
    db = get_db_connection()
    if db:
        try:
            with db.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO stoklar (urun_adi, miktar, birim, barkod) 
                    VALUES (%s, %s, %s, %s)
                """, (urun_adi, miktar, birim, barkod))
            flash("Ürün başarıyla eklendi.", "success")
        except Exception as e:
            flash(f"Hata: {str(e)}", "danger")
        finally:
            db.close()
    return redirect(url_for('stok_listesi'))

@app.route('/siparisler')
def siparisler():
    if 'user' not in session: return redirect(url_for('login'))
    
    db = get_db_connection()
    siparis_listesi = []
    if db:
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT * FROM siparisler ORDER BY tarih DESC")
                siparis_listesi = cursor.fetchall()
        finally:
            db.close()
    return render_template('siparisler.html', siparisler=siparis_listesi)

@app.route('/export_excel')
def export_excel():
    if 'user' not in session: return redirect(url_for('login'))
    
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM siparisler")
            veriler = cursor.fetchall()
        
        if not veriler:
            flash("Dışa aktarılacak veri bulunamadı.", "warning")
            return redirect(url_for('siparisler'))

        df = pd.DataFrame(veriler)
        
        output = io.BytesIO()
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
        flash(f"Excel hatası: {str(e)}", "danger")
        return redirect(url_for('siparisler'))
    finally:
        db.close()

if __name__ == '__main__':
    app.run(debug=True)

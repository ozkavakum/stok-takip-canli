from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
import pymysql
from datetime import datetime
import pandas as pd
import io
import os

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
        print(f"BAĞLANTI HATASI: {e}")
        return None

# --- VERİTABANI BAŞLATMA (TABLOLARI OLUŞTURUR) ---
def init_db():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                # Kullanıcılar
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS kullanicilar (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        kullanici_adi VARCHAR(50) NOT NULL UNIQUE,
                        sifre VARCHAR(255) NOT NULL
                    )
                """)
                cursor.execute("INSERT IGNORE INTO kullanicilar (kullanici_adi, sifre) VALUES ('admin', '123456')")
                
                # Stoklar
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS stoklar (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        urun_adi VARCHAR(100) NOT NULL,
                        miktar INT DEFAULT 0,
                        birim VARCHAR(20),
                        barkod VARCHAR(50) UNIQUE,
                        kritik_seviye INT DEFAULT 5,
                        resim_yolu VARCHAR(255),
                        guncelleme_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    )
                """)

                # Siparişler
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
            print("Tablolar başarıyla kontrol edildi/oluşturuldu.")
        except Exception as e:
            print(f"Tablo oluşturma hatası: {e}")
        finally:
            conn.close()

init_db()

# --- SAYFALAR (ROUTES) ---

@app.route('/')
@app.route('/dashboard') # Hata veren kısım burasıydı, her ikisini de dashboard'a bağladık
def dashboard():
    if 'user' in session:
        return render_template('index.html')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        db = get_db_connection()
        if db:
            try:
                with db.cursor() as cursor:
                    cursor.execute("SELECT * FROM kullanicilar WHERE kullanici_adi = %s", (username,))
                    user = cursor.fetchone()
                    if user and user['sifre'] == password:
                        session['user'] = username
                        return redirect(url_for('dashboard'))
                    else:
                        flash("Hatalı kullanıcı adı veya şifre!", "danger")
            finally:
                db.close()
    return render_template('login.html')

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
                cursor.execute("INSERT INTO stoklar (urun_adi, miktar, birim, barkod) VALUES (%s, %s, %s, %s)", 
                               (urun_adi, miktar, birim, barkod))
            flash("Ürün eklendi!", "success")
        finally:
            db.close()
    return redirect(url_for('stok_listesi'))

@app.route('/siparisler')
def siparisler():
    if 'user' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    siparisler = []
    if db:
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT * FROM siparisler ORDER BY tarih DESC")
                siparisler = cursor.fetchall()
        finally:
            db.close()
    return render_template('siparisler.html', siparisler=siparisler)

@app.route('/export_excel')
def export_excel():
    if 'user' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM siparisler")
            veriler = cursor.fetchall()
        
        if veriler:
            df = pd.DataFrame(veriler)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            output.seek(0)
            return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             as_attachment=True, download_name="siparisler.xlsx")
    finally:
        db.close()
    return redirect(url_for('siparisler'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)

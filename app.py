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
        print(f"BAĞLANTI HATASI: {e}")
        return None

# --- TABLO OLUŞTURMA ---
def init_db():
    db = get_db_connection()
    if db:
        try:
            with db.cursor() as cursor:
                cursor.execute("CREATE TABLE IF NOT EXISTS kullanicilar (id INT AUTO_INCREMENT PRIMARY KEY, kullanici_adi VARCHAR(50) NOT NULL UNIQUE, sifre VARCHAR(255) NOT NULL)")
                cursor.execute("INSERT IGNORE INTO kullanicilar (kullanici_adi, sifre) VALUES ('admin', '123456')")
                cursor.execute("""CREATE TABLE IF NOT EXISTS stoklar (id INT AUTO_INCREMENT PRIMARY KEY, urun_adi VARCHAR(100) NOT NULL, miktar INT DEFAULT 0, birim VARCHAR(20), barkod VARCHAR(50) UNIQUE, kritik_seviye INT DEFAULT 5, resim_yolu VARCHAR(255), guncelleme_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS siparisler (id INT AUTO_INCREMENT PRIMARY KEY, urun_adi VARCHAR(100), adet INT, musteri_adi VARCHAR(100), durum VARCHAR(50) DEFAULT 'Beklemede', tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        finally:
            db.close()

init_db()

# --- ROTALAR (ENDPOINTLER) ---

@app.route('/')
@app.route('/index')
@app.route('/dashboard')
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
    if db and (with_db := db.cursor()):
        with with_db as cursor:
            cursor.execute("SELECT * FROM stoklar")
            stoklar = cursor.fetchall()
        db.close()
    return render_template('stok_listesi.html', stoklar=stoklar)

@app.route('/stok_ekle', methods=['GET', 'POST'])
def stok_ekle():
    if 'user' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        # Ekleme mantığı buraya gelecek
        return redirect(url_for('stok_listesi'))
    return render_template('stok_ekle.html') # Eğer dosyan varsa

@app.route('/siparisler')
def siparisler():
    if 'user' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    siparis_listesi = []
    if db and (with_db := db.cursor()):
        with with_db as cursor:
            cursor.execute("SELECT * FROM siparisler ORDER BY tarih DESC")
            siparis_listesi = cursor.fetchall()
        db.close()
    return render_template('siparisler.html', siparisler=siparis_listesi)

# HATA VEREN EKSİK ROTA:
@app.route('/mobil_barkod')
def mobil_barkod():
    if 'user' not in session: return redirect(url_for('login'))
    return "Mobil Barkod Tarama Sayfası Hazırlanıyor..."

@app.route('/export_excel')
def export_excel():
    if 'user' not in session: return redirect(url_for('login'))
    return "Excel dışa aktarma hazırlanıyor..."

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)

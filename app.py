from flask import Flask, render_template, request, redirect, url_for, session, flash
import pymysql
import os

app = Flask(__name__)
app.secret_key = "stok_takip_gizli_anahtar"

# --- VERİTABANI BAĞLANTISI ---
def get_db_connection():
    return pymysql.connect(
        host='mysql-baa3831-ozkavakumfinans-7da4.l.aivencloud.com',
        user='avnadmin',
        password=r'AVNS_AMj2EWle4W9yxJCGfAi', 
        database='defaultdb',
        port=13396,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        ssl={'ssl': {}} 
    )

# --- OTOMATİK TABLO KURULUMU ---
def init_db():
    try:
        db = get_db_connection()
        with db.cursor() as cursor:
            # Kullanıcılar tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS kullanicilar (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    kullanici_adi VARCHAR(50) NOT NULL UNIQUE,
                    sifre VARCHAR(255) NOT NULL
                )
            """)
            # Admin kullanıcısı (admin / 123456)
            cursor.execute("INSERT IGNORE INTO kullanicilar (kullanici_adi, sifre) VALUES ('admin', '123456')")
            
            # Stoklar tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stoklar (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    urun_adi VARCHAR(100) NOT NULL,
                    miktar INT DEFAULT 0,
                    birim VARCHAR(20),
                    barkod VARCHAR(50) UNIQUE
                )
            """)
        db.close()
        print("Veritabanı başarıyla hazırlandı.")
    except Exception as e:
        print(f"Veritabanı kurulum hatası: {e}")

# İlk çalıştırmada tabloları kur
init_db()

@app.route('/')
def index():
    if 'user' in session:
        return render_template('index.html')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            db = get_db_connection()
            with db.cursor() as cursor:
                cursor.execute("SELECT * FROM kullanicilar WHERE kullanici_adi = %s", (username,))
                user = cursor.fetchone()
                
                if user and user['sifre'] == password:
                    session['user'] = username
                    return redirect(url_for('index'))
                else:
                    flash("Hatalı kullanıcı adı veya şifre!")
            db.close()
        except Exception as e:
            return f"Veritabanı hatası: {str(e)}"
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)

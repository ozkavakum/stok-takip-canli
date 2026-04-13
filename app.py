from flask import Flask, render_template, request, redirect, url_for, session, flash
import pymysql

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

# --- TABLO KURULUMU ---
def init_db():
    try:
        db = get_db_connection()
        with db.cursor() as cursor:
            cursor.execute("CREATE TABLE IF NOT EXISTS kullanicilar (id INT AUTO_INCREMENT PRIMARY KEY, kullanici_adi VARCHAR(50) NOT NULL UNIQUE, sifre VARCHAR(255) NOT NULL)")
            cursor.execute("INSERT IGNORE INTO kullanicilar (kullanici_adi, sifre) VALUES ('admin', '123456')")
        db.close()
    except Exception as e:
        print(f"DB Kurulum Hatası: {e}")

init_db()

# --- SAYFALAR (ROUTES) ---

# Hata veren 'dashboard' burasıydı, ekledik:
@app.route('/')
@app.route('/dashboard')
def dashboard():
    if 'user' in session:
        return render_template('index.html')
    return redirect(url_for('login'))

# Layout.html içinde 'dashboard' ismi geçtiği için bu isimde bir fonksiyon şart:
@app.route('/index')
def index():
    return redirect(url_for('dashboard'))

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
                    return redirect(url_for('dashboard'))
                else:
                    flash("Hatalı kullanıcı adı veya şifre!")
            db.close()
        except Exception as e:
            return f"Veritabanı bağlantı hatası: {str(e)}"
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# Diğer sayfaların (stoklar vb.) hata vermemesi için boş taslaklar:
@app.route('/stoklar')
def stok_listesi():
    if 'user' not in session: return redirect(url_for('login'))
    return "Stok listesi sayfası yakında buraya eklenecek."

@app.route('/siparisler')
def siparisler():
    if 'user' not in session: return redirect(url_for('login'))
    return "Siparişler sayfası yakında buraya eklenecek."

if __name__ == '__main__':
    app.run(debug=True)

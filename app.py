from flask import Flask, render_template, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz
import sqlite3

app = Flask(__name__)
app.secret_key = 'vcx_flower_spa_secret'

def get_db():
    conn = sqlite3.connect('vcx.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    # 1. Bảng người dùng
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE,
        password TEXT,
        name TEXT,
        team TEXT,
        points_to_give INTEGER DEFAULT 200,
        points_received INTEGER DEFAULT 0
    )''')
    
    # 2. Bảng lịch sử tặng hoa
    conn.execute('''CREATE TABLE IF NOT EXISTS gift_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER,
        receiver_id INTEGER,
        gift_name TEXT,
        points INTEGER,
        message TEXT,
        created_at TEXT
    )''')
    
    # 3. Bảng danh sách SĐT được phép đăng ký (Do Admin cấp)
    conn.execute('''CREATE TABLE IF NOT EXISTS allowed_phones (
        phone TEXT PRIMARY KEY
    )''')
    
    # Tạo danh sách số điện thoại được duyệt (Bao gồm các user mẫu và 1 số mới để bạn test đăng ký)
    if conn.execute('SELECT COUNT(*) FROM allowed_phones').fetchone()[0] == 0:
        allowed_list = [
            ('0111111111',), ('0222222222',), ('0333333333',), 
            ('0444444444',), ('0555555555',), ('0666666666',),
            ('0999999999',) # Số này dành để test tính năng ĐĂNG KÝ mới
        ]
        conn.executemany('INSERT INTO allowed_phones (phone) VALUES (?)', allowed_list)
    
    # Tạo sẵn các user đã đăng ký
    if conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        default_pwd = generate_password_hash('123456')
        sample_users = [
            ('0111111111', default_pwd, 'Lê A', 'Team IT', 200, 250),
            ('0222222222', default_pwd, 'Trần B', 'Team Product', 200, 210),
            ('0333333333', default_pwd, 'Nguyễn C', 'Team HR', 200, 180),
            ('0444444444', default_pwd, 'Phạm D', 'Team Global', 200, 150),
            ('0555555555', default_pwd, 'Hoàng E', 'Team Administration', 200, 120),
            ('0666666666', default_pwd, 'Ngô F', 'Team Gift', 200, 90)
        ]
        conn.executemany('INSERT INTO users (phone, password, name, team, points_to_give, points_received) VALUES (?, ?, ?, ?, ?, ?)', sample_users)
        
    conn.commit()
    conn.close()

def reset_weekly_points():
    conn = get_db()
    conn.execute('UPDATE users SET points_to_give = 200')
    conn.commit()
    conn.close()

scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
scheduler.add_job(reset_weekly_points, 'cron', day_of_week='mon', hour=0, minute=1)
scheduler.start()

@app.route('/')
def index():
    return render_template('index.html')

# API ĐĂNG KÝ
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    phone = data.get('phone')
    password = data.get('password')
    name = data.get('name')
    team = data.get('team')
    
    conn = get_db()
    
    # Kiểm tra 1: Số điện thoại có trong danh sách Admin cấp không?
    is_allowed = conn.execute('SELECT * FROM allowed_phones WHERE phone = ?', (phone,)).fetchone()
    if not is_allowed:
        conn.close()
        return jsonify({'success': False, 'message': 'Số điện thoại của bạn không có trong danh sách được phép đăng ký.'})
    
    # Kiểm tra 2: Số điện thoại đã được đăng ký chưa?
    existing_user = conn.execute('SELECT * FROM users WHERE phone = ?', (phone,)).fetchone()
    if existing_user:
        conn.close()
        return jsonify({'success': False, 'message': 'Số điện thoại này đã được đăng ký.'})
    
    # Tạo tài khoản mới
    hashed_pwd = generate_password_hash(password)
    conn.execute('INSERT INTO users (phone, password, name, team, points_to_give, points_received) VALUES (?, ?, ?, ?, 200, 0)', 
                 (phone, hashed_pwd, name, team))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Đăng ký tài khoản thành công! Vui lòng đăng nhập.'})

# API ĐĂNG NHẬP
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE phone = ?', (data.get('phone'),)).fetchone()
    conn.close()
    if user and check_password_hash(user['password'], data.get('password')):
        session['user_id'] = user['id']
        return jsonify({'success': True, 'user': dict(user)})
    return jsonify({'success': False, 'message': 'Sai số điện thoại hoặc mật khẩu'})

# API ĐĂNG XUẤT
@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/auth', methods=['GET'])
def check_auth():
    if 'user_id' in session:
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        conn.close()
        if user:
            return jsonify({'loggedIn': True, 'user': dict(user)})
    return jsonify({'loggedIn': False})

@app.route('/api/heroes', methods=['GET'])
def heroes():
    if 'user_id' not in session: return jsonify([]), 401
    conn = get_db()
    users = conn.execute('SELECT id, name, team, points_received FROM users WHERE id != ? ORDER BY points_received DESC', (session['user_id'],)).fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    if 'user_id' not in session: return jsonify({}), 401
    conn = get_db()
    users = conn.execute('SELECT id, name, team, points_received FROM users ORDER BY points_received DESC').fetchall()
    conn.close()
    
    leaderboard_data = [dict(u) for u in users]
    my_rank = next((index + 1 for index, u in enumerate(leaderboard_data) if u['id'] == session['user_id']), 0)
    my_points = next((u['points_received'] for u in leaderboard_data if u['id'] == session['user_id']), 0)
    return jsonify({'leaderboard': leaderboard_data, 'my_rank': my_rank, 'my_points': my_points})

@app.route('/api/history', methods=['GET'])
def history():
    if 'user_id' not in session: return jsonify({}), 401
    conn = get_db()
    
    sent = conn.execute('''
        SELECT h.gift_name, h.points, h.message, h.created_at, u.name as other_name 
        FROM gift_history h 
        JOIN users u ON h.receiver_id = u.id 
        WHERE h.sender_id = ? 
        ORDER BY h.id DESC
    ''', (session['user_id'],)).fetchall()
    
    received = conn.execute('''
        SELECT h.gift_name, h.points, h.message, h.created_at, u.name as other_name 
        FROM gift_history h 
        JOIN users u ON h.sender_id = u.id 
        WHERE h.receiver_id = ? 
        ORDER BY h.id DESC
    ''', (session['user_id'],)).fetchall()
    
    conn.close()
    return jsonify({'sent': [dict(s) for s in sent], 'received': [dict(r) for r in received]})

@app.route('/api/gift', methods=['POST'])
def gift():
    if 'user_id' not in session: return jsonify({'success': False, 'message': 'Phiên đăng nhập hết hạn'}), 401
    data = request.json
    receiver_id = data.get('receiver_id')
    points = int(data.get('points'))
    gift_name = data.get('gift_name', 'Bó hoa')
    message = data.get('message', '').strip()
    
    conn = get_db()
    sender = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    if sender['points_to_give'] < points:
        conn.close()
        return jsonify({'success': False, 'message': "Bạn không đủ điểm để gửi bó hoa này!"})
        
    vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now_vn = datetime.now(vn_tz).strftime('%d/%m/%Y %H:%M:%S')
    
    conn.execute('UPDATE users SET points_to_give = points_to_give - ? WHERE id = ?', (points, sender['id']))
    conn.execute('UPDATE users SET points_received = points_received + ? WHERE id = ?', (points, receiver_id))
    conn.execute('''
        INSERT INTO gift_history (sender_id, receiver_id, gift_name, points, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (sender['id'], receiver_id, gift_name, points, message, now_vn))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True})

if __name__ == '__main__':
    init_db()
    app.run(debug=True)

import os

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
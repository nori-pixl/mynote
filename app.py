import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)

# --- 設定 ---
app.config['SECRET_KEY'] = 'my-secret-key-98765'
# 自分のPCで動かすので、プログラムと同じ場所に保存
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(UPLOAD_FOLDER, 'bbs.db')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- データベースモデル ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Thread(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    posts = db.relationship('Post', backref='thread', cascade="all, delete", lazy=True)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    thread_id = db.Column(db.Integer, db.ForeignKey('thread.id'), nullable=False)
    user = db.relationship('User', backref='posts')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ルート設定 ---

@app.route('/')
def index():
    threads = Thread.query.order_by(Thread.created_at.desc()).all()
    return render_template('index.html', threads=threads)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('その名前は使われています')
            return redirect(url_for('signup'))
        new_user = User(username=username, password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('ログイン失敗')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/create_thread', methods=['POST'])
@login_required
def create_thread():
    title = request.form.get('title')
    if title:
        new_thread = Thread(title=title)
        db.session.add(new_thread)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/thread/<int:thread_id>', methods=['GET', 'POST'])
def thread_detail(thread_id):
    thread = Thread.query.get_or_404(thread_id)
    if request.method == 'POST':
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        
        content = request.form.get('content')
        file = request.files.get('image')
        filename = None
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        new_post = Post(content=content, image_path=filename, user_id=current_user.id, thread_id=thread.id)
        db.session.add(new_post)
        db.session.commit()

        # Socket.IOで全ユーザーに通知（チャット風ライブ反映）
        socketio.emit('new_post', {
            'content': content,
            'username': current_user.username,
            'image': filename,
            'created_at': datetime.now().strftime('%Y/%m/%d %H:%M'),
            'post_id': new_post.id
        }, room=f"thread_{thread_id}")
        
        return redirect(url_for('thread_detail', thread_id=thread.id))
    
    # 古い順（昇順）に並べ替え
    posts = Post.query.filter_by(thread_id=thread_id).order_by(Post.created_at.asc()).all()
    return render_template('thread.html', thread=thread, posts=posts)

@app.route('/delete_thread/<int:thread_id>')
@login_required
def delete_thread(thread_id):
    thread = Thread.query.get_or_404(thread_id)
    db.session.delete(thread)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete_post/<int:post_id>')
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    thread_id = post.thread_id
    db.session.delete(post)
    db.session.commit()
    return redirect(url_for('thread_detail', thread_id=thread_id))

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Socket.IO の入室管理
@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    # Renderの環境変数からポートを取得、なければ5000
    port = int(os.environ.get("PORT", 5000))
    # Renderでは eventlet や gevent などのサーバーエンジンが必要
    socketio.run(app, host='0.0.0.0', port=port)

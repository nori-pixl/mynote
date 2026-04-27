import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'my-secret-key-safe'
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(UPLOAD_FOLDER, 'bbs.db')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Thread(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    posts = db.relationship('Post', backref='thread', cascade="all, delete")

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    thread_id = db.Column(db.Integer, db.ForeignKey('thread.id'))
    author = db.relationship('User', backref='user_posts')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    threads = Thread.query.order_by(Thread.created_at.desc()).all()
    return render_template('index.html', threads=threads)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        u = request.form.get('username'); p = request.form.get('password')
        if User.query.filter_by(username=u).first(): return redirect(url_for('signup'))
        db.session.add(User(username=u, password=generate_password_hash(p)))
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username'); p = request.form.get('password')
        user = User.query.filter_by(username=u).first()
        if user and check_password_hash(user.password, p):
            login_user(user); return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('index'))

@app.route('/create_thread', methods=['POST'])
@login_required
def create_thread():
    t = request.form.get('title')
    if t: db.session.add(Thread(title=t)); db.session.commit()
    return redirect(url_for('index'))

@app.route('/thread/<int:thread_id>', methods=['GET', 'POST'])
def thread_detail(thread_id):
    thread = Thread.query.get_or_404(thread_id)
    if request.method == 'POST':
        if not current_user.is_authenticated: return redirect(url_for('login'))
        c = request.form.get('content'); f = request.files.get('image'); fname = None
        if f and f.filename != '':
            fname = secure_filename(f.filename)
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        db.session.add(Post(content=c, image_path=fname, user_id=current_user.id, thread_id=thread.id))
        db.session.commit()
        return redirect(url_for('thread_detail', thread_id=thread.id))
    # 古い順（下へ追加）に並べ替え
    posts = Post.query.filter_by(thread_id=thread_id).order_by(Post.created_at.asc()).all()
    return render_template('thread.html', thread=thread, posts=posts)

@app.route('/delete_post/<int:post_id>')
@login_required
def delete_post(post_id):
    p = Post.query.get_or_404(post_id); tid = p.thread_id
    db.session.delete(p); db.session.commit()
    return redirect(url_for('thread_detail', thread_id=tid))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

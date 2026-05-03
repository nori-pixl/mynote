import os, random, string
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nori-final-bbs-2024'
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=365)

# --- データベース設定 ---
uri = os.environ.get('DATABASE_URL')
if uri and uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- モデル定義 ---
subs = db.Table('subs',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('classroom_id', db.Integer, db.ForeignKey('classroom.id'))
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    classrooms = db.relationship('Classroom', secondary=subs, backref=db.backref('members', lazy='dynamic'))

class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(10), unique=True, nullable=False)
    threads = db.relationship('Thread', backref='classroom_ref', cascade="all, delete")

class Thread(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classroom.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)
    posts = db.relationship('Post', backref='thread_ref', cascade="all, delete")

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    thread_id = db.Column(db.Integer, db.ForeignKey('thread.id'))
    parent_id = db.Column(db.Integer, db.ForeignKey('post.id'))
    author = db.relationship('User', backref='user_posts')
    replies = db.relationship('Post', backref=db.backref('parent', remote_side=[id]), cascade="all, delete")

@login_manager.user_loader
def load_user(id): return User.query.get(int(id))

# --- ルート ---
@app.route('/')
@login_required
def index(): return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        u, p = request.form.get('username'), request.form.get('password')
        if User.query.filter_by(username=u).first(): return redirect(url_for('signup'))
        new_user = User(username=u, password=generate_password_hash(p))
        pub = Classroom.query.filter_by(code='PUBLIC').first()
        if not pub:
            pub = Classroom(name='🌍 全員用ロビー', code='PUBLIC'); db.session.add(pub); db.session.flush()
        new_user.classrooms.append(pub); db.session.add(new_user); db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form.get('username'), request.form.get('password')
        user = User.query.filter_by(username=u).first()
        if user and check_password_hash(user.password, p):
            login_user(user, remember=True); return redirect(url_for('index'))
        return render_template('login.html', login_failed=True)
    return render_template('login.html')

@app.route('/class/<int:class_id>')
@login_required
def class_view(class_id):
    target = Classroom.query.get_or_404(class_id)
    threads = Thread.query.filter_by(class_id=class_id).order_by(Thread.created_at.desc()).all()
    return render_template('class_view.html', target_class=target, threads=threads)

@app.route('/thread/<int:thread_id>', methods=['GET', 'POST'])
@login_required
def thread_detail(thread_id):
    thread = Thread.query.get_or_404(thread_id)
    post_count = Post.query.filter_by(thread_id=thread_id).count()
    if request.method == 'POST':
        if post_count >= 500: return redirect(url_for('thread_detail', thread_id=thread.id))
        c, p_id = request.form.get('content'), request.form.get('parent_id')
        db.session.add(Post(content=c, user_id=current_user.id, thread_id=thread.id, parent_id=p_id if p_id else None))
        db.session.commit(); return redirect(url_for('thread_detail', thread_id=thread.id))
    posts = Post.query.filter_by(thread_id=thread_id, parent_id=None).order_by(Post.created_at.asc()).all()
    return render_template('thread.html', thread=thread, posts=posts, post_count=post_count)

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('login'))

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))

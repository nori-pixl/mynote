import os, random, string
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nori-class-list-secret'
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(UPLOAD_FOLDER, 'bbs.db')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- データベースモデル ---

# ユーザーとクラスを紐付けるテーブル
subs = db.Table('subs',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('classroom_id', db.Integer, db.ForeignKey('classroom.id'))
)

class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    code = db.Column(db.String(10), unique=True, nullable=False)
    threads = db.relationship('Thread', backref='classroom', cascade="all, delete")

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    # 参加しているクラスのリスト
    classrooms = db.relationship('Classroom', secondary=subs, backref=db.backref('members', lazy='dynamic'))

class Thread(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classroom.id'))
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

class Reaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'))

@login_manager.user_loader
def load_user(id): return User.query.get(int(id))

# --- ルート設定 ---

@app.route('/')
@login_required
def index():
    # 自分のクラスリストを表示
    return render_template('index.html', Reaction=Reaction)

@app.route('/class/<int:class_id>')
@login_required
def class_view(class_id):
    target_class = Classroom.query.get_or_404(class_id)
    if target_class not in current_user.classrooms:
        return "アクセス権がありません", 403
    threads = Thread.query.filter_by(class_id=class_id).order_by(Thread.created_at.desc()).all()
    return render_template('class_view.html', target_class=target_class, threads=threads)

@app.route('/manage_class', methods=['POST'])
@login_required
def manage_class():
    action = request.form.get('action')
    if action == 'create':
        name = request.form.get('name')
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        new_class = Classroom(name=name, code=code)
        current_user.classrooms.append(new_class)
        db.session.add(new_class)
        db.session.commit()
        flash(f'クラス作成完了！コード: {code}')
    elif action == 'join':
        code = request.form.get('code').upper()
        target = Classroom.query.filter_by(code=code).first()
        if target:
            if target not in current_user.classrooms:
                current_user.classrooms.append(target)
                db.session.commit()
            else:
                flash('すでに参加しています')
        else:
            flash('コードが違います')
    return redirect(url_for('index'))

@app.route('/create_thread/<int:class_id>', methods=['POST'])
@login_required
def create_thread(class_id):
    t = request.form.get('title')
    if t:
        db.session.add(Thread(title=t, class_id=class_id))
        db.session.commit()
    return redirect(url_for('class_view', class_id=class_id))

# --- 他のルート（signup, login, thread_detail, react等）は前回のものをそのまま使用 ---
# ※ thread_detail内の class_id チェックだけ current_user.classrooms を使うように修正
# -------------------------------------------------------------------------
# ... (中略: signup, login, logout, uploads 等の基本機能) ...

# --- app.py の signup 関数を修正 ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        u = request.form.get('username'); p = request.form.get('password')
        if User.query.filter_by(username=u).first(): return redirect(url_for('signup'))
        
        # 新しいユーザーを作成
        new_user = User(username=u, password=generate_password_hash(p))
        
        # 「全員用」という名前のクラスを探す、なければ作る
        public_class = Classroom.query.filter_by(code='PUBLIC').first()
        if not public_class:
            public_class = Classroom(name='全員掲示板（ロビー）', code='PUBLIC')
            db.session.add(public_class)
            db.session.flush()
        
        # ユーザーを全員用クラスに所属させる
        new_user.classrooms.append(public_class)
        
        db.session.add(new_user)
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

@app.route('/thread/<int:thread_id>', methods=['GET', 'POST'])
@login_required
def thread_detail(thread_id):
    thread = Thread.query.get_or_404(thread_id)
    if thread.classroom not in current_user.classrooms: return "Access Denied", 403
    if request.method == 'POST':
        c = request.form.get('content'); f = request.files.get('image'); fname = None
        if f and f.filename != '':
            fname = secure_filename(f.filename); f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        db.session.add(Post(content=c, image_path=fname, user_id=current_user.id, thread_id=thread.id))
        db.session.commit()
        return redirect(url_for('thread_detail', thread_id=thread.id))
    posts = Post.query.filter_by(thread_id=thread_id).order_by(Post.created_at.asc()).all()
    return render_template('thread.html', thread=thread, posts=posts, Reaction=Reaction)

@app.route('/react/<int:post_id>/<string:reac_type>')
@login_required
def react(post_id, reac_type):
    existing = Reaction.query.filter_by(user_id=current_user.id, post_id=post_id, type=reac_type).first()
    if existing: db.session.delete(existing)
    else: db.session.add(Reaction(user_id=current_user.id, post_id=post_id, type=reac_type))
    db.session.commit()
    return redirect(request.referrer)

@app.route('/delete_post/<int:post_id>')
@login_required
def delete_post(post_id):
    p = Post.query.get_or_404(post_id); tid = p.thread_id
    db.session.delete(p); db.session.commit()
    return redirect(url_for('thread_detail', thread_id=tid))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('index'))

with app.app_context(): db.create_all()
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

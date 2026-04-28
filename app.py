import os, random, string
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nori-bbs-stable-key'

# 保存先
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(UPLOAD_FOLDER, 'bbs.db')
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- データベースモデル ---
subs = db.Table('subs',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('classroom_id', db.Integer, db.ForeignKey('classroom.id'))
)

class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    code = db.Column(db.String(10), unique=True, nullable=False)
    threads = db.relationship('Thread', backref='classroom_ref', cascade="all, delete")

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    classrooms = db.relationship('Classroom', secondary=subs, backref=db.backref('members', lazy='dynamic'))

class Thread(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classroom.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)
    posts = db.relationship('Post', backref='thread_ref', cascade="all, delete")

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    thread_id = db.Column(db.Integer, db.ForeignKey('thread.id'))
    author = db.relationship('User', backref='user_posts')
    reactions = db.relationship('Reaction', backref='post_ref', cascade="all, delete")

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
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        u = request.form.get('username'); p = request.form.get('password')
        if User.query.filter_by(username=u).first(): return redirect(url_for('signup'))
        new_user = User(username=u, password=generate_password_hash(p))
        pub = Classroom.query.filter_by(code='PUBLIC').first()
        if not pub:
            pub = Classroom(name='全員掲示板', code='PUBLIC')
            db.session.add(pub); db.session.flush()
        new_user.classrooms.append(pub)
        db.session.add(new_user); db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form.get('username'), request.form.get('password')
        user = User.query.filter_by(username=u).first()
        if user and check_password_hash(user.password, p):
            login_user(user); return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/manage_class', methods=['POST'])
@login_required
def manage_class():
    action = request.form.get('action')
    if action == 'create':
        name = request.form.get('name')
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        new_class = Classroom(name=name, code=code)
        current_user.classrooms.append(new_class)
        db.session.add(new_class); db.session.commit()
    elif action == 'join':
        code = request.form.get('code').upper()
        target = Classroom.query.filter_by(code=code).first()
        if target and target not in current_user.classrooms:
            current_user.classrooms.append(target); db.session.commit()
    return redirect(url_for('index'))

@app.route('/class/<int:class_id>')
@login_required
def class_view(class_id):
    target = Classroom.query.get_or_404(class_id)
    if target not in current_user.classrooms: return "Access Denied", 403
    threads = Thread.query.filter_by(class_id=class_id).order_by(Thread.created_at.desc()).all()
    return render_template('class_view.html', target_class=target, threads=threads)

@app.route('/thread/<int:thread_id>', methods=['GET', 'POST'])
@login_required
def thread_detail(thread_id):
    thread = Thread.query.get_or_404(thread_id)
    post_count = Post.query.filter_by(thread_id=thread_id).count()
    if request.method == 'POST':
        if post_count >= 500: return redirect(url_for('thread_detail', thread_id=thread_id))
        c, f = request.form.get('content'), request.files.get('image'); fname = None
        if f and f.filename != '':
            fname = secure_filename(f.filename); f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        db.session.add(Post(content=c, image_path=fname, user_id=current_user.id, thread_id=thread.id))
        db.session.commit(); return redirect(url_for('thread_detail', thread_id=thread.id))
    posts = Post.query.filter_by(thread_id=thread_id).order_by(Post.created_at.asc()).all()
    return render_template('thread.html', thread=thread, posts=posts, Reaction=Reaction, post_count=post_count)

@app.route('/delete_post/<int:post_id>')
@login_required
def delete_post(post_id):
    p = Post.query.get_or_404(post_id); tid = p.thread_id
    db.session.delete(p); db.session.commit(); return redirect(url_for('thread_detail', thread_id=tid))

@app.route('/delete_thread/<int:thread_id>')
@login_required
def delete_thread(thread_id):
    t = Thread.query.get_or_404(thread_id); cid = t.class_id
    db.session.delete(t); db.session.commit(); return redirect(url_for('class_view', class_id=cid))

@app.route('/delete_class/<int:class_id>')
@login_required
def delete_class(class_id):
    c = Classroom.query.get_or_404(class_id)
    if c.code != 'PUBLIC': db.session.delete(c); db.session.commit()
    return redirect(url_for('index'))

@app.route('/react/<int:post_id>/<string:reac_type>')
@login_required
def react(post_id, reac_type):
    ex = Reaction.query.filter_by(user_id=current_user.id, post_id=post_id, type=reac_type).first()
    if ex: db.session.delete(ex)
    else: db.session.add(Reaction(user_id=current_user.id, post_id=post_id, type=reac_type))
    db.session.commit(); return redirect(request.referrer)

@app.route('/uploads/<filename>')
def uploaded_file(filename): return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('login'))

with app.app_context(): db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

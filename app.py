# app.py
import os
from flask import Flask, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

# Инициализация Flask приложения
app = Flask(__name__)

# Базовая конфигурация
app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///notes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация базы данных
db = SQLAlchemy(app)

# --- ИНИЦИАЛИЗАЦИЯ FLASK-LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему'
login_manager.login_message_category = 'warning'

# --- ЗАГРУЗЧИК ПОЛЬЗОВАТЕЛЯ ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- МОДЕЛИ БАЗЫ ДАННЫХ ---

class User(db.Model, UserMixin):
    """Модель пользователя"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.relationship('Note', backref='author', lazy=True)
    
    def set_password(self, password):
        """Хеширование пароля"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Проверка пароля"""
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'


class Category(db.Model):
    """Модель категории"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(20), default='primary')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notes = db.relationship('Note', backref='category_ref', lazy=True)
    
    def __repr__(self):
        return f'<Category {self.name}>'


class Note(db.Model):
    """Модель заметки"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    is_pinned = db.Column(db.Boolean, default=False)
    tags = db.Column(db.String(200))
    
    def __repr__(self):
        return f'<Note {self.title}>'

# --- МАРШРУТЫ ---

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Регистрация пользователя"""
    from flask import request
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Валидация
        if not all([username, email, password, confirm_password]):
            flash('Все поля обязательны для заполнения', 'danger')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('Пароли не совпадают', 'danger')
            return redirect(url_for('register'))
        
        # Проверка существования пользователя
        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email уже зарегистрирован', 'danger')
            return redirect(url_for('register'))
        
        # Создание пользователя
        user = User(username=username, email=email)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Регистрация успешна! Войдите в систему', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Вход в систему"""
    from flask import request
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Вход выполнен успешно!', 'success')
            return redirect(url_for('dashboard'))
        
        flash('Неверное имя пользователя или пароль', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Выход из системы"""
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

# маршруты для заметок

@app.route('/dashboard')
@login_required
def dashboard():
    """Личный кабинет с поиском и фильтрацией"""
    # Получаем параметры из GET запроса
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', 'all')
    show_archived = request.args.get('archived', 'false') == 'true'
    sort_by = request.args.get('sort', 'updated')  # updated, created, title
    
    # Базовый запрос для заметок текущего пользователя
    query = Note.query.filter_by(user_id=current_user.id)
    
    # Фильтрация по архивированным
    if not show_archived:
        query = query.filter_by(is_archived=False)
    
    # Поиск по тексту
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(
            db.or_(
                Note.title.ilike(search_term),
                Note.content.ilike(search_term),
                Note.tags.ilike(search_term)
            )
        )
    
    # Фильтрация по категории
    if category_filter != 'all':
        if category_filter == 'uncategorized':
            query = query.filter_by(category_id=None)
        else:
            # Проверяем, что категория принадлежит пользователю
            category = Category.query.get(category_filter)
            if category and category.user_id == current_user.id:
                query = query.filter_by(category_id=category_filter)
    
    # Сортировка
    if sort_by == 'created':
        query = query.order_by(Note.created_at.desc())
    elif sort_by == 'title':
        query = query.order_by(Note.title.asc())
    else:  # updated (по умолчанию)
        query = query.order_by(Note.updated_at.desc())
    
    # Сначала закрепленные, потом остальные
    notes = query.all()
    notes.sort(key=lambda x: (not x.is_pinned, x.updated_at), reverse=True)
    
    # Получаем категории пользователя
    categories = Category.query.filter_by(user_id=current_user.id).all()
    
    # Статистика
    total_notes = Note.query.filter_by(user_id=current_user.id).count()
    pinned_notes = Note.query.filter_by(
        user_id=current_user.id, 
        is_pinned=True,
        is_archived=False
    ).count()
    archived_notes = Note.query.filter_by(
        user_id=current_user.id, 
        is_archived=True
    ).count()
    
    return render_template('dashboard.html', 
                         notes=notes, 
                         categories=categories,
                         Category=Category,
                         search_query=search_query,
                         category_filter=category_filter,
                         show_archived=show_archived,
                         sort_by=sort_by,
                         total_notes=total_notes,
                         pinned_notes=pinned_notes,
                         archived_notes=archived_notes)

@app.route('/dashboard')
@login_required
def dashboard():
    """Личный кабинет - список всех заметок"""
    # Получаем заметки текущего пользователя
    notes = Note.query.filter_by(user_id=current_user.id).order_by(
        Note.is_pinned.desc(),  # Сначала закрепленные
        Note.updated_at.desc()  # Потом по дате обновления
    ).all()
    
    # Получаем категории пользователя
    categories = Category.query.filter_by(user_id=current_user.id).all()
    
    return render_template('dashboard.html', 
                         notes=notes, 
                         categories=categories,
                         Category=Category)  # Передаем класс Category в шаблон


@app.route('/notes/new', methods=['GET', 'POST'])
@login_required
def new_note():
    """Создание новой заметки"""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        category_id = request.form.get('category_id')
        tags = request.form.get('tags', '').strip()
        
        # Валидация
        if not title:
            flash('Заголовок обязателен', 'danger')
            return redirect(url_for('new_note'))
        
        # Создаем заметку
        note = Note(
            title=title,
            content=content,
            user_id=current_user.id,
            tags=tags
        )
        
        # Если выбрана категория
        if category_id:
            # Проверяем, что категория принадлежит пользователю
            category = Category.query.get(category_id)
            if category and category.user_id == current_user.id:
                note.category_id = category_id
        
        db.session.add(note)
        db.session.commit()
        
        flash('Заметка успешно создана!', 'success')
        return redirect(url_for('dashboard'))
    
    # GET запрос - показываем форму
    categories = Category.query.filter_by(user_id=current_user.id).all()
    return render_template('note_form.html', 
                         note=None, 
                         categories=categories,
                         action='create')


@app.route('/notes/<int:note_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_note(note_id):
    """Редактирование заметки"""
    note = Note.query.get_or_404(note_id)
    
    # Проверяем, что заметка принадлежит текущему пользователю
    if note.user_id != current_user.id:
        flash('У вас нет доступа к этой заметке', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        note.title = request.form.get('title', '').strip()
        note.content = request.form.get('content', '').strip()
        note.category_id = request.form.get('category_id')
        note.tags = request.form.get('tags', '').strip()
        note.updated_at = datetime.utcnow()  # Обновляем время
        
        if not note.title:
            flash('Заголовок обязателен', 'danger')
            return redirect(url_for('edit_note', note_id=note_id))
        
        db.session.commit()
        flash('Заметка успешно обновлена!', 'success')
        return redirect(url_for('dashboard'))
    
    # GET запрос - показываем форму редактирования
    categories = Category.query.filter_by(user_id=current_user.id).all()
    return render_template('note_form.html', 
                         note=note, 
                         categories=categories,
                         action='edit')


@app.route('/notes/<int:note_id>/delete', methods=['POST'])
@login_required
def delete_note(note_id):
    """Удаление заметки"""
    note = Note.query.get_or_404(note_id)
    
    if note.user_id != current_user.id:
        flash('У вас нет доступа к этой заметке', 'danger')
        return redirect(url_for('dashboard'))
    
    db.session.delete(note)
    db.session.commit()
    
    flash('Заметка успешно удалена!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/notes/<int:note_id>/pin', methods=['POST'])
@login_required
def pin_note(note_id):
    """Закрепление/открепление заметки"""
    note = Note.query.get_or_404(note_id)
    
    if note.user_id != current_user.id:
        flash('У вас нет доступа к этой заметке', 'danger')
        return redirect(url_for('dashboard'))
    
    # Переключаем состояние закрепления
    note.is_pinned = not note.is_pinned
    db.session.commit()
    
    action = "закреплена" if note.is_pinned else "откреплена"
    flash(f'Заметка "{note.title}" {action}!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/notes/<int:note_id>/archive', methods=['POST'])
@login_required
def archive_note(note_id):
    """Архивация/восстановление заметки"""
    note = Note.query.get_or_404(note_id)
    
    if note.user_id != current_user.id:
        flash('У вас нет доступа к этой заметке', 'danger')
        return redirect(url_for('dashboard'))
    
    # Переключаем состояние архивации
    note.is_archived = not note.is_archived
    
    # Если архивируем - снимаем закрепление
    if note.is_archived:
        note.is_pinned = False
    
    db.session.commit()
    
    action = "архивирована" if note.is_archived else "восстановлена из архива"
    flash(f'Заметка "{note.title}" {action}!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/notes/<int:note_id>')
@login_required
def view_note(note_id):
    """Просмотр отдельной заметки"""
    note = Note.query.get_or_404(note_id)
    
    if note.user_id != current_user.id:
        flash('У вас нет доступа к этой заметке', 'danger')
        return redirect(url_for('dashboard'))
    
    return render_template('view_note.html', note=note)

@app.route('/notes/batch-action', methods=['POST'])
@login_required
def batch_action():
    """Массовые действия с заметками"""
    action = request.form.get('action')
    note_ids = request.form.getlist('note_ids')
    
    if not note_ids:
        flash('Не выбрано ни одной заметки', 'warning')
        return redirect(url_for('dashboard'))
    
    notes = Note.query.filter(
        Note.id.in_(note_ids),
        Note.user_id == current_user.id
    ).all()
    
    if not notes:
        flash('Заметки не найдены', 'danger')
        return redirect(url_for('dashboard'))
    
    count = 0
    for note in notes:
        if action == 'archive':
            note.is_archived = True
            note.is_pinned = False
            count += 1
        elif action == 'unarchive':
            note.is_archived = False
            count += 1
        elif action == 'pin':
            note.is_pinned = True
            count += 1
        elif action == 'unpin':
            note.is_pinned = False
            count += 1
        elif action == 'delete':
            db.session.delete(note)
            count += 1
    
    db.session.commit()
    
    actions = {
        'archive': 'архивировано',
        'unarchive': 'восстановлено из архива',
        'pin': 'закреплено',
        'unpin': 'откреплено',
        'delete': 'удалено'
    }
    
    flash(f'{count} заметок {actions.get(action, "обработано")}!', 'success')
    return redirect(url_for('dashboard'))

# маршруты для категорий

@app.route('/categories/new', methods=['POST'])
@login_required
def new_category():
    """Создание новой категории"""
    name = request.form.get('name', '').strip()
    color = request.form.get('color', 'primary')
    
    if not name:
        flash('Название категории обязательно', 'danger')
        return redirect(url_for('dashboard'))
    
    # Проверяем, нет ли уже такой категории
    existing = Category.query.filter_by(
        name=name, 
        user_id=current_user.id
    ).first()
    
    if existing:
        flash('Категория с таким названием уже существует', 'warning')
        return redirect(url_for('dashboard'))
    
    category = Category(
        name=name,
        color=color,
        user_id=current_user.id
    )
    
    db.session.add(category)
    db.session.commit()
    
    flash(f'Категория "{name}" создана!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/categories/<int:category_id>/delete', methods=['POST'])
@login_required
def delete_category(category_id):
    """Удаление категории"""
    category = Category.query.get_or_404(category_id)
    
    if category.user_id != current_user.id:
        flash('У вас нет доступа к этой категории', 'danger')
        return redirect(url_for('dashboard'))
    
    # Переносим заметки в "без категории"
    notes_with_category = Note.query.filter_by(
        category_id=category_id,
        user_id=current_user.id
    ).all()
    
    for note in notes_with_category:
        note.category_id = None
    
    db.session.delete(category)
    db.session.commit()
    
    flash(f'Категория "{category.name}" удалена', 'success')
    return redirect(url_for('dashboard'))

with app.app_context():
    db.create_all()
    print("✅ База данных создана!")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Создаем таблицы в БД
    app.run(debug=True)

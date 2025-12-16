# app.py
import os
from flask import Flask, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import timedelta
import secrets

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

class PasswordResetToken(db.Model):
    """Токен для сброса пароля"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    
    user = db.relationship('User', backref='reset_tokens')
    
    def is_valid(self):
        """Проверка валидности токена"""
        return (datetime.utcnow() < self.expires_at and 
                not self.is_used)
    
    def __repr__(self):
        return f'<PasswordResetToken {self.token[:10]}...>'

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

@app.route('/api/stats')
@login_required
def get_stats():
    """API для получения статистики"""
    # Основная статистика
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
    
    # Статистика по категориям
    categories = Category.query.filter_by(user_id=current_user.id).all()
    category_stats = []
    
    for category in categories:
        notes_count = Note.query.filter_by(
            category_id=category.id,
            user_id=current_user.id,
            is_archived=False
        ).count()
        
        category_stats.append({
            'name': category.name,
            'color': category.color,
            'count': notes_count
        })
    
    # Последние 5 заметок
    recent_notes = Note.query.filter_by(
        user_id=current_user.id,
        is_archived=False
    ).order_by(Note.updated_at.desc()).limit(5).all()
    
    recent = [{
        'id': note.id,
        'title': note.title,
        'updated_at': note.updated_at.strftime('%d.%m.%Y %H:%M')
    } for note in recent_notes]
    
    return {
        'success': True,
        'data': {
            'total_notes': total_notes,
            'pinned_notes': pinned_notes,
            'archived_notes': archived_notes,
            'category_stats': category_stats,
            'recent_notes': recent
        }
    }

@app.route('/stats')
@login_required
def stats_page():
    """Страница с подробной статистикой"""
    # Получаем данные для графиков
    notes_by_month = []
    
    # Заметки за последние 6 месяцев
    from datetime import datetime, timedelta
    import calendar
    
    for i in range(5, -1, -1):
        month_start = datetime.utcnow().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=30*i)
        
        month_end = month_start + timedelta(days=32)
        month_end = month_end.replace(day=1) - timedelta(days=1)
        
        count = Note.query.filter(
            Note.user_id == current_user.id,
            Note.created_at >= month_start,
            Note.created_at <= month_end
        ).count()
        
        notes_by_month.append({
            'month': calendar.month_name[month_start.month],
            'count': count
        })
    
    # Топ тегов
    all_tags = {}
    notes = Note.query.filter_by(user_id=current_user.id).all()
    
    for note in notes:
        if note.tags:
            for tag in note.tags.split(','):
                tag_clean = tag.strip().lower()
                if tag_clean:
                    all_tags[tag_clean] = all_tags.get(tag_clean, 0) + 1
    
    top_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # Статистика по времени суток
    import random  # Временные данные для демо
    hourly_stats = [random.randint(0, 10) for _ in range(24)]
    
    return render_template('stats.html',
                         notes_by_month=notes_by_month,
                         top_tags=top_tags,
                         hourly_stats=hourly_stats)

@app.route('/export/notes')
@login_required
def export_notes():
    """Экспорт заметок в формате Markdown"""
    import io
    from flask import send_file
    
    # Получаем заметки пользователя
    notes = Note.query.filter_by(
        user_id=current_user.id,
        is_archived=False
    ).order_by(Note.created_at.desc()).all()
    
    # Создаем Markdown документ
    output = io.StringIO()
    
    output.write(f"# Экспорт заметок из NoteFlow\n\n")
    output.write(f"Пользователь: {current_user.username}\n")
    output.write(f"Дата экспорта: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}\n")
    output.write(f"Всего заметок: {len(notes)}\n\n")
    
    for note in notes:
        output.write(f"## {note.title}\n\n")
        
        if note.category_id:
            category = Category.query.get(note.category_id)
            if category:
                output.write(f"**Категория:** {category.name}\n\n")
        
        if note.tags:
            output.write(f"**Теги:** {note.tags}\n\n")
        
        output.write(f"**Создано:** {note.created_at.strftime('%d.%m.%Y %H:%M')}\n")
        output.write(f"**Обновлено:** {note.updated_at.strftime('%d.%m.%Y %H:%M')}\n\n")
        
        if note.content:
            output.write(f"{note.content}\n")
        
        output.write(f"\n---\n\n")
    
    # Конвертируем в bytes для отправки
    content = output.getvalue().encode('utf-8')
    output.close()
    
    return send_file(
        io.BytesIO(content),
        mimetype='text/markdown',
        as_attachment=True,
        download_name=f'noteflow_export_{datetime.utcnow().strftime("%Y%m%d")}.md'
    )

@app.route('/profile')
@login_required
def profile():
    """Страница профиля пользователя"""
    # Статистика пользователя
    total_notes = Note.query.filter_by(user_id=current_user.id).count()
    pinned_notes = Note.query.filter_by(
        user_id=current_user.id, 
        is_pinned=True,
        is_archived=False
    ).count()
    
    # Последняя активность
    last_note = Note.query.filter_by(
        user_id=current_user.id
    ).order_by(Note.updated_at.desc()).first()
    
    return render_template('profile.html',
                         total_notes=total_notes,
                         pinned_notes=pinned_notes,
                         last_note=last_note)


@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    """Обновление профиля пользователя"""
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    
    if not username or not email:
        flash('Все поля обязательны для заполнения', 'danger')
        return redirect(url_for('profile'))
    
    # Проверяем уникальность username
    if username != current_user.username:
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Имя пользователя уже занято', 'danger')
            return redirect(url_for('profile'))
    
    # Проверяем уникальность email
    if email != current_user.email:
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            flash('Email уже зарегистрирован', 'danger')
            return redirect(url_for('profile'))
    
    # Обновляем данные
    current_user.username = username
    current_user.email = email
    db.session.commit()
    
    flash('Профиль успешно обновлен!', 'success')
    return redirect(url_for('profile'))


@app.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    """Изменение пароля"""
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    # Проверка текущего пароля
    if not current_user.check_password(current_password):
        flash('Текущий пароль неверен', 'danger')
        return redirect(url_for('profile'))
    
    # Проверка нового пароля
    if new_password != confirm_password:
        flash('Новые пароли не совпадают', 'danger')
        return redirect(url_for('profile'))
    
    if len(new_password) < 6:
        flash('Пароль должен содержать минимум 6 символов', 'danger')
        return redirect(url_for('profile'))
    
    # Устанавливаем новый пароль
    current_user.set_password(new_password)
    db.session.commit()
    
    flash('Пароль успешно изменен!', 'success')
    return redirect(url_for('profile'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Запрос на сброс пароля"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Создаем токен сброса пароля
            token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(hours=24)
            
            reset_token = PasswordResetToken(
                user_id=user.id,
                token=token,
                expires_at=expires_at
            )
            
            db.session.add(reset_token)
            db.session.commit()
            
            # В реальном приложении здесь была бы отправка email
            # Для демо просто показываем ссылку
            reset_url = url_for('reset_password', token=token, _external=True)
            
            flash(
                f'Ссылка для сброса пароля: {reset_url}<br>'
                f'В реальном приложении это будет отправлено на email.',
                'info'
            )
        
        # Всегда показываем одинаковое сообщение для безопасности
        flash('Если email существует, инструкции отправлены на почту', 'info')
        return redirect(url_for('login'))
    
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Сброс пароля по токену"""
    reset_token = PasswordResetToken.query.filter_by(token=token).first()
    
    if not reset_token or not reset_token.is_valid():
        flash('Недействительная или просроченная ссылка', 'danger')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Пароли не совпадают', 'danger')
            return redirect(url_for('reset_password', token=token))
        
        if len(password) < 6:
            flash('Пароль должен содержать минимум 6 символов', 'danger')
            return redirect(url_for('reset_password', token=token))
        
        # Обновляем пароль
        user = reset_token.user
        user.set_password(password)
        
        # Помечаем токен как использованный
        reset_token.is_used = True
        
        db.session.commit()
        
        flash('Пароль успешно изменен! Теперь вы можете войти.', 'success')
        return redirect(url_for('login'))
    
    return render_template('reset_password.html', token=token)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Создаем таблицы в БД
    app.run(debug=True)

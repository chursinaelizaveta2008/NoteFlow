# app.py
import os
from flask import Flask, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# Инициализация Flask приложения
app = Flask(__name__)

# Базовая конфигурация
app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///notes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация базы данных
db = SQLAlchemy(app)

# --- Модели будут здесь ---

# --- Маршруты будут здесь ---

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Создаем таблицы в БД
    app.run(debug=True)

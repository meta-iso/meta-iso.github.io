# -*- coding: utf-8 -*-
import os
import sys
import socket
import secrets
import threading
import webbrowser
from datetime import datetime

# ==========================================
# AUTOMATYCZNA INSTALACJA BRAKUJĄCYCH BIBLIOTEK
# (uruchamia się tylko przy starcie z .py, nie w gotowym .exe)
# ==========================================

def ensure_packages():
    if getattr(sys, 'frozen', False):
        return
    import importlib.util
    import subprocess
    required = {'flask': 'flask', 'flask_sqlalchemy': 'flask_sqlalchemy', 'webview': 'pywebview'}
    for module, package in required.items():
        if importlib.util.find_spec(module) is None:
            print(f'Brak biblioteki {package} - instaluję...')
            result = subprocess.run([sys.executable, '-m', 'pip', 'install', package])
            if result.returncode != 0 and module != 'webview':
                print(f'Nie udało się zainstalować {package}. Zainstaluj ją ręcznie: '
                      f'{sys.executable} -m pip install {package}')
                sys.exit(1)


ensure_packages()

from flask import Flask, render_template_string, request, redirect, url_for, session, flash, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.serving import make_server

# ==========================================
# ŚCIEŻKI (działają zarówno w .py, jak i w .exe z PyInstallera)
# ==========================================

FROZEN = getattr(sys, 'frozen', False)

# Zasoby dołączone do .exe (np. folder static z Bootstrapem)
RESOURCE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

# Dane użytkownika (baza, klucz sesji) muszą leżeć w zapisywalnym miejscu,
# a nie w tymczasowym folderze, z którego rozpakowuje się .exe
if FROZEN:
    _base = os.environ.get('APPDATA') or os.path.expanduser('~')
    DATA_DIR = os.path.join(_base, 'eDziennik')
else:
    DATA_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, 'edziennik.db')
KEY_PATH = os.path.join(DATA_DIR, 'secret.key')


def load_secret_key():
    """Losowy klucz sesji zapisany na dysku (zamiast klucza wpisanego na sztywno w kodzie)."""
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, 'r', encoding='utf-8') as f:
            key = f.read().strip()
            if key:
                return key
    key = secrets.token_hex(32)
    with open(KEY_PATH, 'w', encoding='utf-8') as f:
        f.write(key)
    return key


app = Flask(__name__, static_folder=os.path.join(RESOURCE_DIR, 'static'))
app.config['SECRET_KEY'] = load_secret_key()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_PATH.replace('\\', '/')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


@app.context_processor
def inject_assets():
    """Bootstrap z lokalnego folderu static (offline); jeśli go brak - z CDN."""
    css_local = os.path.join(app.static_folder, 'bootstrap.min.css')
    js_local = os.path.join(app.static_folder, 'bootstrap.bundle.min.js')
    return {
        'BS_CSS': '/static/bootstrap.min.css' if os.path.exists(css_local)
                  else 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
        'BS_JS': '/static/bootstrap.bundle.min.js' if os.path.exists(js_local)
                 else 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
    }

# ==========================================
# MODELE BAZY DANYCH
# ==========================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False) # admin, teacher, student, staff
    subject = db.Column(db.String(50), nullable=True)
    assigned_class = db.Column(db.String(10), nullable=True)

class Grade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(50), nullable=False)
    value = db.Column(db.Integer, nullable=False)
    weight = db.Column(db.Integer, nullable=False, default=1)
    description = db.Column(db.String(100), nullable=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    is_final = db.Column(db.Boolean, default=False)

    student = db.relationship('User', foreign_keys=[student_id])
    teacher = db.relationship('User', foreign_keys=[teacher_id])

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), nullable=False) # Obecny, Nieobecny, Spóźnienie, Usprawiedliwiony
    excuse_requested = db.Column(db.Boolean, default=False)

    student = db.relationship('User', foreign_keys=[student_id])

class LessonTopic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(50), nullable=False)
    assigned_class = db.Column(db.String(10), nullable=False)
    topic = db.Column(db.String(255), nullable=False)
    date = db.Column(db.String(10), nullable=False)

class Remark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(20), nullable=False, default='Negatywna') # Pozytywna, Negatywna, Neutralna
    points = db.Column(db.Integer, nullable=False, default=0)
    text = db.Column(db.Text, nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

    teacher = db.relationship('User', foreign_keys=[teacher_id])
    student = db.relationship('User', foreign_keys=[student_id])

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_sent = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])

# Nowy model bazy danych na potrzeby sekcji aktualności
class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(50), default='Życie szkoły')

# ==========================================
# ULEPSZONE SZABLONY INTERFEJSU (UI)
# ==========================================

LAYOUT_BEFORE = '''<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>System e-Dziennika</title>
    <link href="{{ BS_CSS }}" rel="stylesheet">
</head>
<body class="d-flex flex-column min-vh-100 bg-light">
<nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4 py-3 shadow-sm">
    <div class="container">
        <a class="navbar-brand fw-bold" href="/">📚 LIBRUS Pro Portal</a>
        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
            <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="navbarNav">
            <ul class="navbar-nav me-auto">
                <li class="nav-item"><a class="nav-link text-white" href="/">Strona Główna</a></li>
                {% if session.get('user_id') %}
                    {% if session['role'] == 'admin' %}
                        <li class="nav-item"><a class="nav-link text-white" href="/admin">Panel Admina</a></li>
                    {% elif session['role'] == 'teacher' %}
                        <li class="nav-item"><a class="nav-link text-white" href="/teacher">Panel Nauczyciela</a></li>
                    {% elif session['role'] == 'student' %}
                        <li class="nav-item"><a class="nav-link text-white" href="/student">Panel Ucznia</a></li>
                    {% endif %}
                {% endif %}
            </ul>
            <div class="navbar-nav ms-auto align-items-center">
                {% if session.get('user_id') %}
                    <span class="navbar-text me-3 text-white">
                        Witaj, <strong>{{ session['username'] }}</strong> <span class="badge bg-light text-dark ms-1">{{ session['role'] }}</span>
                    </span>
                    <a class="btn btn-info btn-sm rounded-pill text-dark px-3 me-2 fw-semibold" href="/messages">✉ Wiadomości</a>
                    <a class="btn btn-outline-light btn-sm rounded-pill px-3" href="/logout">Wyloguj się</a>
                {% endif %}
            </div>
        </div>
    </div>
</nav>
<div class="container flex-grow-1">
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, message in messages %}
                <div class="alert alert-{{ 'danger' if category=='error' else 'success' }} alert-dismissible fade show rounded-3 shadow-sm" role="alert">
                    {{ message }}
                    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                </div>
            {% endfor %}
        {% endif %}
    {% endwith %}'''

LAYOUT_AFTER = '''</div>
<footer class="bg-dark text-white text-center py-3 mt-5">
    <div class="container">
        <small class="text-muted">&copy; 2026 LIBRUS Pro - System Zarządzania Placówką Oświatową</small>
    </div>
</footer>
<script src="{{ BS_JS }}"></script>
</body>
</html>'''

HOME_HTML = LAYOUT_BEFORE + '''
<div class="row g-4">
    <!-- Kolumna Lewa: Artykuły i aktualności -->
    <div class="col-lg-8">
        <div class="p-4 bg-white rounded-3 shadow-sm mb-4">
            <h2 class="fw-bold text-dark border-bottom pb-2 mb-4">📰 Aktualności z życia szkoły</h2>
            
            {% for item in news_list %}
                <div class="card mb-4 border-0 bg-light p-3">
                    <div class="card-body p-2">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <span class="badge bg-primary rounded-pill">{{ item.category }}</span>
                            <small class="text-muted">{{ item.date_added.strftime('%d.%m.%Y %H:%M') }}</small>
                        </div>
                        <h4 class="card-title fw-bold text-primary">{{ item.title }}</h4>
                        <p class="card-text text-secondary mt-2">{{ item.content }}</p>
                    </div>
                </div>
            {% else %}
                <p class="text-muted">Brak aktualnych wiadomości w tym momencie.</p>
            {% endfor %}
        </div>
    </div>
    
    <!-- Kolumna Prawa: Formularz Logowania / Stan sesji -->
    <div class="col-lg-4">
        <div class="card shadow-sm border-0 sticky-top" style="top: 20px;">
            <div class="card-header bg-primary text-white text-center py-3 rounded-top-3">
                <h4 class="mb-0 fw-bold">🔐 Strefa Logowania</h4>
            </div>
            <div class="card-body p-4 bg-white rounded-bottom-3">
                {% if not session.get('user_id') %}
                    <form method="POST" action="/login_process">
                        <div class="mb-3">
                            <label class="form-label">Login użytkownika</label>
                            <input type="text" name="username" class="form-control" required>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Hasło dostępowe</label>
                            <input type="password" name="password" class="form-control" required>
                            <div class="form-text text-muted small mt-1">Domyślne hasła testowe to: 123456</div>
                        </div>
                        <button type="submit" class="btn btn-primary w-100 py-2 fw-semibold">Zaloguj się</button>
                    </form>
                {% else %}
                    <div class="text-center py-2">
                        <div class="fs-1 mb-2">✅</div>
                        <h5 class="fw-bold mb-1">Jesteś już zalogowany</h5>
                        <p class="text-muted small">Masz aktywną sesję jako użytkownik <strong>{{ session['username'] }}</strong>.</p>
                        
                        <div class="d-grid gap-2 mt-4">
                            {% if session['role'] == 'admin' %}
                                <a href="/admin" class="btn btn-dark">Przejdź do Panelu Administratora</a>
                            {% elif session['role'] == 'teacher' %}
                                <a href="/teacher" class="btn btn-dark">Przejdź do Panelu Nauczyciela</a>
                            {% elif session['role'] == 'student' %}
                                <a href="/student" class="btn btn-dark">Przejdź do Karty Ocen</a>
                            {% else %}
                                <a href="/messages" class="btn btn-dark">Przejdź do Wiadomości</a>
                            {% endif %}
                            <a href="/logout" class="btn btn-outline-danger btn-sm mt-2">Wyloguj z systemu</a>
                        </div>
                    </div>
                {% endif %}
            </div>
        </div>
    </div>
</div>
''' + LAYOUT_AFTER

ADMIN_HTML = LAYOUT_BEFORE + '''
<div class="card shadow-sm p-4 mb-4 bg-white border-0">
    <h2 class="fw-bold text-dark mb-0">🛠️ Panel Administracyjny (Dyrektor / Rektor)</h2>
</div>
<div class="row g-4">
    <div class="col-md-4">
        <div class="card shadow-sm p-4 border-0 bg-white">
            <h5 class="fw-bold mb-3 text-primary">Dodaj nowego użytkownika</h5>
            <form method="POST">
                <div class="mb-3"><label class="form-label">Login</label><input type="text" name="username" class="form-control" required></div>
                <div class="mb-3"><label class="form-label">Hasło</label><input type="password" name="password" class="form-control" required></div>
                <div class="mb-3">
                    <label class="form-label">Rola</label>
                    <select name="role" class="form-select">
                        <option value="student">Uczeń</option>
                        <option value="teacher">Nauczyciel</option>
                        <option value="admin">Administrator</option>
                        <option value="staff">Sekretariat / Obsługa</option>
                    </select>
                </div>
                <div class="mb-3"><label class="form-label">Klasa (opcjonalnie)</label><input type="text" name="assigned_class" class="form-control"></div>
                <div class="mb-3"><label class="form-label">Przedmiot (opcjonalnie)</label><input type="text" name="subject" class="form-control"></div>
                <button type="submit" class="btn btn-primary w-100 fw-semibold">Utwórz konto</button>
            </form>
        </div>
    </div>
    <div class="col-md-8">
        <div class="card shadow-sm p-4 border-0 bg-white">
            <h5 class="fw-bold mb-3 text-secondary">Lista zarejestrowanych osób</h5>
            <div class="table-responsive">
                <table class="table table-striped table-hover align-middle">
                    <thead class="table-dark"><tr><th>ID</th><th>Login</th><th>Rola</th><th>Klasa</th><th>Przedmiot</th></tr></thead>
                    <tbody>
                        {% for u in users %}
                        <tr><td>{{ u.id }}</td><td><strong>{{ u.username }}</strong></td><td><span class="badge bg-secondary">{{ u.role }}</span></td><td>{{ u.assigned_class or '-' }}</td><td>{{ u.subject or '-' }}</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>
''' + LAYOUT_AFTER

TEACHER_HTML = LAYOUT_BEFORE + '''
<div class="card shadow-sm p-4 mb-4 bg-white border-0">
    <h2 class="fw-bold text-dark mb-1">🧑‍🏫 Panel Nauczyciela: {{ session['username'] }}</h2>
    <div class="text-muted">Przedmiot: <span class="badge bg-primary fs-6">{{ teacher.subject }}</span> | Klasa: <span class="badge bg-secondary fs-6">{{ teacher.assigned_class }}</span></div>
</div>
<div class="row g-4 mb-4">
    <div class="col-md-4">
        <div class="card shadow-sm p-4 border-0 bg-white h-100">
            <h6 class="text-primary fw-bold mb-3">📝 Wystaw ocenę</h6>
            <form action="/teacher/add_grade" method="POST">
                <div class="mb-2">
                    <select name="student_id" class="form-select form-select-sm">
                        {% for s in students %} <option value="{{ s.id }}">{{ s.username }}</option> {% endfor %}
                    </select>
                </div>
                <div class="mb-2"><input type="number" min="1" max="6" name="value" class="form-control form-control-sm" placeholder="Ocena (1-6)" required></div>
                <div class="mb-2"><input type="number" min="1" max="10" name="weight" value="1" class="form-control form-control-sm" placeholder="Waga" required></div>
                <div class="mb-2"><input type="text" name="description" class="form-control form-control-sm" placeholder="Opis wpisu"></div>
                <div class="form-check mb-3"><input type="checkbox" name="is_final" class="form-check-input" id="f"><label class="form-check-label small" for="f">Ocena końcowa</label></div>
                <button type="submit" class="btn btn-primary w-100 btn-sm fw-semibold">Zapisz ocenę</button>
            </form>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card shadow-sm p-4 border-0 bg-white h-100">
            <h6 class="text-warning fw-bold mb-3">🕒 Frekwencja</h6>
            <form action="/teacher/add_attendance" method="POST">
                <div class="mb-2">
                    <select name="student_id" class="form-select form-select-sm">
                        {% for s in students %} <option value="{{ s.id }}">{{ s.username }}</option> {% endfor %}
                    </select>
                </div>
                <div class="mb-2"><input type="date" name="date" value="{{ current_date }}" class="form-control form-control-sm" required></div>
                <div class="mb-3">
                    <select name="status" class="form-select form-select-sm">
                        <option value="Obecny">Obecny</option>
                        <option value="Nieobecny">Nieobecny</option>
                        <option value="Spóźnienie">Spóźnienie</option>
                    </select>
                </div>
                <button type="submit" class="btn btn-warning w-100 btn-sm text-dark fw-semibold">Zapisz obecność</button>
            </form>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card shadow-sm p-4 border-0 bg-white h-100">
            <h6 class="text-danger fw-bold mb-3">⚠️ Wpisz uwagę</h6>
            <form action="/teacher/add_remark" method="POST">
                <div class="mb-2">
                    <select name="student_id" class="form-select form-select-sm">
                        {% for s in students %} <option value="{{ s.id }}">{{ s.username }}</option> {% endfor %}
                    </select>
                </div>
                <div class="mb-2">
                    <select name="category" class="form-select form-select-sm">
                        <option value="Negatywna">Negatywna (Punkty ujemne)</option>
                        <option value="Pozytywna">Pozytywna (Punkty dodatnie)</option>
                        <option value="Neutralna">Neutralna (Bez zmian)</option>
                    </select>
                </div>
                <div class="mb-2"><input type="number" name="points" class="form-control form-control-sm" placeholder="Punkty (np. -10 lub 15)" required></div>
                <div class="mb-3"><input type="text" name="text" class="form-control form-control-sm" placeholder="Treść uwagi" required></div>
                <button type="submit" class="btn btn-danger w-100 btn-sm fw-semibold">Dodaj uwagę</button>
            </form>
        </div>
    </div>
</div>
<div class="card shadow-sm p-4 mb-4 border-0 bg-white">
    <h6 class="text-success fw-bold mb-3">📚 Temat Lekcji</h6>
    <form action="/teacher/add_topic" method="POST" class="d-flex gap-2">
        <input type="text" name="topic" class="form-control form-control-sm" placeholder="Wpisz temat dzisiejszych zajęć..." required>
        <button type="submit" class="btn btn-success btn-sm px-4 fw-semibold">Zapisz temat</button>
    </form>
</div>
<div class="card shadow-sm p-4 border-0 bg-white">
    <h5 class="fw-bold text-dark mb-3">Ostatnio wystawione oceny</h5>
    <div class="table-responsive">
        <table class="table table-hover align-middle">
            <thead class="table-light"><tr><th>Uczeń</th><th>Ocena</th><th>Opis</th><th>Rodzaj</th><th>Akcja</th></tr></thead>
            <tbody>
                {% for g in grades %}
                <tr>
                    <td><strong>{{ g.student.username }}</strong></td>
                    <td><span class="badge bg-dark fs-6">{{ g.value }} (waga {{ g.weight }})</span></td>
                    <td>{{ g.description or '-' }}</td>
                    <td><span class="badge border border-secondary text-secondary">{{ 'Semestralna' if g.is_final else 'Cząstkowa' }}</span></td>
                    <td><form action="/teacher/delete_grade/{{ g.id }}" method="POST" onsubmit="return confirm('Usunąć tę ocenę?');"><button type="submit" class="btn btn-outline-danger btn-sm rounded-pill px-3">Usuń</button></form></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
''' + LAYOUT_AFTER

STUDENT_HTML = LAYOUT_BEFORE + '''
<div class="card shadow-sm p-4 mb-4 bg-white border-0">
    <h2 class="fw-bold text-dark mb-1">🎓 Panel Ucznia: {{ session['username'] }}</h2>
    <h5 class="text-muted">Klasa: <strong>{{ student_class }}</strong> | Sugerowane Zachowanie: <span class="badge bg-info text-dark">{{ behavior_grade }}</span></h5>
</div>
<div class="row g-4">
    <div class="col-md-8">
        <div class="card shadow-sm p-4 border-0 bg-white mb-4">
            <h5 class="fw-bold text-dark mb-3">📋 Karta Ocen i Średnie Ważone</h5>
            <div class="table-responsive">
                <table class="table table-bordered text-center align-middle">
                    <thead class="table-dark"><tr><th>Przedmiot</th><th>Oceny cząstkowe</th><th>Średnia ważona</th><th>Semestralna</th></tr></thead>
                    <tbody>
                        {% for sub, data in subjects_data.items() %}
                        <tr>
                            <td class="text-start"><strong>{{ sub }}</strong></td>
                            <td>
                                {% for g in data.partials %}
                                <span class="badge bg-light text-dark border m-1" title="{{ g.description }}">{{ g.value }} <small class="text-muted">(w{{ g.weight }})</small></span>
                                {% endfor %}
                            </td>
                            <td><span class="badge bg-info text-dark px-3 py-2 fs-6">{{ "%.2f"|format(data.avg) if data.avg > 0 else '-' }}</span></td>
                            <td>{% if data.final %}<span class="badge bg-success px-3 py-2 fs-6">{{ data.final.value }}</span>{% else %}-{% endif %}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card shadow-sm p-4 border-0 bg-white text-center mb-4">
            <h5 class="fw-bold text-dark mb-3">📈 Statystyka obecności</h5>
            <div class="progress my-3" style="height: 25px;"><div class="progress-bar bg-success" style="width: {{ attendance_pct }}%;">{{ "%.1f"|format(attendance_pct) }}%</div></div>
        </div>
        <div class="card shadow-sm p-4 border-0 bg-white">
            <h5 class="fw-bold text-dark mb-3">📝 Dziennik Uwag Szkolnych (Bilans: {{ total_remark_points }} pkt)</h5>
            {% for r in remarks %}
            <div class="alert alert-{{ 'danger' if r.category=='Negatywna' else ('success' if r.category=='Pozytywna' else 'secondary') }} p-3 mb-2 small rounded-3">
                <strong>{{ r.teacher.username }}</strong> [{{ r.category }} / {{ r.points }} pkt]:<br><div class="mt-1 text-dark">{{ r.text }}</div>
            </div>
            {% else %}
            <p class="text-success small mb-0">✅ Brak uwag w systemie. Wzorowa postawa!</p>
            {% endfor %}
        </div>
    </div>
</div>
''' + LAYOUT_AFTER

MESSAGES_HTML = LAYOUT_BEFORE + '''
<div class="card shadow-sm p-4 mb-4 bg-white border-0">
    <h2 class="fw-bold text-dark mb-0">✉️ Skrzynka wiadomości systemowych</h2>
</div>
<div class="row g-4">
    <div class="col-md-5">
        <div class="card shadow-sm p-4 border-0 bg-white">
            <h5 class="fw-bold text-dark mb-3">Nowa wiadomość</h5>
            <form method="POST">
                <div class="mb-3">
                    <label class="form-label fw-semibold text-muted">Wybierz adresata:</label>
                    <select name="receiver_id" class="form-select form-select-sm" size="10" required>
                        <optgroup label="🧑‍🏫 NAUCZYCIELE">
                            {% for u in all_users if u.role == 'teacher' %}
                            <option value="{{ u.id }}">mgr {{ u.username }} - {{ u.subject }}</option>
                            {% endfor %}
                        </optgroup>
                        <optgroup label="🧑‍🎓 UCZNIOWIE">
                            {% for u in all_users if u.role == 'student' %}
                            <option value="{{ u.id }}">{{ u.username }} (Klasa {{ u.assigned_class }})</option>
                            {% endfor %}
                        </optgroup>
                        <optgroup label="🏢 ADMINISTRACJA / SEKRETARIAT">
                            {% for u in all_users if u.role in ['admin', 'staff'] %}
                            <option value="{{ u.id }}">{{ u.username|upper }} (Władze / Obsługa)</option>
                            {% endfor %}
                        </optgroup>
                    </select>
                </div>
                <div class="mb-2"><input type="text" name="title" class="form-control form-control-sm" placeholder="Temat wiadomości" required></div>
                <div class="mb-3"><textarea name="content" rows="4" class="form-control form-control-sm" placeholder="Treść wiadomości..." required></textarea></div>
                <button type="submit" class="btn btn-dark w-100 btn-sm fw-semibold">Wyślij e-Wiadomość</button>
            </form>
        </div>
    </div>
    <div class="col-md-7">
        <div class="card shadow-sm p-4 border-0 bg-white">
            <h5 class="fw-bold text-dark mb-3">Skrzynka odbiorcza</h5>
            {% for m in inbox %}
            <div class="border rounded p-3 mb-3 bg-light shadow-sm rounded-3">
                <div class="d-flex justify-content-between small text-muted mb-2"><strong>Od: {{ m.sender.username }} ({{ m.sender.role }})</strong><span>{{ m.date_sent.strftime('%d.%m.%Y %H:%M') }}</span></div>
                <h6 class="fw-bold text-primary mb-2">{{ m.title }}</h6>
                <p class="mb-0 small text-dark">{{ m.content }}</p>
            </div>
            {% else %}
            <p class="text-muted small">Brak wiadomości w skrzynce.</p>
            {% endfor %}
        </div>
    </div>
</div>
''' + LAYOUT_AFTER

# ==========================================
# LOGIKA ROUTINGU APLIKACJI
# ==========================================

@app.route('/')
def home():
    news_list = News.query.order_by(News.date_added.desc()).all()
    return render_template_string(HOME_HTML, news_list=news_list)

@app.route('/login_process', methods=['POST'])
def login_process():
    username = request.form['username']
    password = request.form['password']
    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password, password):
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role
        if user.role == 'admin': return redirect(url_for('admin'))
        elif user.role == 'teacher': return redirect(url_for('teacher'))
        elif user.role == 'student': return redirect(url_for('student'))
        else: return redirect(url_for('messages'))
    flash('Nieprawidłowe dane logowania', 'error')
    return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Wylogowano pomyślnie.', 'success')
    return redirect(url_for('home'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if session.get('role') != 'admin': return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        role = request.form['role']
        assigned_class = (request.form.get('assigned_class') or '').strip() or None
        subject = (request.form.get('subject') or '').strip() or None
        if role not in ('student', 'teacher', 'admin', 'staff'):
            flash('Nieprawidłowa rola.', 'error')
        elif not username or not password:
            flash('Login i hasło są wymagane.', 'error')
        elif User.query.filter_by(username=username).first():
            flash('Użytkownik o takim loginie już istnieje.', 'error')
        else:
            db.session.add(User(username=username, password=generate_password_hash(password), role=role, assigned_class=assigned_class, subject=subject))
            db.session.commit()
            flash('Konto utworzone pomyślnie!', 'success')
    users = User.query.all()
    return render_template_string(ADMIN_HTML, users=users)

@app.route('/teacher')
def teacher():
    if session.get('role') != 'teacher': return redirect(url_for('home'))
    teacher = db.session.get(User, session['user_id'])
    students = User.query.filter_by(role='student', assigned_class=teacher.assigned_class).all()
    grades = Grade.query.filter_by(teacher_id=teacher.id).order_by(Grade.date_added.desc()).all()
    c_date = datetime.now().strftime('%Y-%m-%d')
    return render_template_string(TEACHER_HTML, teacher=teacher, students=students, grades=grades, current_date=c_date)

def get_own_student(teacher, student_id):
    """Zwraca ucznia tylko jeśli należy do klasy danego nauczyciela."""
    st = db.session.get(User, student_id)
    if not st or st.role != 'student' or st.assigned_class != teacher.assigned_class:
        abort(403)
    return st


@app.route('/teacher/add_grade', methods=['POST'])
def teacher_add_grade():
    if session.get('role') != 'teacher': abort(403)
    teacher = db.session.get(User, session['user_id'])
    student = get_own_student(teacher, int(request.form['student_id']))
    value, weight = int(request.form['value']), int(request.form['weight'])
    if not (1 <= value <= 6 and 1 <= weight <= 10):
        flash('Ocena musi być w zakresie 1-6, a waga 1-10.', 'error')
        return redirect(url_for('teacher'))
    db.session.add(Grade(
        student_id=student.id, teacher_id=teacher.id, subject=teacher.subject,
        value=value, weight=weight,
        description=request.form.get('description'), is_final='is_final' in request.form
    ))
    db.session.commit()
    flash('Ocena została zapisana.', 'success')
    return redirect(url_for('teacher'))

@app.route('/teacher/add_attendance', methods=['POST'])
def teacher_add_attendance():
    if session.get('role') != 'teacher': abort(403)
    teacher = db.session.get(User, session['user_id'])
    student = get_own_student(teacher, int(request.form['student_id']))
    if request.form['status'] not in ('Obecny', 'Nieobecny', 'Spóźnienie'):
        abort(400)
    db.session.add(Attendance(
        student_id=student.id, teacher_id=teacher.id, subject=teacher.subject,
        date=request.form['date'], status=request.form['status']
    ))
    db.session.commit()
    flash('Frekwencja została zapisana.', 'success')
    return redirect(url_for('teacher'))

@app.route('/teacher/add_remark', methods=['POST'])
def teacher_add_remark():
    if session.get('role') != 'teacher': abort(403)
    teacher = db.session.get(User, session['user_id'])
    student = get_own_student(teacher, int(request.form['student_id']))
    if request.form['category'] not in ('Pozytywna', 'Negatywna', 'Neutralna'):
        abort(400)
    db.session.add(Remark(
        student_id=student.id, teacher_id=teacher.id,
        category=request.form['category'], points=int(request.form['points']),
        text=request.form['text']
    ))
    db.session.commit()
    flash('Uwaga została dodana do bazy!', 'success')
    return redirect(url_for('teacher'))

@app.route('/teacher/add_topic', methods=['POST'])
def teacher_add_topic():
    if session.get('role') != 'teacher': abort(403)
    teacher = db.session.get(User, session['user_id'])
    db.session.add(LessonTopic(
        teacher_id=teacher.id, subject=teacher.subject, assigned_class=teacher.assigned_class,
        topic=request.form['topic'], date=datetime.now().strftime('%Y-%m-%d')
    ))
    db.session.commit()
    flash('Temat lekcji odnotowany.', 'success')
    return redirect(url_for('teacher'))

@app.route('/teacher/delete_grade/<int:id>', methods=['POST'])
def delete_grade(id):
    if session.get('role') != 'teacher': abort(403)
    g = db.get_or_404(Grade, id)
    if g.teacher_id != session['user_id']: abort(403)
    db.session.delete(g)
    db.session.commit()
    flash('Ocena została usunięta.', 'success')
    return redirect(url_for('teacher'))

@app.route('/student')
def student():
    if session.get('role') != 'student': return redirect(url_for('home'))
    student = db.session.get(User, session['user_id'])
    subjects = ["Język polski", "Matematyka", "Język angielski", "Historia", "Chemia", "Fizyka", "Biologia", "Geografia", "WOS", "Informatyka (IT)", "Religia", "Filozofia", "Biznes i zarządzanie (BiZ)", "Plastyka", "Edukacja obywatelska", "Wychowanie fizyczne"]

    subjects_data = {}
    for sub in subjects:
        partials = Grade.query.filter_by(student_id=student.id, subject=sub, is_final=False).all()
        final = Grade.query.filter_by(student_id=student.id, subject=sub, is_final=True).first()
        val_sum, weight_sum = sum(g.value * g.weight for g in partials), sum(g.weight for g in partials)
        subjects_data[sub] = {'partials': partials, 'final': final, 'avg': (val_sum / weight_sum if weight_sum > 0 else 0.0)}

    all_att = Attendance.query.filter_by(student_id=student.id).all()
    obs = len([a for a in all_att if a.status in ['Obecny', 'Spóźnienie']])
    attendance_pct = (obs / len(all_att) * 100) if all_att else 100.0

    remarks = Remark.query.filter_by(student_id=student.id).all()
    total_pts = sum(r.points for r in remarks)

    if total_pts >= 50: b_grade = "Wzorowe"
    elif total_pts >= 20: b_grade = "Bardzo dobre"
    elif total_pts >= 0: b_grade = "Dobre"
    elif total_pts >= -20: b_grade = "Poprawne"
    else: b_grade = "Naganne"

    return render_template_string(STUDENT_HTML, student_class=student.assigned_class, subjects_data=subjects_data, attendance_pct=attendance_pct, remarks=remarks, total_remark_points=total_pts, behavior_grade=b_grade)

@app.route('/messages', methods=['GET', 'POST'])
def messages():
    if 'user_id' not in session: return redirect(url_for('home'))
    if request.method == 'POST':
        receiver = db.session.get(User, int(request.form['receiver_id']))
        if not receiver or receiver.id == session['user_id']:
            flash('Nieprawidłowy adresat.', 'error')
        else:
            db.session.add(Message(sender_id=session['user_id'], receiver_id=receiver.id, title=request.form['title'], content=request.form['content']))
            db.session.commit()
            flash('Wiadomość została pomyślnie wysłana!', 'success')
    inbox = Message.query.filter_by(receiver_id=session['user_id']).order_by(Message.date_sent.desc()).all()
    all_users = User.query.filter(User.id != session['user_id']).all()
    return render_template_string(MESSAGES_HTML, inbox=inbox, all_users=all_users)

# ==========================================
# INICJALIZACJA SYSTEMU I BAZY DANYCH
# ==========================================

def init_db():
    db.create_all()
    if not User.query.first():  # dane startowe tylko przy pierwszym uruchomieniu
        # Wypełnienie tabeli News startowymi artykułami dla ładnego wyglądu strony
        if not News.query.first():
            db.session.add(News(
                title="Sukces w Ogólnopolskim Konkursie Programistycznym!",
                content="Z dumą informujemy, że reprezentanci klas o profilu IT zajęli 1. miejsce w ogólnopolskim hackathonie dla szkół średnich. Projekt z zakresu automatyzacji procesów szkolnych zyskał najwyższe uznanie jury.",
                category="Osiągnięcia"
            ))
            db.session.add(News(
                title="Dni Otwarte placówki oraz Festiwal Nauki 2026",
                content="Zapraszamy przyszłych kandydatów wraz z rodzicami na tegoroczne Dni Otwarte, które odbędą się już w najbliższą sobotę od godziny 10:00. W programie m.in. pokazy laboratoryjne z chemii i fizyki oraz prezentacje projektów uczniowskich.",
                category="Wydarzenia"
            ))
            db.session.add(News(
                title="Modernizacja infrastruktury sportowej",
                content="Zakończył się remont głównej hali sportowej. Wymieniono parkiet na nowoczesną nawierzchnię syntetyczną oraz zainstalowano energooszczędne oświetlenie LED, co znacznie podniesie komfort zajęć wychowania fizycznego.",
                category="Inwestycje"
            ))

        for a_name in ["dyrektor", "rektor"]:
            if not User.query.filter_by(username=a_name).first():
                db.session.add(User(username=a_name, password=generate_password_hash("123456"), role="admin"))
        if not User.query.filter_by(username="sekretariat").first():
            db.session.add(User(username="sekretariat", password=generate_password_hash("123456"), role="staff"))

        teachers_setup = [
            ("zyleta", "Język polski", "1a"), ("orton", "Wychowanie fizyczne", "1b"),
            ("morgan", "Historia", "1c"), ("morawski", "Informatyka (IT)", "1d"),
            ("krzysztof", "Matematyka", "2a"), ("rollins", "Chemia", "2b"),
            ("cena", "Geografia", "2c"), ("breaker", "Biologia", "2d"),
            ("knight", "WOS", "3a"), ("menter", "Religia", "3b"),
            ("roman", "Fizyka", "3c"), ("frost", "Język angielski", "3d"),
            ("dominik", "Filozofia", "4a"), ("perez", "Biznes i zarządzanie (BiZ)", "4b"),
            ("sky", "Plastyka", "4c"), ("cody", "Edukacja obywatelska", "4d")
        ]
        for name, sub, cls in teachers_setup:
            if not User.query.filter_by(username=name).first():
                db.session.add(User(username=name, password=generate_password_hash("123456"), role="teacher", subject=sub, assigned_class=cls))

        students_setup = {"a1":"1a", "b2":"1b", "c3":"1c", "d4":"1d", "e5":"2a", "f6":"2b", "g7":"3a", "h8":"3b", "i9":"4a", "j0":"4b"}
        for st, cls in students_setup.items():
            if not User.query.filter_by(username=st).first():
                db.session.add(User(username=st, password=generate_password_hash("123456"), role="student", assigned_class=cls))
        db.session.commit()

# ==========================================
# OKNO APLIKACJI DESKTOPOWEJ
# ==========================================

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    with app.app_context():
        init_db()

    port = find_free_port()
    server = make_server('127.0.0.1', port, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{port}/'

    try:
        import webview  # pywebview - natywne okno zamiast przeglądarki
    except ImportError:
        # Awaryjnie: otwórz w domyślnej przeglądarce
        print(f'Aplikacja działa pod adresem {url} (Ctrl+C aby zakończyć)')
        webbrowser.open(url)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    else:
        webview.create_window('LIBRUS Pro - e-Dziennik', url, width=1280, height=820, min_size=(900, 600))
        webview.start()

    server.shutdown()


if __name__ == '__main__':
    main()

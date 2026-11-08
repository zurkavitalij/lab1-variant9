"""Точка входа WSGI-сервера Gunicorn: gunicorn wsgi:app"""
from some_app import app

if __name__ == "__main__":
    app.run()

@echo off
echo Запускаю бота...

:: Проверяем наличие Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Python не установлен! Установите Python 3.11 или выше
    pause
    exit /b 1
)

:: Проверяем наличие venv
if not exist venv (
    echo Создаю виртуальное окружение...
    python -m venv venv
)

:: Активируем venv
call venv\Scripts\activate.bat

:: Обновляем pip
python -m pip install --upgrade pip

:: Устанавливаем зависимости
pip install -r requirements.txt

:: Запускаем бота
python main.py

pause 
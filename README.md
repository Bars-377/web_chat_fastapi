# Инструкция

## Настройка

1. Открыть pyvenv.cfg по пути \myenv

   Изменить пути к интерпритаторам

## Запуск

1. Запустить виртуальное окружение:

         .\myenv\Scripts\activate

2. Запустить приложение:

         python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

## Дополнительно:

Создаёт requirements.txt:

      python -m pip freeze > requirements.txt

Установить requirements.txt:

      python -m pip install -r requirements.txt

   PowerShell

   python -m pip freeze | ForEach-Object { python -m pip uninstall -y $_ }
@echo off
chcp 65001 >nul
echo جاري تثبيت المكتبة المطلوبة (مرة واحدة)...
py -m pip install -r requirements.txt
echo جاري تشغيل البرنامج...
py main.py
pause

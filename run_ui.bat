@echo off
echo.
echo ===============================================
echo  YouTube Segment Extractor - Web UI
echo ===============================================
echo.
echo Starting the web application...
echo Your browser should open automatically.
echo If not, go to: http://localhost:8501
echo.
echo Press Ctrl+C to stop the application
echo.

python -m streamlit run ui_app.py --server.port 8501 --server.headless false

pause
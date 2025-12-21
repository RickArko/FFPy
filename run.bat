@echo off
echo.
echo ========================================
echo   FFPy - Fantasy Football Projections
echo ========================================
echo.
echo Starting app with ESPN API (free)...
echo.
echo The app will open in your browser at:
echo http://localhost:8501
echo.
echo Press Ctrl+C to stop the server
echo.
uv run streamlit run src/ffpy/app.py

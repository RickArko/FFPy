.PHONY: install run clean dev help

help:
	@echo "FFPy - Fantasy Football Point Projections"
	@echo ""
	@echo "Available commands:"
	@echo "  make install    - Install dependencies and set up the environment"
	@echo "  make run        - Run the Streamlit app"
	@echo "  make dev        - Run the app in development mode with auto-reload"
	@echo "  make clean      - Remove build artifacts and cache files"
	@echo "  make help       - Show this help message"

install:
	@echo "Installing FFPy dependencies..."
	uv sync
	@echo ""
	@echo "Installation complete!"
	@echo "Run 'make run' to start the application"

run:
	@echo ""
	@echo "========================================"
	@echo "  FFPy - Fantasy Football Projections"
	@echo "========================================"
	@echo ""
	@echo "Starting app with ESPN API (free)..."
	@echo ""
	@echo "The app will open in your browser at:"
	@echo "http://localhost:8501"
	@echo ""
	@echo "Press Ctrl+C to stop the server"
	@echo ""
	@uv run streamlit run src/ffpy/app.py

dev:
	@echo "Starting app in development mode..."
	uv run streamlit run src/ffpy/app.py --server.runOnSave=true

clean:
	@echo "Cleaning build artifacts..."
	rm -rf .uv
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "Clean complete!"

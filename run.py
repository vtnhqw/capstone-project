import os
import sys
import subprocess
import webbrowser
import time

def install_requirements():
    print("Checking and installing dependencies...")
    python_bin = sys.executable
    try:
        # Check if modules can be imported
        import fastapi
        import uvicorn
        import cryptography
        print("All dependencies are already installed.")
    except ImportError:
        print("Some dependencies are missing. Installing via pip...")
        try:
            subprocess.check_call([python_bin, "-m", "pip", "install", "-r", "requirements.txt"])
            print("Successfully installed all dependencies!")
        except Exception as e:
            print(f"Error during pip installation: {e}")
            print("Please make sure you have active internet connection.")
            sys.exit(1)

def run_server():
    # Make sure we're in the project directory
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)
    
    # Launch uvicorn
    print("\n------------------------------------------------")
    print("Launching EduMind Study Concierge on http://127.0.0.1:8000")
    print("Press Ctrl+C in this terminal window to stop the server.")
    print("------------------------------------------------\n")
    
    # Open browser after a short delay to let server initialize
    try:
        def open_browser():
            time.sleep(1.5)
            print("Opening EduMind Dashboard in your default web browser...")
            webbrowser.open("http://127.0.0.1:8000")
        
        import threading
        threading.Thread(target=open_browser, daemon=True).start()
    except Exception:
        pass # fail silently if background browser launch fails
        
    try:
        import uvicorn
        uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
    except KeyboardInterrupt:
        print("\nEduMind server stopped by user.")
    except Exception as e:
        print(f"\nFailed to start Uvicorn server: {e}")

if __name__ == "__main__":
    install_requirements()
    run_server()

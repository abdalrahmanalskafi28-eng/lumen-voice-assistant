@echo off
cd /d "%~dp0"
echo Installing Lumen requirements... please wait
python -m pip install --upgrade pip
python -m pip install SpeechRecognition gTTS playsound==1.2.2 groq edge-tts pyaudio
echo.
if not exist groq_key.txt type nul > groq_key.txt
echo Paste your Groq API key in the Notepad window, save, and close it.
start notepad groq_key.txt
echo.
echo Done. Now double-click test_jarvis.bat
pause

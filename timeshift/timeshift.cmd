@echo off
set PATH=%ProgramFiles%\Anaconda3;%ProgramFiles(x86)%\Anaconda3;%ProgramFiles%\Anaconda;%ProgramFiles(x86)%\Anaconda;%PATH%
call conda activate 2>NUL
python timeshift.py "%1"
if ERRORLEVEL 1 py -3 timeshift.py "%1"

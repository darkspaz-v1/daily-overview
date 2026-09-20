@echo off
REM Plan today around your classes and deadlines.
REM   "Plan Day.cmd"              -> today
REM   "Plan Day.cmd" tomorrow     -> tomorrow
REM   "Plan Day.cmd" --load       -> next 14 days' workload
cd /d "%~dp0"
python plan-day.py %*
echo.
pause

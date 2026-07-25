@echo off
setlocal
set GRADLE_VERSION=8.11.1
set DIST_ROOT=%USERPROFILE%\.gradle\chatgpt-wrapper\gradle-%GRADLE_VERSION%
set GRADLE_HOME=%DIST_ROOT%\gradle-%GRADLE_VERSION%
set ARCHIVE=%DIST_ROOT%\gradle-%GRADLE_VERSION%-bin.zip

if not exist "%GRADLE_HOME%\bin\gradle.bat" (
  if not exist "%DIST_ROOT%" mkdir "%DIST_ROOT%"
  if not exist "%ARCHIVE%" powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing 'https://services.gradle.org/distributions/gradle-%GRADLE_VERSION%-bin.zip' -OutFile '%ARCHIVE%'"
  if exist "%GRADLE_HOME%" rmdir /S /Q "%GRADLE_HOME%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%ARCHIVE%' -DestinationPath '%DIST_ROOT%' -Force"
)

call "%GRADLE_HOME%\bin\gradle.bat" %*
endlocal

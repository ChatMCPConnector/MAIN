# CI-Abnahme

Die verbindliche Abnahme erfolgt über den Workflow `Nebula Stride Android` auf einem Pull Request und anschließend erneut nach der Übernahme auf `main`.

Dabei werden Projektimport, GDScript-Tests, Debug- und Release-Export, Paket- und Signaturprüfung, Installation, App-Start, simulierte Eingaben, Pause, Game over, Logcat sowie vier Screenshots geprüft. Ausschließlich die signierte Release-APK wird in den europäischen Sauce-Labs-App-Speicher geladen; eine automatische Gerätesitzung wird nicht gestartet.

# CI-Abnahme

Die verbindliche Abnahme erfolgt über den Workflow `Nebula Stride Android` auf einem Pull Request und anschließend erneut nach der Übernahme auf `main`.

Geprüft werden Projektimport, deterministische GDScript-Tests, Debug- und Release-Export, Paket-, Architektur- und Signaturprüfung sowie ein vollständiger Lauf auf einem Android-API-34-x86_64-Emulator. Der Emulator installiert ein separates x86_64-Release-Template-APK und prüft App-Start, Tutorial, Hauptmenü, Gameplay, alle vier Wischrichtungen, Pause, Game over, Neustart, Logcat und sechs Screenshots.

Für die Veröffentlichung bleibt das eigentliche Release-APK ausschließlich ARM64 und signiert. Nur dieses APK wird nach einem erfolgreichen Lauf auf `main` in den europäischen Sauce-Labs-App-Speicher geladen. Eine automatische Sauce-Labs-Gerätesitzung wird nicht gestartet.

Der Emulator verwendet den Dummy-Audiotreiber, während die normale ARM64-Anwendung ihre Musik und Soundeffekte behält. Die prozedural erzeugte Musik wird nach dem regulären Stream-Ende über das `finished`-Signal neu gestartet, damit kein PCM-Loop-Endpunkt außerhalb des Puffers gelesen wird.

Die Pull-Request-Abnahme gilt erst als bestanden, wenn der Emulator-Smoke-Test und die technische sowie visuelle Kontrolle aller sechs Screenshots erfolgreich sind.

# Sauce Labs Android Test App

Kleine, bewusst einfache Android-App zum Prüfen von Sauce Labs Real Device Cloud und Emulatoren.

## Enthaltene Testszenarien

- Texteingabe und Begrüßung
- Plus-, Minus- und Reset-Schaltflächen
- Schalter für den Testmodus
- eindeutiger Erfolgsstatus
- stabile Android-View-IDs und Content Descriptions für Automatisierung
- JUnit-Unit-Tests für die Zählerlogik
- Espresso-Instrumentierungstest für den vollständigen UI-Ablauf

## APK in Sauce Labs testen

1. Öffne in GitHub **Actions**.
2. Starte **Android CI and Sauce Labs Upload** über **Run workflow** auf dem gewünschten Branch.
3. Der Workflow baut `app-debug.apk` und `app-debug-androidTest.apk`.
4. Beide Dateien werden im europäischen Sauce-Labs-App-Speicher abgelegt.
5. Öffne in Sauce Labs **App Management** und wähle `app-debug.apk`.
6. Starte einen **Live Test** auf einem Android-Gerät oder Emulator.

Bei einem Push auf `main` erfolgt der Upload ebenfalls automatisch.

## Empfohlener manueller Test

1. App starten.
2. `Sauce` in das Namensfeld schreiben.
3. **Begrüßung anzeigen** antippen und `Hallo, Sauce!` prüfen.
4. Den Zähler zweimal erhöhen und anschließend zurücksetzen.
5. Den Testmodus aktivieren.
6. **Test erfolgreich abschließen** antippen.
7. `STATUS: TEST ERFOLGREICH` prüfen.

## Technische Daten

- Paket: `com.chatmcpconnector.saucelabstestapp`
- Minimum SDK: 23
- Target/Compile SDK: 35
- Java: 17
- Android Gradle Plugin: 8.10.1
- Gradle: 8.11.1

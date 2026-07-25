# Game Design – Nebula Stride

## Identität

Asterion war eine schwebende Maschinenstadt, bis ihr Sternenkern zerbrach. Die Kurierpilotin Astra trägt den letzten stabilen Navigationskern und muss über drei Energiekanäle durch die kollabierenden Bezirke fliehen. Der visuelle Stil verbindet dunkles Weltraumblau, Cyan-Leitlinien, Magenta-Gefahren und goldene Sternsplitter.

## Kernmechaniken

- Automatische Bewegung, deren Tempo langsam von 10 auf maximal 25 Einheiten pro Sekunde steigt.
- Drei feste Spuren mit geglättetem statt teleportiertem Spurwechsel.
- Sprung mit eigener vertikaler Geschwindigkeit und Schwerkraft.
- Zeitbegrenzte Rutschbewegung mit sichtbar reduzierter Figurenhöhe.
- Barrieren müssen übersprungen, Energiebögen unterrutscht und Säulen vollständig umgangen werden.
- Sternsplitter erhöhen Zähler und Punktestand.

## Strecken- und Fairnessregeln

Streckensegmente, Hindernisse und Splitter werden gepoolt. Jedes Muster lässt mindestens eine Spur frei. In der Anfangsphase werden höchstens einfache Ein-Hindernis-Muster erzeugt; später dürfen zwei Spuren blockiert sein. Sammelreihen liegen ausschließlich auf als sicher gewählten Spuren. Feste Seeds ermöglichen reproduzierbare Tests.

## Fortschritt und Balancing

Punkte entsprechen der zurückgelegten Distanz plus 25 Punkten pro Sternsplitter. Die Geschwindigkeit steigt kontinuierlich, ist jedoch begrenzt. Die Spawn-Abstände verkürzen sich moderat mit der Distanz. Sichtweite und Reaktionszeit bleiben so ausgelegt, dass jede erzeugte Situation lösbar ist.

## Zustände

Start, Tutorial, Countdown, Spielen, Pausiert und Game over sind gegenseitig ausschließende Zustände. Ein Neustart setzt Spur, Tempo, Strecke, Hindernisse, Sammelobjekte, Punktestand, Animation und temporäre Eingaben zurück.

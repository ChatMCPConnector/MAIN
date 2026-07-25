# Pokémon-Recherche und Spielbalancing

Stand: 25. Juli 2026

Diese App verwendet **genau sechs Pokémon**. Die ursprünglichen Typen, Basiswerte und typischen Attacken wurden anhand offizieller Pokédex-Seiten und der etablierten Datenbank Pokémon Database geprüft. Die App übernimmt bewusst **nicht** das vollständige Regelwerk, sondern nutzt ein reduziertes, offline verfügbares Kampfsystem.

## Quellen

- Offizieller Pokémon-Pokédex: https://www.pokemon.com/uk/pokedex
- Pikachu: https://pokemondb.net/pokedex/pikachu
- Charmander: https://pokemondb.net/pokedex/charmander
- Squirtle: https://pokemondb.net/pokedex/squirtle
- Bulbasaur: https://pokemondb.net/pokedex/bulbasaur
- Geodude: https://pokemondb.net/pokedex/geodude
- Pidgey: https://pokemondb.net/pokedex/pidgey
- Typentabelle: https://pokemondb.net/type

## Anpassungsprinzipien

- Originalwerte dienen nur als Ausgangspunkt für Rollen wie schnell, robust oder offensiv.
- Spezial-Angriff und physischer Angriff werden in einen einzigen Angriffswert zusammengeführt.
- Sehr effektive Treffer verwenden `1,5×`, normale `1,0×`, nicht sehr effektive `0,75×`.
- Doppeltypen werden multipliziert, aber auf `0,75×` bis `1,5×` begrenzt. Dadurch sind Doppel-Schwächen und Immunitäten nicht kampfentscheidend.
- Starke Attacken haben niedrigere Genauigkeit.
- Ein kleiner Zufallsfaktor von `0,90` bis `1,06` verhindert völlig identische Runden.
- Die Schadensskalierung ist auf typische Kämpfe von ungefähr drei bis acht Runden ausgelegt.

## Finale Daten

| Pokémon | Originaltyp | Ausgangstendenz | Angepasst: KP / Angriff / Verteidigung / Initiative | Attacken | Balancing-Rolle |
|---|---|---|---|---|---|
| Pikachu | Elektro | sehr hohe Initiative, geringe Defensive | `92 / 70 / 48 / 92` | Donnerschock, Ruckzuckhieb, Funkensprung, Donner | Schnellster Angreifer; hoher Druck, aber fragil. |
| Glumanda | Feuer | offensiv und beweglich | `100 / 67 / 55 / 72` | Kratzer, Glut, Feuerzahn, Feuersturm | Ausgewogener Feuer-Angreifer; stark gegen Pflanze. |
| Schiggy | Wasser | hohe Verteidigung, eher langsam | `116 / 60 / 78 / 48` | Tackle, Aquaknarre, Nassschweif, Hydropumpe | Kontrollierter Tank; niedriger Angriff wird durch Ausdauer ausgeglichen. |
| Bisasam | Pflanze | solide Defensive und Spezialwerte | `112 / 63 / 68 / 52` | Tackle, Rankenhieb, Rasierblatt, Samenbomben | Stabiler Allrounder gegen Wasser und Gestein/Boden. |
| Kleinstein | Gestein/Boden | sehr hohe Verteidigung, extrem langsam | `118 / 72 / 88 / 30` | Tackle, Steinwurf, Dampfwalze, Steinhagel | Langsamster Tank mit klaren Wasser-/Pflanzen-Schwächen. |
| Taubsi | Normal/Flug | schnell, aber geringe Basiswerte | `98 / 62 / 54 / 80` | Tackle, Windstoß, Ruckzuckhieb, Aero-Ass | Schneller flexibler Konter gegen Pflanze; bleibt defensiv verwundbar. |

## Vereinfachte Typenbeziehungen

Nur die für die sechs Pokémon relevanten Beziehungen sind implementiert. Beispiele:

- Feuer ist stark gegen Pflanze.
- Wasser ist stark gegen Feuer sowie Gestein/Boden.
- Pflanze ist stark gegen Wasser sowie Gestein/Boden.
- Elektro ist stark gegen Wasser und Flug, aber schwach gegen Boden und Pflanze.
- Boden ist stark gegen Elektro, Feuer und Gestein.
- Gestein ist stark gegen Feuer und Flug.
- Flug ist stark gegen Pflanze.
- Normal ist immer neutral.

## Urheberrecht und Offline-Betrieb

Die App enthält keine kopierten Original-Sprites. Jede Darstellung ist eine selbst erstellte, stark vereinfachte Pixelinterpretation aus lokalen Farbfeldern. Während der Laufzeit werden keine Webseiten, APIs oder Bilder geladen.

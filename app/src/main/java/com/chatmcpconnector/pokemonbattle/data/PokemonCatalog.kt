package com.chatmcpconnector.pokemonbattle.data

import com.chatmcpconnector.pokemonbattle.game.RandomSource
import com.chatmcpconnector.pokemonbattle.model.ElementType
import com.chatmcpconnector.pokemonbattle.model.Move
import com.chatmcpconnector.pokemonbattle.model.Pokemon

object PokemonCatalog {
    val all: List<Pokemon> = listOf(
        Pokemon(
            id = "pikachu",
            name = "Pikachu",
            types = listOf(ElementType.ELECTRIC),
            maxHp = 92,
            attack = 70,
            defense = 48,
            speed = 92,
            moves = listOf(
                Move("Donnerschock", ElementType.ELECTRIC, 42, 100),
                Move("Ruckzuckhieb", ElementType.NORMAL, 48, 100),
                Move("Funkensprung", ElementType.ELECTRIC, 62, 95),
                Move("Donner", ElementType.ELECTRIC, 88, 78)
            )
        ),
        Pokemon(
            id = "charmander",
            name = "Glumanda",
            types = listOf(ElementType.FIRE),
            maxHp = 100,
            attack = 67,
            defense = 55,
            speed = 72,
            moves = listOf(
                Move("Kratzer", ElementType.NORMAL, 42, 100),
                Move("Glut", ElementType.FIRE, 46, 100),
                Move("Feuerzahn", ElementType.FIRE, 64, 93),
                Move("Feuersturm", ElementType.FIRE, 88, 80)
            )
        ),
        Pokemon(
            id = "squirtle",
            name = "Schiggy",
            types = listOf(ElementType.WATER),
            maxHp = 116,
            attack = 60,
            defense = 78,
            speed = 48,
            moves = listOf(
                Move("Tackle", ElementType.NORMAL, 42, 100),
                Move("Aquaknarre", ElementType.WATER, 46, 100),
                Move("Nassschweif", ElementType.WATER, 68, 90),
                Move("Hydropumpe", ElementType.WATER, 90, 78)
            )
        ),
        Pokemon(
            id = "bulbasaur",
            name = "Bisasam",
            types = listOf(ElementType.GRASS),
            maxHp = 112,
            attack = 63,
            defense = 68,
            speed = 52,
            moves = listOf(
                Move("Tackle", ElementType.NORMAL, 42, 100),
                Move("Rankenhieb", ElementType.GRASS, 46, 100),
                Move("Rasierblatt", ElementType.GRASS, 62, 95),
                Move("Samenbomben", ElementType.GRASS, 82, 85)
            )
        ),
        Pokemon(
            id = "geodude",
            name = "Kleinstein",
            types = listOf(ElementType.ROCK, ElementType.GROUND),
            maxHp = 118,
            attack = 72,
            defense = 88,
            speed = 30,
            moves = listOf(
                Move("Tackle", ElementType.NORMAL, 42, 100),
                Move("Steinwurf", ElementType.ROCK, 52, 90),
                Move("Dampfwalze", ElementType.GROUND, 62, 95),
                Move("Steinhagel", ElementType.ROCK, 78, 86)
            )
        ),
        Pokemon(
            id = "pidgey",
            name = "Taubsi",
            types = listOf(ElementType.NORMAL, ElementType.FLYING),
            maxHp = 98,
            attack = 62,
            defense = 54,
            speed = 80,
            moves = listOf(
                Move("Tackle", ElementType.NORMAL, 42, 100),
                Move("Windstoß", ElementType.FLYING, 46, 100),
                Move("Ruckzuckhieb", ElementType.NORMAL, 55, 100),
                Move("Aero-Ass", ElementType.FLYING, 72, 92)
            )
        )
    )

    fun randomPair(random: RandomSource): Pair<Pokemon, Pokemon> {
        require(all.size >= 2)
        val playerIndex = random.nextInt(all.size)
        val opponentOffset = random.nextInt(all.size - 1)
        val opponentIndex = if (opponentOffset >= playerIndex) opponentOffset + 1 else opponentOffset
        return all[playerIndex] to all[opponentIndex]
    }
}

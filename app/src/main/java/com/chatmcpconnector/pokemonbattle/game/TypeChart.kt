package com.chatmcpconnector.pokemonbattle.game

import com.chatmcpconnector.pokemonbattle.model.ElementType

object TypeChart {
    const val SUPER_EFFECTIVE = 1.5
    const val NORMAL_EFFECTIVE = 1.0
    const val NOT_VERY_EFFECTIVE = 0.75

    private val strengths = setOf(
        ElementType.FIRE to ElementType.GRASS,
        ElementType.WATER to ElementType.FIRE,
        ElementType.WATER to ElementType.ROCK,
        ElementType.WATER to ElementType.GROUND,
        ElementType.GRASS to ElementType.WATER,
        ElementType.GRASS to ElementType.ROCK,
        ElementType.GRASS to ElementType.GROUND,
        ElementType.ELECTRIC to ElementType.WATER,
        ElementType.ELECTRIC to ElementType.FLYING,
        ElementType.GROUND to ElementType.ELECTRIC,
        ElementType.GROUND to ElementType.FIRE,
        ElementType.GROUND to ElementType.ROCK,
        ElementType.ROCK to ElementType.FIRE,
        ElementType.ROCK to ElementType.FLYING,
        ElementType.FLYING to ElementType.GRASS
    )

    private val resistances = setOf(
        ElementType.FIRE to ElementType.WATER,
        ElementType.FIRE to ElementType.ROCK,
        ElementType.WATER to ElementType.GRASS,
        ElementType.WATER to ElementType.ELECTRIC,
        ElementType.GRASS to ElementType.FIRE,
        ElementType.GRASS to ElementType.FLYING,
        ElementType.ELECTRIC to ElementType.GROUND,
        ElementType.ELECTRIC to ElementType.GRASS,
        ElementType.ELECTRIC to ElementType.ELECTRIC,
        ElementType.GROUND to ElementType.WATER,
        ElementType.GROUND to ElementType.GRASS,
        ElementType.GROUND to ElementType.FLYING,
        ElementType.ROCK to ElementType.WATER,
        ElementType.ROCK to ElementType.GRASS,
        ElementType.ROCK to ElementType.GROUND,
        ElementType.FLYING to ElementType.ELECTRIC,
        ElementType.FLYING to ElementType.ROCK
    )

    fun multiplier(attackType: ElementType, defenderTypes: List<ElementType>): Double {
        val raw = defenderTypes.fold(1.0) { value, defenderType ->
            value * singleMultiplier(attackType, defenderType)
        }
        return raw.coerceIn(NOT_VERY_EFFECTIVE, SUPER_EFFECTIVE)
    }

    fun singleMultiplier(attackType: ElementType, defenderType: ElementType): Double = when {
        attackType to defenderType in strengths -> SUPER_EFFECTIVE
        attackType to defenderType in resistances -> NOT_VERY_EFFECTIVE
        else -> NORMAL_EFFECTIVE
    }
}

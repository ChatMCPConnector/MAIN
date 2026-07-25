package com.chatmcpconnector.pokemonbattle

import com.chatmcpconnector.pokemonbattle.game.RandomSource

class TestRandomSource(
    doubles: List<Double> = listOf(0.0),
    ints: List<Int> = listOf(0)
) : RandomSource {
    private val doubleValues = doubles.ifEmpty { listOf(0.0) }
    private val intValues = ints.ifEmpty { listOf(0) }
    private var doubleIndex = 0
    private var intIndex = 0

    override fun nextInt(bound: Int): Int {
        val value = intValues[intIndex++ % intValues.size]
        return Math.floorMod(value, bound)
    }

    override fun nextDouble(): Double = doubleValues[doubleIndex++ % doubleValues.size].coerceIn(0.0, 0.999999)
}

package com.chatmcpconnector.pokemonbattle.game

interface RandomSource {
    fun nextInt(bound: Int): Int
    fun nextDouble(): Double
}

class KotlinRandomSource(
    private val random: kotlin.random.Random = kotlin.random.Random.Default
) : RandomSource {
    override fun nextInt(bound: Int): Int = random.nextInt(bound)
    override fun nextDouble(): Double = random.nextDouble()
}

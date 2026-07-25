package com.chatmcpconnector.pokemonbattle.game

import com.chatmcpconnector.pokemonbattle.model.Move
import com.chatmcpconnector.pokemonbattle.model.Pokemon
import kotlin.math.floor

object DamageCalculator {
    private const val SCALE = 0.28
    private const val MIN_RANDOM = 0.90
    private const val RANDOM_SPAN = 0.16

    data class Result(
        val hit: Boolean,
        val damage: Int,
        val effectiveness: Double
    )

    fun calculate(
        attacker: Pokemon,
        defender: Pokemon,
        move: Move,
        random: RandomSource
    ): Result {
        val hitRoll = random.nextDouble() * 100.0
        val effectiveness = TypeChart.multiplier(move.type, defender.types)
        if (hitRoll >= move.accuracy) {
            return Result(hit = false, damage = 0, effectiveness = effectiveness)
        }

        val baseDamage = (attacker.attack.toDouble() * move.power.toDouble() / defender.defense.toDouble()) * SCALE
        val randomFactor = MIN_RANDOM + (random.nextDouble() * RANDOM_SPAN)
        val damage = floor(baseDamage * effectiveness * randomFactor).toInt().coerceAtLeast(1)
        return Result(hit = true, damage = damage, effectiveness = effectiveness)
    }
}

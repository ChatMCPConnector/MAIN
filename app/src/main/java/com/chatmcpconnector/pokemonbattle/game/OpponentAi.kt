package com.chatmcpconnector.pokemonbattle.game

import com.chatmcpconnector.pokemonbattle.model.Move
import com.chatmcpconnector.pokemonbattle.model.Pokemon
import kotlin.math.max

object OpponentAi {
    fun chooseMove(attacker: Pokemon, defender: Pokemon, random: RandomSource): Move {
        val effectiveMoves = attacker.moves.filter {
            TypeChart.multiplier(it.type, defender.types) > TypeChart.NORMAL_EFFECTIVE
        }

        val pool = if (effectiveMoves.isNotEmpty() && random.nextDouble() < 0.78) {
            effectiveMoves
        } else {
            attacker.moves
        }

        val weighted = pool.map { move ->
            val effectiveness = TypeChart.multiplier(move.type, defender.types)
            val score = max(1, (move.power * move.accuracy * effectiveness / 100.0).toInt())
            move to score
        }
        val totalWeight = weighted.sumOf { it.second }
        var roll = random.nextInt(totalWeight)
        for ((move, weight) in weighted) {
            if (roll < weight) return move
            roll -= weight
        }
        return weighted.last().first
    }
}

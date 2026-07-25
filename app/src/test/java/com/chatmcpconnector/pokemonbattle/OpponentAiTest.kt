package com.chatmcpconnector.pokemonbattle

import com.chatmcpconnector.pokemonbattle.data.PokemonCatalog
import com.chatmcpconnector.pokemonbattle.game.OpponentAi
import com.chatmcpconnector.pokemonbattle.game.TypeChart
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OpponentAiTest {
    @Test
    fun aiPrefersSuperEffectiveMoveWhenAvailable() {
        val pikachu = PokemonCatalog.all.first { it.id == "pikachu" }
        val squirtle = PokemonCatalog.all.first { it.id == "squirtle" }
        val move = OpponentAi.chooseMove(pikachu, squirtle, TestRandomSource(doubles = listOf(0.0), ints = listOf(0)))
        assertTrue(TypeChart.multiplier(move.type, squirtle.types) > 1.0)
    }

    @Test
    fun aiStillChoosesAMoveWithoutSuperEffectiveOption() {
        val pidgey = PokemonCatalog.all.first { it.id == "pidgey" }
        val squirtle = PokemonCatalog.all.first { it.id == "squirtle" }
        val move = OpponentAi.chooseMove(pidgey, squirtle, TestRandomSource(doubles = listOf(0.9), ints = listOf(7)))
        assertNotNull(move)
        assertTrue(move in pidgey.moves)
    }

    @Test
    fun weightedSelectionCanReachEveryMove() {
        val pidgey = PokemonCatalog.all.first { it.id == "pidgey" }
        val squirtle = PokemonCatalog.all.first { it.id == "squirtle" }
        val chosen = (0..500).map { roll ->
            OpponentAi.chooseMove(pidgey, squirtle, TestRandomSource(doubles = listOf(0.99), ints = listOf(roll)))
        }.toSet()
        assertTrue(chosen.size >= 3)
    }
}

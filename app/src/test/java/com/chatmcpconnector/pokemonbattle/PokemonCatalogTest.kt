package com.chatmcpconnector.pokemonbattle

import com.chatmcpconnector.pokemonbattle.data.PokemonCatalog
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PokemonCatalogTest {
    @Test
    fun exactlySixPokemonAreDefined() {
        assertEquals(6, PokemonCatalog.all.size)
    }

    @Test
    fun everyPokemonHasExactlyFourDifferentMoves() {
        PokemonCatalog.all.forEach { pokemon ->
            assertEquals(4, pokemon.moves.size)
            assertEquals(4, pokemon.moves.map { it.name }.distinct().size)
        }
    }

    @Test
    fun randomPairNeverContainsTheSamePokemon() {
        repeat(120) { seed ->
            val (player, opponent) = PokemonCatalog.randomPair(TestRandomSource(ints = listOf(seed, seed * 7 + 3)))
            assertNotEquals(player.id, opponent.id)
        }
    }

    @Test
    fun allStatsAndMovesAreUsable() {
        assertTrue(PokemonCatalog.all.all { it.maxHp > 0 && it.attack > 0 && it.defense > 0 && it.speed > 0 })
        assertTrue(PokemonCatalog.all.flatMap { it.moves }.all { it.power > 0 && it.accuracy in 1..100 })
    }
}

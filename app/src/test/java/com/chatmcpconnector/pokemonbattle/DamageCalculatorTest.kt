package com.chatmcpconnector.pokemonbattle

import com.chatmcpconnector.pokemonbattle.data.PokemonCatalog
import com.chatmcpconnector.pokemonbattle.game.DamageCalculator
import com.chatmcpconnector.pokemonbattle.model.ElementType
import com.chatmcpconnector.pokemonbattle.model.Move
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DamageCalculatorTest {
    private val pikachu = PokemonCatalog.all.first { it.id == "pikachu" }
    private val squirtle = PokemonCatalog.all.first { it.id == "squirtle" }
    private val geodude = PokemonCatalog.all.first { it.id == "geodude" }

    @Test
    fun missedMoveDealsNoDamage() {
        val result = DamageCalculator.calculate(
            pikachu,
            squirtle,
            Move("Riskant", ElementType.NORMAL, 100, 50),
            TestRandomSource(doubles = listOf(0.75))
        )
        assertEquals(false, result.hit)
        assertEquals(0, result.damage)
    }

    @Test
    fun higherAttackIncreasesDamage() {
        val low = DamageCalculator.calculate(pikachu.copy(attack = 40), squirtle, pikachu.moves[0], TestRandomSource(doubles = listOf(0.0, 0.0)))
        val high = DamageCalculator.calculate(pikachu.copy(attack = 80), squirtle, pikachu.moves[0], TestRandomSource(doubles = listOf(0.0, 0.0)))
        assertTrue(high.damage > low.damage)
    }

    @Test
    fun higherDefenseReducesDamage() {
        val lowDefense = DamageCalculator.calculate(pikachu, squirtle.copy(defense = 40), pikachu.moves[0], TestRandomSource(doubles = listOf(0.0, 0.0)))
        val highDefense = DamageCalculator.calculate(pikachu, squirtle.copy(defense = 100), pikachu.moves[0], TestRandomSource(doubles = listOf(0.0, 0.0)))
        assertTrue(lowDefense.damage > highDefense.damage)
    }

    @Test
    fun higherPowerIncreasesDamage() {
        val weak = DamageCalculator.calculate(pikachu, squirtle, Move("Schwach", ElementType.NORMAL, 40, 100), TestRandomSource(doubles = listOf(0.0, 0.0)))
        val strong = DamageCalculator.calculate(pikachu, squirtle, Move("Stark", ElementType.NORMAL, 80, 100), TestRandomSource(doubles = listOf(0.0, 0.0)))
        assertTrue(strong.damage > weak.damage)
    }

    @Test
    fun effectivenessChangesDamageInExpectedDirection() {
        val normal = DamageCalculator.calculate(pikachu, squirtle, Move("Neutral", ElementType.NORMAL, 50, 100), TestRandomSource(doubles = listOf(0.0, 0.0)))
        val effective = DamageCalculator.calculate(pikachu, squirtle, Move("Elektro", ElementType.ELECTRIC, 50, 100), TestRandomSource(doubles = listOf(0.0, 0.0)))
        val resisted = DamageCalculator.calculate(pikachu, geodude, Move("Elektro", ElementType.ELECTRIC, 50, 100), TestRandomSource(doubles = listOf(0.0, 0.0)))
        assertTrue(effective.damage > normal.damage)
        assertTrue(resisted.damage < normal.damage)
    }

    @Test
    fun successfulHitAlwaysDealsAtLeastOneDamage() {
        val result = DamageCalculator.calculate(
            pikachu.copy(attack = 1),
            geodude.copy(defense = 999),
            Move("Mini", ElementType.ELECTRIC, 1, 100),
            TestRandomSource(doubles = listOf(0.0, 0.0))
        )
        assertEquals(1, result.damage)
    }
}

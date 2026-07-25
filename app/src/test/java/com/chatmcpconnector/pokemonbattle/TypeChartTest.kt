package com.chatmcpconnector.pokemonbattle

import com.chatmcpconnector.pokemonbattle.model.ElementType
import com.chatmcpconnector.pokemonbattle.game.TypeChart
import org.junit.Assert.assertEquals
import org.junit.Test

class TypeChartTest {
    @Test
    fun superEffectiveRelationsUseOnePointFive() {
        assertEquals(1.5, TypeChart.multiplier(ElementType.FIRE, listOf(ElementType.GRASS)), 0.0)
        assertEquals(1.5, TypeChart.multiplier(ElementType.WATER, listOf(ElementType.FIRE)), 0.0)
        assertEquals(1.5, TypeChart.multiplier(ElementType.ELECTRIC, listOf(ElementType.FLYING)), 0.0)
        assertEquals(1.5, TypeChart.multiplier(ElementType.GROUND, listOf(ElementType.ELECTRIC)), 0.0)
    }

    @Test
    fun notVeryEffectiveRelationsUseZeroPointSevenFive() {
        assertEquals(0.75, TypeChart.multiplier(ElementType.FIRE, listOf(ElementType.WATER)), 0.0)
        assertEquals(0.75, TypeChart.multiplier(ElementType.ELECTRIC, listOf(ElementType.GROUND)), 0.0)
        assertEquals(0.75, TypeChart.multiplier(ElementType.FLYING, listOf(ElementType.ROCK)), 0.0)
    }

    @Test
    fun normalRelationsUseOne() {
        assertEquals(1.0, TypeChart.multiplier(ElementType.NORMAL, listOf(ElementType.FIRE)), 0.0)
        assertEquals(1.0, TypeChart.multiplier(ElementType.WATER, listOf(ElementType.FLYING)), 0.0)
    }

    @Test
    fun dualTypeExtremesAreCappedForBalance() {
        assertEquals(1.5, TypeChart.multiplier(ElementType.WATER, listOf(ElementType.ROCK, ElementType.GROUND)), 0.0)
        assertEquals(0.75, TypeChart.multiplier(ElementType.ELECTRIC, listOf(ElementType.ELECTRIC, ElementType.GRASS)), 0.0)
    }
}

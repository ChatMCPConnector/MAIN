package com.chatmcpconnector.pokemonbattle

import com.chatmcpconnector.pokemonbattle.data.PokemonCatalog
import com.chatmcpconnector.pokemonbattle.game.BattleEngine
import com.chatmcpconnector.pokemonbattle.game.BattleEvent
import com.chatmcpconnector.pokemonbattle.game.BattleState
import com.chatmcpconnector.pokemonbattle.game.Combatant
import com.chatmcpconnector.pokemonbattle.game.Winner
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BattleEngineTest {
    private val pikachu = PokemonCatalog.all.first { it.id == "pikachu" }
    private val squirtle = PokemonCatalog.all.first { it.id == "squirtle" }

    @Test
    fun newBattleStartsWithFullHpAndResetState() {
        val battle = BattleEngine.newBattle(TestRandomSource(ints = listOf(0, 0)))
        assertEquals(battle.player.pokemon.maxHp, battle.player.currentHp)
        assertEquals(battle.opponent.pokemon.maxHp, battle.opponent.currentHp)
        assertEquals(1, battle.round)
        assertFalse(battle.isProcessing)
        assertNull(battle.winner)
    }

    @Test
    fun hpNeverDropsBelowZero() {
        val state = BattleState(
            player = Combatant(pikachu),
            opponent = Combatant(squirtle, currentHp = 1)
        )
        val started = BattleEngine.beginRound(state, 3, TestRandomSource(doubles = listOf(0.0, 0.0, 0.0), ints = listOf(0)))!!
        assertEquals(0, started.finalState.opponent.currentHp)
    }

    @Test
    fun battleEndsImmediatelyAndSecondAttackIsSkippedAfterKnockout() {
        val state = BattleState(
            player = Combatant(pikachu),
            opponent = Combatant(squirtle, currentHp = 1)
        )
        val started = BattleEngine.beginRound(state, 0, TestRandomSource(doubles = listOf(0.0, 0.0, 0.0), ints = listOf(0)))!!
        assertEquals(Winner.PLAYER, started.finalState.winner)
        assertEquals(1, started.events.filterIsInstance<BattleEvent.AttackStarted>().size)
    }

    @Test
    fun defeatedPokemonCannotStartAnotherRound() {
        val state = BattleState(
            player = Combatant(pikachu, currentHp = 0),
            opponent = Combatant(squirtle),
            winner = Winner.OPPONENT
        )
        assertNull(BattleEngine.beginRound(state, 0, TestRandomSource()))
    }

    @Test
    fun processingLockRejectsRapidSecondInput() {
        val state = BattleState(player = Combatant(pikachu), opponent = Combatant(squirtle))
        val started = BattleEngine.beginRound(state, 0, TestRandomSource(doubles = listOf(0.0, 0.0, 0.0), ints = listOf(0)))
        assertNotNull(started)
        assertTrue(started!!.lockedState.isProcessing)
        assertNull(BattleEngine.beginRound(started.lockedState, 1, TestRandomSource()))
    }

    @Test
    fun newBattleAfterFinishedBattleHasNoOldState() {
        val finished = BattleState(
            player = Combatant(pikachu, 0),
            opponent = Combatant(squirtle, 5),
            round = 9,
            messages = listOf("alt"),
            winner = Winner.OPPONENT
        )
        assertTrue(finished.isFinished)
        val fresh = BattleEngine.newBattle(TestRandomSource(ints = listOf(2, 3)))
        assertEquals(1, fresh.round)
        assertNull(fresh.winner)
        assertEquals(fresh.player.pokemon.maxHp, fresh.player.currentHp)
        assertEquals(fresh.opponent.pokemon.maxHp, fresh.opponent.currentHp)
        assertFalse(fresh.messages.contains("alt"))
    }
}

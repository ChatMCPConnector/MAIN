package com.chatmcpconnector.pokemonbattle.game

import com.chatmcpconnector.pokemonbattle.model.ElementType
import com.chatmcpconnector.pokemonbattle.model.Move
import com.chatmcpconnector.pokemonbattle.model.Pokemon

enum class Side { PLAYER, OPPONENT }
enum class Winner { PLAYER, OPPONENT }

data class Combatant(
    val pokemon: Pokemon,
    val currentHp: Int = pokemon.maxHp
) {
    val isFainted: Boolean get() = currentHp <= 0

    fun takeDamage(damage: Int): Combatant = copy(
        currentHp = (currentHp - damage.coerceAtLeast(0)).coerceAtLeast(0)
    )
}

data class BattleState(
    val player: Combatant,
    val opponent: Combatant,
    val round: Int = 1,
    val messages: List<String> = listOf("Ein neuer Kampf beginnt!"),
    val isProcessing: Boolean = false,
    val winner: Winner? = null
) {
    val isFinished: Boolean get() = winner != null
}

sealed interface BattleEvent {
    data class AttackStarted(val side: Side, val move: Move) : BattleEvent
    data class Missed(val side: Side, val move: Move) : BattleEvent
    data class DamageApplied(
        val target: Side,
        val damage: Int,
        val remainingHp: Int,
        val effectiveness: Double,
        val effectType: ElementType
    ) : BattleEvent
    data class Fainted(val side: Side, val pokemonName: String) : BattleEvent
    data class Finished(val winner: Winner) : BattleEvent
}

data class StartedRound(
    val lockedState: BattleState,
    val events: List<BattleEvent>,
    val finalState: BattleState
)

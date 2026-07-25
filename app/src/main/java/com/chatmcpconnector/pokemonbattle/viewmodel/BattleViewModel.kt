package com.chatmcpconnector.pokemonbattle.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.chatmcpconnector.pokemonbattle.game.BattleEngine
import com.chatmcpconnector.pokemonbattle.game.BattleEvent
import com.chatmcpconnector.pokemonbattle.game.BattleState
import com.chatmcpconnector.pokemonbattle.game.KotlinRandomSource
import com.chatmcpconnector.pokemonbattle.game.RandomSource
import com.chatmcpconnector.pokemonbattle.game.Side
import com.chatmcpconnector.pokemonbattle.game.TypeChart
import com.chatmcpconnector.pokemonbattle.game.Winner
import com.chatmcpconnector.pokemonbattle.model.ElementType
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

enum class AppScreen { START, BATTLE }

data class BattleUiState(
    val screen: AppScreen = AppScreen.START,
    val battle: BattleState? = null,
    val activeSide: Side? = null,
    val hitSide: Side? = null,
    val effectType: ElementType? = null,
    val showResult: Boolean = false
)

class BattleViewModel(
    private val random: RandomSource = KotlinRandomSource()
) : ViewModel() {
    private val _uiState = MutableStateFlow(BattleUiState())
    val uiState: StateFlow<BattleUiState> = _uiState.asStateFlow()

    fun startBattle() {
        _uiState.value = BattleUiState(
            screen = AppScreen.BATTLE,
            battle = BattleEngine.newBattle(random)
        )
    }

    fun returnToStart() {
        _uiState.value = BattleUiState()
    }

    fun chooseMove(index: Int) {
        val currentUi = _uiState.value
        val currentBattle = currentUi.battle ?: return
        val started = BattleEngine.beginRound(currentBattle, index, random) ?: return

        _uiState.value = currentUi.copy(
            battle = started.lockedState,
            showResult = false
        )

        viewModelScope.launch {
            var liveState = started.lockedState
            for (event in started.events) {
                when (event) {
                    is BattleEvent.AttackStarted -> {
                        val attackerName = if (event.side == Side.PLAYER) {
                            liveState.player.pokemon.name
                        } else {
                            liveState.opponent.pokemon.name
                        }
                        liveState = liveState.copy(
                            messages = appendMessage(liveState.messages, "$attackerName setzt ${event.move.name} ein!")
                        )
                        _uiState.value = _uiState.value.copy(
                            battle = liveState,
                            activeSide = event.side,
                            hitSide = null,
                            effectType = event.move.type
                        )
                        delay(260)
                    }

                    is BattleEvent.Missed -> {
                        liveState = liveState.copy(
                            messages = appendMessage(liveState.messages, "Die Attacke ging daneben!")
                        )
                        _uiState.value = _uiState.value.copy(
                            battle = liveState,
                            activeSide = null,
                            hitSide = null
                        )
                        delay(380)
                    }

                    is BattleEvent.DamageApplied -> {
                        liveState = if (event.target == Side.PLAYER) {
                            liveState.copy(player = liveState.player.copy(currentHp = event.remainingHp))
                        } else {
                            liveState.copy(opponent = liveState.opponent.copy(currentHp = event.remainingHp))
                        }

                        val targetName = if (event.target == Side.PLAYER) {
                            liveState.player.pokemon.name
                        } else {
                            liveState.opponent.pokemon.name
                        }
                        val effectivenessMessage = when {
                            event.effectiveness > TypeChart.NORMAL_EFFECTIVE -> "Das ist sehr effektiv!"
                            event.effectiveness < TypeChart.NORMAL_EFFECTIVE -> "Das ist nicht sehr effektiv."
                            else -> "Die Attacke trifft!"
                        }
                        liveState = liveState.copy(
                            messages = appendMessage(
                                appendMessage(liveState.messages, effectivenessMessage),
                                "$targetName verliert ${event.damage} KP."
                            )
                        )
                        _uiState.value = _uiState.value.copy(
                            battle = liveState,
                            activeSide = null,
                            hitSide = event.target,
                            effectType = event.effectType
                        )
                        delay(430)
                    }

                    is BattleEvent.Fainted -> {
                        liveState = liveState.copy(
                            messages = appendMessage(liveState.messages, "${event.pokemonName} wurde besiegt!")
                        )
                        _uiState.value = _uiState.value.copy(battle = liveState, hitSide = event.side)
                        delay(350)
                    }

                    is BattleEvent.Finished -> {
                        liveState = liveState.copy(
                            winner = event.winner,
                            messages = appendMessage(
                                liveState.messages,
                                if (event.winner == Winner.PLAYER) "Du hast gewonnen!" else "Du hast verloren!"
                            )
                        )
                    }
                }
            }

            val finalWithMessages = started.finalState.copy(
                messages = liveState.messages,
                player = liveState.player,
                opponent = liveState.opponent
            )
            _uiState.value = _uiState.value.copy(
                battle = finalWithMessages,
                activeSide = null,
                hitSide = null,
                effectType = null,
                showResult = finalWithMessages.isFinished
            )
        }
    }

    private fun appendMessage(messages: List<String>, message: String): List<String> =
        (messages + message).takeLast(5)
}

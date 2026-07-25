package com.chatmcpconnector.pokemonbattle.game

import com.chatmcpconnector.pokemonbattle.model.Move

object BattleEngine {
    fun newBattle(random: RandomSource): BattleState {
        val (player, opponent) = com.chatmcpconnector.pokemonbattle.data.PokemonCatalog.randomPair(random)
        return BattleState(
            player = Combatant(player),
            opponent = Combatant(opponent),
            messages = listOf("${player.name} tritt gegen ${opponent.name} an!")
        )
    }

    fun beginRound(
        state: BattleState,
        playerMoveIndex: Int,
        random: RandomSource
    ): StartedRound? {
        if (state.isProcessing || state.isFinished) return null
        if (playerMoveIndex !in state.player.pokemon.moves.indices) return null
        if (state.player.isFainted || state.opponent.isFainted) return null

        val playerMove = state.player.pokemon.moves[playerMoveIndex]
        val opponentMove = OpponentAi.chooseMove(state.opponent.pokemon, state.player.pokemon, random)
        val locked = state.copy(isProcessing = true)

        val playerFirst = when {
            state.player.pokemon.speed > state.opponent.pokemon.speed -> true
            state.player.pokemon.speed < state.opponent.pokemon.speed -> false
            else -> random.nextDouble() < 0.5
        }

        val order = if (playerFirst) {
            listOf(Side.PLAYER to playerMove, Side.OPPONENT to opponentMove)
        } else {
            listOf(Side.OPPONENT to opponentMove, Side.PLAYER to playerMove)
        }

        var working = locked
        val events = mutableListOf<BattleEvent>()

        for ((side, move) in order) {
            val attacker = if (side == Side.PLAYER) working.player else working.opponent
            val defender = if (side == Side.PLAYER) working.opponent else working.player
            if (attacker.isFainted || defender.isFainted || working.isFinished) break

            events += BattleEvent.AttackStarted(side, move)
            val result = DamageCalculator.calculate(attacker.pokemon, defender.pokemon, move, random)
            if (!result.hit) {
                events += BattleEvent.Missed(side, move)
                continue
            }

            val damaged = defender.takeDamage(result.damage)
            if (side == Side.PLAYER) {
                working = working.copy(opponent = damaged)
                events += BattleEvent.DamageApplied(
                    target = Side.OPPONENT,
                    damage = result.damage,
                    remainingHp = damaged.currentHp,
                    effectiveness = result.effectiveness,
                    effectType = move.type
                )
                if (damaged.isFainted) {
                    working = working.copy(winner = Winner.PLAYER)
                    events += BattleEvent.Fainted(Side.OPPONENT, damaged.pokemon.name)
                    events += BattleEvent.Finished(Winner.PLAYER)
                    break
                }
            } else {
                working = working.copy(player = damaged)
                events += BattleEvent.DamageApplied(
                    target = Side.PLAYER,
                    damage = result.damage,
                    remainingHp = damaged.currentHp,
                    effectiveness = result.effectiveness,
                    effectType = move.type
                )
                if (damaged.isFainted) {
                    working = working.copy(winner = Winner.OPPONENT)
                    events += BattleEvent.Fainted(Side.PLAYER, damaged.pokemon.name)
                    events += BattleEvent.Finished(Winner.OPPONENT)
                    break
                }
            }
        }

        val final = working.copy(
            round = if (working.isFinished) working.round else working.round + 1,
            isProcessing = false
        )
        return StartedRound(lockedState = locked, events = events, finalState = final)
    }
}

package com.chatmcpconnector.pokemonbattle.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.chatmcpconnector.pokemonbattle.game.BattleState
import com.chatmcpconnector.pokemonbattle.game.Combatant
import com.chatmcpconnector.pokemonbattle.game.Side
import com.chatmcpconnector.pokemonbattle.game.Winner
import com.chatmcpconnector.pokemonbattle.model.ElementType
import com.chatmcpconnector.pokemonbattle.model.Move
import com.chatmcpconnector.pokemonbattle.viewmodel.AppScreen
import com.chatmcpconnector.pokemonbattle.viewmodel.BattleUiState
import com.chatmcpconnector.pokemonbattle.viewmodel.BattleViewModel

private val PixelFont = FontFamily.Monospace
private val Cream = Color(0xFFF4F1DE)
private val Ink = Color(0xFF101820)
private val Panel = Color(0xFF243847)
private val Red = Color(0xFFE84545)
private val Gold = Color(0xFFF2CC60)

@Composable
fun PokemonBattleApp(viewModel: BattleViewModel = viewModel()) {
    val uiState by viewModel.uiState.collectAsState()
    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        when (uiState.screen) {
            AppScreen.START -> StartScreen(onStart = viewModel::startBattle)
            AppScreen.BATTLE -> BattleScreen(
                uiState = uiState,
                onMove = viewModel::chooseMove,
                onNewBattle = viewModel::startBattle,
                onHome = viewModel::returnToStart
            )
        }
    }
}

@Composable
private fun StartScreen(onStart: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 22.dp, vertical = 42.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        PokeballMark(modifier = Modifier.size(112.dp))
        Spacer(Modifier.height(24.dp))
        Text(
            text = "POKÉMON\nPIXELKAMPF",
            fontFamily = PixelFont,
            fontWeight = FontWeight.Black,
            fontSize = 30.sp,
            lineHeight = 33.sp,
            textAlign = TextAlign.Center,
            color = Gold
        )
        Spacer(Modifier.height(18.dp))
        Text(
            text = "Zwei zufällige Pokémon treten in einem einfachen 1-gegen-1-Kampf gegeneinander an.",
            fontFamily = PixelFont,
            fontSize = 16.sp,
            lineHeight = 23.sp,
            textAlign = TextAlign.Center,
            color = Cream
        )
        Spacer(Modifier.height(30.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("pikachu", "charmander", "squirtle").forEach {
                PokemonPixelSprite(
                    pokemonId = it,
                    side = Side.OPPONENT,
                    flash = false,
                    modifier = Modifier.size(76.dp)
                )
            }
        }
        Spacer(Modifier.height(30.dp))
        Button(
            onClick = onStart,
            modifier = Modifier
                .fillMaxWidth()
                .height(62.dp),
            shape = RoundedCornerShape(4.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Red, contentColor = Cream)
        ) {
            Text("KAMPF STARTEN", fontFamily = PixelFont, fontWeight = FontWeight.Bold, fontSize = 18.sp)
        }
        Spacer(Modifier.height(16.dp))
        Text(
            "6 Pokémon · 4 Attacken · komplett offline",
            fontFamily = PixelFont,
            fontSize = 12.sp,
            color = Color(0xFFADC4D3),
            textAlign = TextAlign.Center
        )
    }
}

@Composable
private fun PokeballMark(modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .aspectRatio(1f)
            .clip(RoundedCornerShape(50))
            .background(Red)
            .border(8.dp, Ink, RoundedCornerShape(50)),
        contentAlignment = Alignment.Center
    ) {
        Box(Modifier.fillMaxWidth().height(10.dp).background(Ink))
        Box(
            Modifier
                .size(34.dp)
                .clip(RoundedCornerShape(50))
                .background(Cream)
                .border(8.dp, Ink, RoundedCornerShape(50))
        )
    }
}

@Composable
private fun BattleScreen(
    uiState: BattleUiState,
    onMove: (Int) -> Unit,
    onNewBattle: () -> Unit,
    onHome: () -> Unit
) {
    val battle = uiState.battle ?: return
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(top = 28.dp, start = 12.dp, end = 12.dp, bottom = 18.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                "RUNDE ${battle.round}",
                fontFamily = PixelFont,
                fontWeight = FontWeight.Bold,
                color = Gold,
                fontSize = 16.sp
            )
            TextButton(onClick = onHome, enabled = !battle.isProcessing) {
                Text("ENDE", fontFamily = PixelFont, color = Cream)
            }
        }

        BattleField(uiState = uiState, battle = battle)
        MessagePanel(messages = battle.messages)
        MoveGrid(
            moves = battle.player.pokemon.moves,
            enabled = !battle.isProcessing && !battle.isFinished,
            onMove = onMove
        )
    }

    if (uiState.showResult && battle.winner != null) {
        ResultDialog(
            winner = battle.winner,
            winningPokemon = if (battle.winner == Winner.PLAYER) battle.player.pokemon.name else battle.opponent.pokemon.name,
            rounds = battle.round,
            onNewBattle = onNewBattle,
            onHome = onHome
        )
    }
}

@Composable
private fun BattleField(uiState: BattleUiState, battle: BattleState) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(4.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFCAD8C1))
    ) {
        Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            CombatantPanel(
                combatant = battle.opponent,
                side = Side.OPPONENT,
                active = uiState.activeSide == Side.OPPONENT,
                hit = uiState.hitSide == Side.OPPONENT
            )
            CombatantPanel(
                combatant = battle.player,
                side = Side.PLAYER,
                active = uiState.activeSide == Side.PLAYER,
                hit = uiState.hitSide == Side.PLAYER
            )
        }
    }
}

@Composable
private fun CombatantPanel(combatant: Combatant, side: Side, active: Boolean, hit: Boolean) {
    val attackScale by animateFloatAsState(
        targetValue = if (active) 1.08f else 1f,
        animationSpec = tween(180),
        label = "attackScale"
    )
    val hitRotation by animateFloatAsState(
        targetValue = if (hit) 4f else 0f,
        animationSpec = tween(160),
        label = "hitRotation"
    )

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(150.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        if (side == Side.OPPONENT) {
            StatusBox(combatant, Modifier.weight(1f))
            SpriteBox(combatant, side, hit, attackScale, hitRotation)
        } else {
            SpriteBox(combatant, side, hit, attackScale, hitRotation)
            StatusBox(combatant, Modifier.weight(1f))
        }
    }
}

@Composable
private fun SpriteBox(
    combatant: Combatant,
    side: Side,
    hit: Boolean,
    attackScale: Float,
    hitRotation: Float
) {
    val direction = if (side == Side.PLAYER) 1 else -1
    PokemonPixelSprite(
        pokemonId = combatant.pokemon.id,
        side = side,
        flash = hit,
        modifier = Modifier
            .width(138.dp)
            .fillMaxHeight()
            .offset(x = if (attackScale > 1f) (direction * 8).dp else 0.dp)
            .scale(attackScale)
            .graphicsLayer(rotationZ = hitRotation * direction)
    )
}

@Composable
private fun StatusBox(combatant: Combatant, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(3.dp),
        colors = CardDefaults.cardColors(containerColor = Cream)
    ) {
        Column(Modifier.padding(9.dp)) {
            Text(
                combatant.pokemon.name.uppercase(),
                fontFamily = PixelFont,
                fontWeight = FontWeight.Black,
                fontSize = 15.sp,
                color = Ink,
                maxLines = 1
            )
            Text(
                combatant.pokemon.types.joinToString(" / ") { it.displayName },
                fontFamily = PixelFont,
                fontSize = 10.sp,
                color = Color(0xFF475C69),
                maxLines = 1
            )
            Spacer(Modifier.height(7.dp))
            HpBar(combatant.currentHp, combatant.pokemon.maxHp)
            Spacer(Modifier.height(4.dp))
            Text(
                "KP ${combatant.currentHp}/${combatant.pokemon.maxHp}",
                modifier = Modifier.fillMaxWidth(),
                textAlign = TextAlign.End,
                fontFamily = PixelFont,
                fontWeight = FontWeight.Bold,
                fontSize = 11.sp,
                color = Ink
            )
        }
    }
}

@Composable
private fun HpBar(current: Int, maximum: Int) {
    val target = (current.toFloat() / maximum.toFloat()).coerceIn(0f, 1f)
    val progress by animateFloatAsState(targetValue = target, animationSpec = tween(420), label = "hp")
    val hpColor = when {
        target > 0.5f -> Color(0xFF43A047)
        target > 0.2f -> Color(0xFFF9A825)
        else -> Color(0xFFD32F2F)
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text("KP", fontFamily = PixelFont, fontWeight = FontWeight.Black, fontSize = 10.sp, color = Ink)
        Spacer(Modifier.width(5.dp))
        Box(
            Modifier
                .weight(1f)
                .height(12.dp)
                .background(Color(0xFF4C5961), RoundedCornerShape(2.dp))
                .padding(2.dp)
        ) {
            Box(
                Modifier
                    .fillMaxHeight()
                    .fillMaxWidth(progress)
                    .background(hpColor, RoundedCornerShape(1.dp))
            )
        }
    }
}

@Composable
private fun MessagePanel(messages: List<String>) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(4.dp),
        colors = CardDefaults.cardColors(containerColor = Panel)
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            messages.takeLast(4).forEachIndexed { index, message ->
                Text(
                    text = if (index == messages.takeLast(4).lastIndex) "▶ $message" else "  $message",
                    fontFamily = PixelFont,
                    fontSize = if (index == messages.takeLast(4).lastIndex) 13.sp else 11.sp,
                    lineHeight = 17.sp,
                    color = if (index == messages.takeLast(4).lastIndex) Cream else Color(0xFF9FB3C1)
                )
            }
        }
    }
}

@Composable
private fun MoveGrid(moves: List<Move>, enabled: Boolean, onMove: (Int) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        moves.chunked(2).forEachIndexed { rowIndex, rowMoves ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                rowMoves.forEachIndexed { columnIndex, move ->
                    val index = rowIndex * 2 + columnIndex
                    Button(
                        onClick = { onMove(index) },
                        enabled = enabled,
                        modifier = Modifier
                            .weight(1f)
                            .height(72.dp),
                        shape = RoundedCornerShape(4.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = typeColor(move.type),
                            contentColor = Ink,
                            disabledContainerColor = Color(0xFF4F5E68),
                            disabledContentColor = Color(0xFFAFBBC2)
                        ),
                        contentPadding = ButtonDefaults.ContentPadding
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                move.name.uppercase(),
                                fontFamily = PixelFont,
                                fontWeight = FontWeight.Black,
                                fontSize = 12.sp,
                                textAlign = TextAlign.Center,
                                maxLines = 1
                            )
                            Text(
                                "${move.type.displayName} · ST ${move.power} · ${move.accuracy}%",
                                fontFamily = PixelFont,
                                fontSize = 9.sp,
                                textAlign = TextAlign.Center,
                                maxLines = 1
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ResultDialog(
    winner: Winner,
    winningPokemon: String,
    rounds: Int,
    onNewBattle: () -> Unit,
    onHome: () -> Unit
) {
    AlertDialog(
        onDismissRequest = {},
        title = {
            Text(
                if (winner == Winner.PLAYER) "SIEG!" else "NIEDERLAGE",
                fontFamily = PixelFont,
                fontWeight = FontWeight.Black,
                color = if (winner == Winner.PLAYER) Gold else Red
            )
        },
        text = {
            Text(
                "$winningPokemon gewinnt nach $rounds Runden.",
                fontFamily = PixelFont,
                color = Cream
            )
        },
        confirmButton = {
            Button(onClick = onNewBattle) {
                Text("NEUER KAMPF", fontFamily = PixelFont)
            }
        },
        dismissButton = {
            TextButton(onClick = onHome) {
                Text("STARTSEITE", fontFamily = PixelFont, color = Cream)
            }
        },
        containerColor = Panel
    )
}

private fun typeColor(type: ElementType): Color = when (type) {
    ElementType.NORMAL -> Color(0xFFD6D0B8)
    ElementType.FIRE -> Color(0xFFF28C45)
    ElementType.WATER -> Color(0xFF67B7D1)
    ElementType.GRASS -> Color(0xFF78B85A)
    ElementType.ELECTRIC -> Color(0xFFF2D34F)
    ElementType.GROUND -> Color(0xFFC6A36B)
    ElementType.ROCK -> Color(0xFFAAA27A)
    ElementType.FLYING -> Color(0xFFA8B9E8)
}

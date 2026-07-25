package com.chatmcpconnector.pokemonbattle.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val PixelScheme = darkColorScheme(
    primary = Color(0xFFE84545),
    onPrimary = Color(0xFFFFF8E7),
    secondary = Color(0xFFF2CC60),
    onSecondary = Color(0xFF101820),
    background = Color(0xFF101820),
    onBackground = Color(0xFFF4F1DE),
    surface = Color(0xFF1D2A35),
    onSurface = Color(0xFFF4F1DE),
    outline = Color(0xFF8BA6B8)
)

@Composable
fun PokemonBattleTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = PixelScheme,
        typography = MaterialTheme.typography,
        content = content
    )
}

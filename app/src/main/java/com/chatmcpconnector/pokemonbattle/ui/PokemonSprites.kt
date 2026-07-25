package com.chatmcpconnector.pokemonbattle.ui

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import com.chatmcpconnector.pokemonbattle.game.Side

private data class PixelSprite(
    val rows: List<String>,
    val palette: Map<Char, Color>
)

private val sprites = mapOf(
    "pikachu" to PixelSprite(
        rows = listOf(
            "..Y......Y..", ".YY......YY.", ".YK......KY.", "..YYYYYYYY..",
            ".YYYYYYYYYY.", ".YRYYYYYYRY.", ".YYYYKKYYYY.", "..YYYYYYYY..",
            "...YYYYYY...", "..YYYYYYYY..", ".YY.YYYY.YY.", "....Y..Y...."
        ),
        palette = mapOf('Y' to Color(0xFFF4D84A), 'K' to Color(0xFF1B1B1B), 'R' to Color(0xFFE84545))
    ),
    "charmander" to PixelSprite(
        rows = listOf(
            "....OO......", "...OOOO.....", "..OOKKOO....", "..OOOOOO....",
            "...OOOOOO...", "..OOOOOOOO..", ".OOOOOOOOOO.", "..OOOOOOOO..",
            "...OOOOOO.F.", "..OO.OOO.FFF", ".OO..OO...RF", "..O..O......"
        ),
        palette = mapOf('O' to Color(0xFFF28C45), 'K' to Color(0xFF202020), 'F' to Color(0xFFFFC13B), 'R' to Color(0xFFE84545))
    ),
    "squirtle" to PixelSprite(
        rows = listOf(
            "....BB......", "...BBBB.....", "..BBKKBB....", "..BBBBBB....",
            "...BBBBBB...", "..BBTTBBBB..", ".BBBTTTTBBB.", ".BBBTTTTBBB.",
            "..BBTTTTBB..", "...BBBBBB...", "..BB....BB..", "...B....B..."
        ),
        palette = mapOf('B' to Color(0xFF72C7D9), 'K' to Color(0xFF202020), 'T' to Color(0xFFC98A55))
    ),
    "bulbasaur" to PixelSprite(
        rows = listOf(
            "....GG......", "...GGGG.....", "..GDDDDG....", ".GDDDDDDG...",
            ".TTKKKKTT....", "TTTTTTTTTT..", "TDTDTDTDTD..", ".TTTTTTTT....",
            "..TTTTTTT...", ".TT.TTT.TT...", "TT..TT..TT..", "....T...T..."
        ),
        palette = mapOf('T' to Color(0xFF62B8A6), 'D' to Color(0xFF287A4B), 'G' to Color(0xFF6DBF4B), 'K' to Color(0xFF202020))
    ),
    "geodude" to PixelSprite(
        rows = listOf(
            "....SS......", "..SSSSSS....", ".SSSSSSSS...", "SSSKSSKSSS..",
            "SSSSSSSSSS..", ".SSSSSSSS...", "..SSSSSS....", "ASSSSSSSSA..",
            "AA..SS..AA..", "A...SS...A..", "....SS......", "...S..S....."
        ),
        palette = mapOf('S' to Color(0xFF8D8F92), 'K' to Color(0xFF202020), 'A' to Color(0xFF6D6F72))
    ),
    "pidgey" to PixelSprite(
        rows = listOf(
            ".....C......", "....CCC.....", "...CCKCC....", "..CCCCCCC...",
            ".CCBBBBCCC...", "CCBBBBBBCC..", ".CBBBBBBC...", "..CBBBBCC...",
            "...CCCCCC...", "..CC.CC.CC..", ".CC..CC..CC.", ".....C......"
        ),
        palette = mapOf('C' to Color(0xFFB98A5A), 'B' to Color(0xFFF2D1A0), 'K' to Color(0xFF202020))
    )
)

@Composable
fun PokemonPixelSprite(
    pokemonId: String,
    side: Side,
    flash: Boolean,
    modifier: Modifier = Modifier
) {
    val sprite = sprites.getValue(pokemonId)
    Canvas(modifier = modifier) {
        val rows = sprite.rows
        val columns = rows.maxOf { it.length }
        val cell = minOf(size.width / columns, size.height / rows.size)
        val imageWidth = cell * columns
        val xStart = (size.width - imageWidth) / 2f
        for ((rowIndex, row) in rows.withIndex()) {
            for (columnIndex in row.indices) {
                val sourceColumn = if (side == Side.PLAYER) row.lastIndex - columnIndex else columnIndex
                val sourceSymbol = row[sourceColumn]
                val color = sprite.palette[sourceSymbol] ?: continue
                drawRect(
                    color = if (flash) Color.White else color,
                    topLeft = Offset(xStart + columnIndex * cell, rowIndex * cell),
                    size = Size(cell + 0.35f, cell + 0.35f)
                )
            }
        }
    }
}

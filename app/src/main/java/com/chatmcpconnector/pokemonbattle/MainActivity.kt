package com.chatmcpconnector.pokemonbattle

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.chatmcpconnector.pokemonbattle.ui.PokemonBattleApp
import com.chatmcpconnector.pokemonbattle.ui.theme.PokemonBattleTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            PokemonBattleTheme {
                PokemonBattleApp()
            }
        }
    }
}

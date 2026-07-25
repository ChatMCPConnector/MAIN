package com.chatmcpconnector.pokemonbattle.model

data class Move(
    val name: String,
    val type: ElementType,
    val power: Int,
    val accuracy: Int
) {
    init {
        require(name.isNotBlank())
        require(power in 1..120)
        require(accuracy in 1..100)
    }
}

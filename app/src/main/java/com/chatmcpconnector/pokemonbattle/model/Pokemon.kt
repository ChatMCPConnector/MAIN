package com.chatmcpconnector.pokemonbattle.model

data class Pokemon(
    val id: String,
    val name: String,
    val types: List<ElementType>,
    val maxHp: Int,
    val attack: Int,
    val defense: Int,
    val speed: Int,
    val moves: List<Move>
) {
    init {
        require(id.isNotBlank())
        require(name.isNotBlank())
        require(types.size in 1..2)
        require(maxHp > 0)
        require(attack > 0)
        require(defense > 0)
        require(speed > 0)
        require(moves.size == 4)
        require(moves.map { it.name }.distinct().size == 4)
    }
}

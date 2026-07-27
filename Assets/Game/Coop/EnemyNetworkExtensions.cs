namespace Riftbound
{
    public static class EnemyNetworkExtensions
    {
        public static void Initialize(
            this EnemyController enemy,
            GameBootstrap bootstrap,
            EnemyKind kind,
            float scale)
        {
            var networkId = CoopCombatWorld.CreateNetworkId(
                bootstrap.RoomIndex,
                kind,
                enemy.transform.position);
            enemy.Initialize(bootstrap, kind, scale, networkId);
        }
    }
}

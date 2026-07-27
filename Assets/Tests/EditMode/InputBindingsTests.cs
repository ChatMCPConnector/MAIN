using NUnit.Framework;
using UnityEngine.InputSystem;

namespace NeonRift.Tests
{
    public sealed class InputBindingsTests
    {
        [SetUp]
        public void SetUp()
        {
            InputBindings.ResetAll();
        }

        [TearDown]
        public void TearDown()
        {
            InputBindings.ResetAll();
        }

        [Test]
        public void DefaultsMatchDocumentedKeyboardLayout()
        {
            Assert.That(InputBindings.Get(0, PlayerAction.MoveUp), Is.EqualTo(Key.UpArrow));
            Assert.That(InputBindings.Get(0, PlayerAction.Light), Is.EqualTo(Key.Z));
            Assert.That(InputBindings.Get(0, PlayerAction.DashGuard), Is.EqualTo(Key.B));
            Assert.That(InputBindings.Get(1, PlayerAction.MoveUp), Is.EqualTo(Key.W));
            Assert.That(InputBindings.Get(1, PlayerAction.Light), Is.EqualTo(Key.F));
            Assert.That(InputBindings.Get(1, PlayerAction.DashGuard), Is.EqualTo(Key.T));
        }

        [Test]
        public void SetPersistsAChangedBinding()
        {
            InputBindings.Set(0, PlayerAction.Jump, Key.Space);

            Assert.That(InputBindings.Get(0, PlayerAction.Jump), Is.EqualTo(Key.Space));
            Assert.That(InputBindings.Label(0, PlayerAction.Jump), Is.EqualTo("SPACE"));
        }

        [Test]
        public void AssigningAnOccupiedKeySwapsBindings()
        {
            InputBindings.Set(0, PlayerAction.Light, Key.X);

            Assert.That(InputBindings.Get(0, PlayerAction.Light), Is.EqualTo(Key.X));
            Assert.That(InputBindings.Get(0, PlayerAction.Heavy), Is.EqualTo(Key.Z));
        }

        [Test]
        public void ResetPlayerRestoresDefaultsWithoutChangingOtherPlayer()
        {
            InputBindings.Set(0, PlayerAction.Jump, Key.Space);
            InputBindings.Set(1, PlayerAction.Jump, Key.N);

            InputBindings.ResetPlayer(0);

            Assert.That(InputBindings.Get(0, PlayerAction.Jump), Is.EqualTo(Key.V));
            Assert.That(InputBindings.Get(1, PlayerAction.Jump), Is.EqualTo(Key.N));
        }

        [TestCase(Key.Escape)]
        [TestCase(Key.F11)]
        public void ReservedGlobalKeysCannotBeBound(Key key)
        {
            Assert.That(InputBindings.IsBindable(key), Is.False);
            Assert.Throws<System.ArgumentException>(() => InputBindings.Set(0, PlayerAction.Light, key));
        }
    }
}

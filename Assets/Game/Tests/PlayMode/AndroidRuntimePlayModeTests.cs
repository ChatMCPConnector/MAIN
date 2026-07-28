using System.Collections;
using System.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace Riftbound.Tests
{
    public sealed class AndroidRuntimePlayModeTests
    {
        [UnityTest]
        public IEnumerator RuntimeBootstrapCreatesPlayableTouchWorld()
        {
            GameBootstrap game = null;
            for (var frame = 0; frame < 180 && game == null; frame++)
            {
                game = Object.FindFirstObjectByType<GameBootstrap>();
                yield return null;
            }

            Assert.That(game, Is.Not.Null, "GameBootstrap did not start in PlayMode.");

            for (var frame = 0; frame < 180 && game.Player == null; frame++)
                yield return null;

            Assert.That(game.Player, Is.Not.Null, "The runtime bootstrap did not create a player.");
            Assert.That(Camera.main, Is.Not.Null, "The runtime bootstrap did not create a main camera.");

            var eventSystem = EventSystem.current ?? Object.FindFirstObjectByType<EventSystem>();
            Assert.That(eventSystem, Is.Not.Null, "No EventSystem exists for touch input.");
            Assert.That(
                eventSystem.currentInputModule,
                Is.TypeOf<InputSystemUIInputModule>(),
                "The touch UI is not using Unity's Input System module.");

            var hud = Object.FindFirstObjectByType<TouchHud>();
            Assert.That(hud, Is.Not.Null, "The touch HUD was not created.");

            var canvas = hud.GetComponent<Canvas>();
            Assert.That(canvas, Is.Not.Null.And.Property("enabled").True);
            Assert.That(hud.GetComponent<GraphicRaycaster>(), Is.Not.Null);

            var buttons = hud.GetComponentsInChildren<Button>(true);
            Assert.That(buttons.Length, Is.GreaterThanOrEqualTo(4), "Action buttons are missing.");
            var buttonNames = buttons.Select(button => button.gameObject.name).ToArray();
            Assert.That(buttonNames, Does.Contain("ANGRIFF"));
            Assert.That(buttonNames, Does.Contain("DASH"));
            Assert.That(buttonNames, Does.Contain("FÄHIGKEIT"));
            Assert.That(buttonNames, Does.Contain("INVENTAR"));

            var stick = hud.GetComponentInChildren<VirtualStick>(true);
            Assert.That(stick, Is.Not.Null, "The virtual movement stick is missing.");
            Assert.That(stick.target, Is.SameAs(game.Player));
            Assert.That(stick.knob, Is.Not.Null);

            Assert.That(
                Object.FindObjectsByType<EnemyController>(FindObjectsSortMode.None).Length,
                Is.GreaterThan(0),
                "The first combat room contains no enemies.");

            Canvas.ForceUpdateCanvases();
            var stickRect = stick.GetComponent<RectTransform>();
            Assert.That(stickRect.rect.width, Is.GreaterThan(0f));
            Assert.That(stickRect.rect.height, Is.GreaterThan(0f));

            var start = game.Player.transform.position;
            var localTarget = new Vector3(stickRect.rect.width * .22f, 0f, 0f);
            var screenTarget = RectTransformUtility.WorldToScreenPoint(
                null,
                stickRect.TransformPoint(localTarget));
            var pointer = new PointerEventData(eventSystem)
            {
                pointerId = 1,
                position = screenTarget,
                pressPosition = screenTarget,
                button = PointerEventData.InputButton.Left
            };

            stick.OnPointerDown(pointer);
            for (var frame = 0; frame < 20; frame++)
                yield return null;
            stick.OnPointerUp(pointer);

            Assert.That(
                game.Player.transform.position.x,
                Is.GreaterThan(start.x + .05f),
                "Dragging the on-screen stick did not move the player.");
        }
    }
}

# Building the Unity edition

## Requirements

- Unity Editor `6000.3.17f1`
- Windows Build Support (Mono) module
- Internet access for the selected CC0 assets and Unity packages
- A valid Unity license for command-line or CI builds

## Local workflow

1. Open the repository in Unity Hub using the pinned editor version.
2. Wait for Package Manager import to complete.
3. Select **Neon Rift → Prepare Unity project**.
4. Select **Neon Rift → Download or repair CC0 assets**.
5. Select **Neon Rift → Build portable Windows game**.

Output:

```text
build/StandaloneWindows64/NeonRift/NeonRift.exe
```

## Command line

Once the Unity editor is installed and activated:

```powershell
Unity.exe -batchmode -nographics -quit `
  -projectPath . `
  -executeMethod NeonRift.Editor.BuildAutomation.BuildWindows `
  -logFile build-unity.log
```

## GitHub Actions license secrets

GameCI receives the standard Unity activation variables. Configure one supported route:

### License file

- `UNITY_LICENSE`

### Serial activation

- `UNITY_EMAIL`
- `UNITY_PASSWORD`
- `UNITY_SERIAL`

The workflow never prints these secret values. If neither route exists, source validation still runs and Unity-dependent jobs are marked as skipped.

using System;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Security.Cryptography;
using UnityEditor;
using UnityEngine;

namespace NeonRift.Editor
{
    public static class OpenAssetInstaller
    {
        private const string LockRelativePath = "AssetSources/open-assets.lock.json";
        private const string DestinationRelativePath = "Resources/Community/OpenAssets";
        private const string CacheDirectoryName = "OpenAssetCache";
        private const string UserAgent = "NeonRift-Unity-Open-Asset-Installer/1.0";
        private const int MaximumArchiveEntries = 4096;
        private const long MaximumSingleExtractedBytes = 134_217_728;
        private const long MaximumTotalExtractedBytes = 536_870_912;
        private const double MaximumCompressionRatio = 200d;

        [Serializable]
        private sealed class AssetLock
        {
            public int schemaVersion;
            public string generatedAtUtc;
            public AssetEntry[] assets = Array.Empty<AssetEntry>();
        }

        [Serializable]
        private sealed class AssetEntry
        {
            public string provider = string.Empty;
            public string id = string.Empty;
            public string kind = string.Empty;
            public string resolution = string.Empty;
            public string format = string.Empty;
            public string target = string.Empty;
            public string source = string.Empty;
            public string license = string.Empty;
            public string credit = string.Empty;
            public long maxDownloadBytes;
            public DownloadEntry[] files = Array.Empty<DownloadEntry>();
        }

        [Serializable]
        private sealed class DownloadEntry
        {
            public string url = string.Empty;
            public string path = string.Empty;
            public long size;
            public string md5 = string.Empty;
            public bool extract;
        }

        [MenuItem("Neon Rift/Download or repair Poly Haven and ambientCG assets")]
        public static void DownloadFromMenu()
        {
            bool success = EnsureAssets(true, true);
            EditorUtility.DisplayDialog(
                "Neon Rift open assets",
                success
                    ? "All requested Poly Haven and ambientCG assets are available."
                    : "One or more open-asset downloads failed. The existing procedural fallback remains available. Check the Console for details.",
                "OK");
        }

        public static bool EnsureAssets(bool showProgress)
        {
            return EnsureAssets(showProgress, false);
        }

        private static bool EnsureAssets(bool showProgress, bool forceRepair)
        {
            string projectRoot = Directory.GetParent(Application.dataPath)?.FullName ?? Environment.CurrentDirectory;
            string lockPath = Path.Combine(projectRoot, LockRelativePath.Replace('/', Path.DirectorySeparatorChar));
            if (!File.Exists(lockPath))
            {
                Debug.Log("No open-asset lock file is present; skipping Poly Haven and ambientCG downloads.");
                return true;
            }

            AssetLock assetLock;
            try
            {
                assetLock = JsonUtility.FromJson<AssetLock>(File.ReadAllText(lockPath));
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Could not read {LockRelativePath}: {exception.Message}");
                return false;
            }

            if (assetLock == null || assetLock.schemaVersion != 1)
            {
                Debug.LogWarning($"Unsupported or invalid open-asset lock file: {LockRelativePath}");
                return false;
            }

            AssetEntry[] assets = assetLock.assets ?? Array.Empty<AssetEntry>();
            if (assets.Length == 0) return true;

            string destinationRoot = Path.Combine(Application.dataPath, DestinationRelativePath.Replace('/', Path.DirectorySeparatorChar));
            string cacheRoot = Path.Combine(projectRoot, CacheDirectoryName);
            Directory.CreateDirectory(destinationRoot);
            Directory.CreateDirectory(cacheRoot);

            int totalFiles = 0;
            foreach (AssetEntry asset in assets)
            {
                totalFiles += asset?.files?.Length ?? 0;
            }

            bool success = true;
            int fileIndex = 0;
            try
            {
                foreach (AssetEntry asset in assets)
                {
                    if (asset == null)
                    {
                        success = false;
                        continue;
                    }

                    string targetDirectory;
                    try
                    {
                        targetDirectory = SafeChildPath(destinationRoot, asset.target, true);
                    }
                    catch (Exception exception)
                    {
                        Debug.LogWarning($"Rejected target path for {asset.provider}/{asset.id}: {exception.Message}");
                        success = false;
                        continue;
                    }

                    string markerPath = Path.Combine(targetDirectory, ".open-asset.json");
                    if (forceRepair && Directory.Exists(targetDirectory))
                    {
                        Directory.Delete(targetDirectory, true);
                    }
                    else if (File.Exists(markerPath) && VerifyInstalledAsset(asset, targetDirectory))
                    {
                        fileIndex += asset.files?.Length ?? 0;
                        continue;
                    }
                    else if (File.Exists(markerPath))
                    {
                        File.Delete(markerPath);
                        Debug.LogWarning($"Repairing incomplete or corrupted open asset {asset.provider}/{asset.id}.");
                    }

                    Directory.CreateDirectory(targetDirectory);
                    bool assetSuccess = true;
                    DownloadEntry[] files = asset.files ?? Array.Empty<DownloadEntry>();
                    foreach (DownloadEntry file in files)
                    {
                        fileIndex++;
                        if (showProgress)
                        {
                            float progress = totalFiles > 0 ? fileIndex / (float)totalFiles : 1f;
                            EditorUtility.DisplayProgressBar(
                                "Neon Rift open assets",
                                $"{asset.provider}/{asset.id}: {file?.path}",
                                progress);
                        }

                        if (file == null || !TryInstallFile(asset, file, targetDirectory, cacheRoot))
                        {
                            assetSuccess = false;
                            success = false;
                        }
                    }

                    if (assetSuccess)
                    {
                        string marker = JsonUtility.ToJson(asset, true) + Environment.NewLine;
                        File.WriteAllText(markerPath, marker);
                        Debug.Log($"Installed CC0 asset {asset.provider}/{asset.id} ({asset.resolution}, {asset.format}).");
                    }
                }
            }
            finally
            {
                if (showProgress) EditorUtility.ClearProgressBar();
            }

            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            return success;
        }

        private static bool VerifyInstalledAsset(AssetEntry asset, string targetDirectory)
        {
            try
            {
                DownloadEntry[] files = asset.files ?? Array.Empty<DownloadEntry>();
                if (files.Length == 0) return false;

                foreach (DownloadEntry file in files)
                {
                    if (file == null) return false;
                    if (file.extract)
                    {
                        bool hasPayload = false;
                        if (Directory.Exists(targetDirectory))
                        {
                            foreach (string installedFile in Directory.EnumerateFiles(targetDirectory, "*", SearchOption.AllDirectories))
                            {
                                if (!string.Equals(Path.GetFileName(installedFile), ".open-asset.json", StringComparison.OrdinalIgnoreCase))
                                {
                                    hasPayload = true;
                                    break;
                                }
                            }
                        }
                        if (!hasPayload) return false;
                        continue;
                    }

                    string destination = SafeChildPath(targetDirectory, file.path, false);
                    if (!VerifyExisting(destination, file)) return false;
                }
                return true;
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Open asset verification failed ({asset.provider}/{asset.id}): {exception.Message}");
                return false;
            }
        }

        private static bool TryInstallFile(
            AssetEntry asset,
            DownloadEntry file,
            string targetDirectory,
            string cacheRoot)
        {
            try
            {
                if (!Uri.TryCreate(file.url, UriKind.Absolute, out Uri uri) || uri.Scheme != Uri.UriSchemeHttps)
                {
                    throw new InvalidDataException("Only absolute HTTPS download URLs are permitted.");
                }

                long maximumBytes = asset.maxDownloadBytes > 0 ? asset.maxDownloadBytes : 104_857_600;
                if (file.size > maximumBytes)
                {
                    throw new InvalidDataException($"Declared file size {file.size} exceeds limit {maximumBytes}.");
                }

                if (file.extract)
                {
                    string archiveName = SafeCacheName(asset.provider, asset.id, file.path, uri);
                    string archivePath = Path.Combine(cacheRoot, archiveName);
                    if (!VerifyExisting(archivePath, file))
                    {
                        DownloadFile(uri, archivePath, maximumBytes);
                        VerifyDownloaded(archivePath, file);
                    }
                    ExtractZipSafely(archivePath, targetDirectory);
                    return true;
                }

                string destination = SafeChildPath(targetDirectory, file.path, false);
                if (VerifyExisting(destination, file)) return true;
                DownloadFile(uri, destination, maximumBytes);
                VerifyDownloaded(destination, file);
                return true;
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Open asset download failed ({asset.provider}/{asset.id}, {file.url}): {exception.Message}");
                return false;
            }
        }

        private static void DownloadFile(Uri uri, string destination, long maximumBytes)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(destination) ?? Application.dataPath);
            string temporary = destination + ".download";
            if (File.Exists(temporary)) File.Delete(temporary);

            try
            {
                using var client = new HttpClient();
                client.DefaultRequestHeaders.UserAgent.ParseAdd(UserAgent);
                using HttpResponseMessage response = client.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead)
                    .GetAwaiter()
                    .GetResult();
                response.EnsureSuccessStatusCode();
                long? contentLength = response.Content.Headers.ContentLength;
                if (contentLength.HasValue && contentLength.Value > maximumBytes)
                {
                    throw new InvalidDataException($"Remote file is {contentLength.Value} bytes; limit is {maximumBytes}.");
                }

                using Stream source = response.Content.ReadAsStreamAsync().GetAwaiter().GetResult();
                using (var destinationStream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                {
                    var buffer = new byte[81_920];
                    long total = 0;
                    while (true)
                    {
                        int read = source.Read(buffer, 0, buffer.Length);
                        if (read <= 0) break;
                        total += read;
                        if (total > maximumBytes)
                        {
                            throw new InvalidDataException($"Download exceeded limit of {maximumBytes} bytes.");
                        }
                        destinationStream.Write(buffer, 0, read);
                    }
                }

                if (File.Exists(destination)) File.Delete(destination);
                File.Move(temporary, destination);
            }
            finally
            {
                if (File.Exists(temporary)) File.Delete(temporary);
            }
        }

        private static bool VerifyExisting(string path, DownloadEntry file)
        {
            if (!File.Exists(path)) return false;
            try
            {
                VerifyDownloaded(path, file);
                return true;
            }
            catch
            {
                File.Delete(path);
                return false;
            }
        }

        private static void VerifyDownloaded(string path, DownloadEntry file)
        {
            var info = new FileInfo(path);
            if (file.size > 0 && info.Length != file.size)
            {
                throw new InvalidDataException($"Size mismatch for {path}: expected {file.size}, got {info.Length}.");
            }
            if (!string.IsNullOrWhiteSpace(file.md5))
            {
                using MD5 md5 = MD5.Create();
                using FileStream stream = File.OpenRead(path);
                string actual = BitConverter.ToString(md5.ComputeHash(stream)).Replace("-", string.Empty).ToLowerInvariant();
                if (!string.Equals(actual, file.md5.Trim().ToLowerInvariant(), StringComparison.Ordinal))
                {
                    throw new InvalidDataException($"MD5 mismatch for {path}.");
                }
            }
        }

        private static string SafeChildPath(string root, string relative, bool directory)
        {
            if (string.IsNullOrWhiteSpace(relative))
            {
                throw new InvalidDataException("Relative path is empty.");
            }

            string normalized = relative.Replace('\\', '/').TrimStart('/');
            foreach (string part in normalized.Split('/'))
            {
                if (string.IsNullOrWhiteSpace(part) || part == "." || part == "..")
                {
                    throw new InvalidDataException("Relative path contains an unsafe segment.");
                }
            }

            string fullRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                              + Path.DirectorySeparatorChar;
            string candidate = Path.GetFullPath(Path.Combine(root, normalized));
            string comparisonPath = directory
                ? candidate.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar
                : candidate;
            if (!comparisonPath.StartsWith(fullRoot, StringComparison.Ordinal))
            {
                throw new InvalidDataException("Path attempted to leave the open-asset directory.");
            }
            return candidate;
        }

        private static string SafeCacheName(string provider, string id, string path, Uri uri)
        {
            string seed = $"{provider}/{id}/{path}/{uri.AbsoluteUri}";
            using SHA256 sha = SHA256.Create();
            string hash = BitConverter.ToString(sha.ComputeHash(System.Text.Encoding.UTF8.GetBytes(seed)))
                .Replace("-", string.Empty)
                .ToLowerInvariant();
            string extension = Path.GetExtension(uri.AbsolutePath);
            if (!string.Equals(extension, ".zip", StringComparison.OrdinalIgnoreCase)) extension = ".zip";
            return hash + extension;
        }

        private static void ExtractZipSafely(string archivePath, string targetDirectory)
        {
            string fullTarget = Path.GetFullPath(targetDirectory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                                + Path.DirectorySeparatorChar;
            using ZipArchive archive = ZipFile.OpenRead(archivePath);
            if (archive.Entries.Count > MaximumArchiveEntries)
            {
                throw new InvalidDataException($"Archive contains {archive.Entries.Count} entries; limit is {MaximumArchiveEntries}.");
            }

            long totalExtractedBytes = 0;
            foreach (ZipArchiveEntry entry in archive.Entries)
            {
                int unixType = (entry.ExternalAttributes >> 16) & 0xF000;
                if (unixType == 0xA000)
                {
                    throw new InvalidDataException("Archive contains a symbolic link, which is not permitted.");
                }
                if (entry.Length > MaximumSingleExtractedBytes)
                {
                    throw new InvalidDataException($"Archive entry {entry.FullName} is too large ({entry.Length} bytes).");
                }
                if (entry.Length > 0 && entry.CompressedLength == 0)
                {
                    throw new InvalidDataException($"Archive entry {entry.FullName} has an invalid compression size.");
                }
                if (entry.CompressedLength > 0 && entry.Length / (double)entry.CompressedLength > MaximumCompressionRatio)
                {
                    throw new InvalidDataException($"Archive entry {entry.FullName} exceeds the compression-ratio limit.");
                }
                if (entry.Length > MaximumTotalExtractedBytes - totalExtractedBytes)
                {
                    throw new InvalidDataException($"Archive expands beyond {MaximumTotalExtractedBytes} bytes.");
                }
                totalExtractedBytes += entry.Length;

                string destination = Path.GetFullPath(Path.Combine(targetDirectory, entry.FullName));
                if (!destination.StartsWith(fullTarget, StringComparison.Ordinal))
                {
                    throw new InvalidDataException("Archive entry attempted to leave the target directory.");
                }
                if (string.IsNullOrEmpty(entry.Name))
                {
                    Directory.CreateDirectory(destination);
                    continue;
                }
                Directory.CreateDirectory(Path.GetDirectoryName(destination) ?? targetDirectory);
                entry.ExtractToFile(destination, true);
            }
        }
    }
}

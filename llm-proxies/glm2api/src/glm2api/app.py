from __future__ import annotations

import errno
import signal
import traceback

from .config import AppConfig, ConfigError, load_config
from .logging_utils import get_logger, setup_logging
from .server import GLM2APIServer
from .services.glm_client import GLMWebClient


class StartupError(RuntimeError):
    pass


class Application:
    def __init__(self, config: AppConfig) -> None:
        setup_logging(config.log_level)
        self.config = config
        self.logger = get_logger("glm2api.app")
        self.logger.info(
            "Application initialized concurrency=%s accounts=%s exposed_models=%s",
            config.glm_max_concurrency,
            len(config.glm_refresh_tokens),
            len(config.exposed_models),
        )
        self.client = GLMWebClient(config=config, logger=get_logger("glm2api.glm"))
        try:
            self.server = GLM2APIServer(
                config=config,
                glm_client=self.client,
                logger=get_logger("glm2api.http"),
            )
        except OSError as exc:
            raise self._wrap_server_error(exc) from exc
        except Exception as exc:
            raise StartupError(f"Failed to initialize HTTP service: {exc}") from exc
        self._stopping = False
        self._install_signal_handlers()

    def run(self) -> None:
        if self.config.env_file_created:
            self.logger.info("No config file found, automatically copied from default example: %s", self.config.env_file_path)
        self.logger.info(
            "Starting service host=%s port=%s prefix=%s accounts=%s debug_dump_all=%s models=%s",
            self.config.host,
            self.config.port,
            self.config.api_prefix,
            len(self.config.glm_refresh_tokens),
            self.config.debug_dump_all,
            ",".join(self.config.exposed_models),
        )
        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            self.logger.info("Received Ctrl+C, shutting down service gracefully...")
        except OSError as exc:
            self.logger.error("HTTP service runtime error error=%s", exc)
            raise StartupError(f"HTTP service run failed: {exc}") from exc
        except Exception as exc:
            self.logger.error("Service exited abnormally error=%s\n%s", exc, traceback.format_exc())
            raise
        finally:
            self.stop()

    def stop(self) -> None:
        if self._stopping:
            return
        self._stopping = True
        self.logger.info("Stopping HTTP service and releasing listen port...")
        try:
            self.server.shutdown()
        except Exception as exc:
            self.logger.warning("Exception while closing HTTP service error=%s", exc)
        self.logger.info("glm2api exited")

    def _install_signal_handlers(self) -> None:
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(signum, self._handle_signal)
            except (ValueError, AttributeError):
                continue

    def _handle_signal(self, signum: int, frame) -> None:
        signal_name = signal.Signals(signum).name
        self.logger.info("Received exit signal %s, preparing to shut down service...", signal_name)
        raise KeyboardInterrupt

    def _wrap_server_error(self, exc: OSError) -> StartupError:
        if exc.errno in {errno.EADDRINUSE, 10048}:
            return StartupError(f"Port already in use: {self.config.host}:{self.config.port}")
        if exc.errno in {errno.EACCES, 10013}:
            return StartupError(f"No permission to listen on address: {self.config.host}:{self.config.port}")
        if exc.errno in {errno.EADDRNOTAVAIL, 10049}:
            return StartupError(f"Listen address not available: {self.config.host}")
        return StartupError(f"Failed to start HTTP service: {exc}")


def create_application() -> Application:
    try:
        config = load_config()
    except ConfigError:
        raise
    except Exception as exc:
        raise StartupError(f"Failed to read config: {exc}") from exc
    return Application(config)

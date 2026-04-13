# Standard library imports
import dataclasses
import threading
from typing import override

# Local application/library specific imports
import web_server._logic as web_server_logic
from . import _logic as logic
import util.const
import web_server

SERVER_MODE_TYPE = web_server_logic.server_mode


@dataclasses.dataclass(kw_only=True, unsafe_hash=True)
class obj_type(logic.gameconfig_entry, logic.loggable_entry):
    web_port: int = util.const.RFD_DEFAULT_PORT
    is_ipv6: bool
    is_ssl: bool
    frontend_proxy: str | None = None
    rbolock_proxy_port: int | None = dataclasses.field(
        default_factory=lambda: 443,
    )
    rbolock_http_proxy_port: int | None = dataclasses.field(
        default_factory=lambda: 80,
    )

    server_mode: SERVER_MODE_TYPE
    httpd: web_server_logic.web_server | None = None
    proxy = None

    def __post_init__(self) -> None:
        super().__post_init__()
        self.threads: list[threading.Thread] = []

    @override
    def process(self) -> None:
        super().process()
        self.httpd = web_server.make_server(
            self.web_port,
            self.is_ssl,
            self.is_ipv6,
            self.game_config,
            self.server_mode,
            self.logger,
            frontend_proxy=self.frontend_proxy,
        )
        self._start_rbolock_proxy()

        th = threading.Thread(
            target=self.httpd.serve_forever,
            daemon=True,
        )
        self.threads.append(th)
        th.start()

    @override
    def stop(self) -> None:
        proxy = self.proxy
        if proxy is not None:
            proxy.stop()
            self.proxy = None
        if self.httpd is None:
            return
        self.httpd.shutdown()
        self.httpd.server_close()
        self.httpd = None
        super().stop()

    def _start_rbolock_proxy(self) -> None:
        if (
            not self.is_ssl or
            self.is_ipv6 or
            self.httpd is None
        ):
            return

        import util.ssl_context
        from web_server.proxy import RoblockProxy, RoblockProxyGroup

        cert_path, key_path = util.ssl_context.get_server_cert_paths()
        proxies: list[RoblockProxy] = []

        def try_start_proxy(
            proxy: RoblockProxy,
            port: int | None,
            scheme: str,
        ) -> None:
            if (
                port is None or
                port == self.web_port
            ):
                return

            proxy.set_target('127.0.0.1', self.web_port)
            try:
                proxy.start()
            except OSError as error:
                self.log(
                    'Failed to start %s rbolock proxy on port %d: %s' % (
                        scheme,
                        port,
                        error,
                    )
                )
                return

            proxies.append(proxy)
            self.log(
                'Started %s rbolock proxy on 127.0.0.1:%d -> 127.0.0.1:%d' % (
                    scheme,
                    port,
                    self.web_port,
                )
            )

        try_start_proxy(
            RoblockProxy(
                self.rbolock_proxy_port,
                cert_path,
                key_path,
                listen_tls=True,
                upstream_tls=self.is_ssl,
            ),
            self.rbolock_proxy_port,
            'HTTPS',
        )
        try_start_proxy(
            RoblockProxy(
                self.rbolock_http_proxy_port,
                listen_tls=False,
                upstream_tls=self.is_ssl,
            ),
            self.rbolock_http_proxy_port,
            'HTTP',
        )

        if not proxies:
            return

        proxy_group = RoblockProxyGroup(*proxies)
        self.proxy = proxy_group
        self.httpd.proxy = proxy_group

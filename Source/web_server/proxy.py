from __future__ import annotations

import socket
import ssl
import threading


class RoblockProxy:
    def __init__(
        self,
        listen_port: int,
        cert_path: str | None = None,
        key_path: str | None = None,
        *,
        listen_tls: bool = True,
        upstream_tls: bool = True,
    ) -> None:
        self.listen_port = listen_port
        self.cert_path = cert_path
        self.key_path = key_path
        self.listen_tls = listen_tls
        self.upstream_tls = upstream_tls
        self._target_host = '127.0.0.1'
        self._target_port = listen_port
        self._lock = threading.Lock()
        self._started = False
        self._stopped = threading.Event()
        self._socket: socket.socket | None = None

    def set_target(self, host: str, port: int) -> None:
        with self._lock:
            self._target_host = host
            self._target_port = port

    def get_target(self) -> tuple[str, int]:
        with self._lock:
            return (self._target_host, self._target_port)

    def start(self) -> None:
        if self._started:
            return
        self._started = True

        raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        raw_socket.bind(('127.0.0.1', self.listen_port))
        raw_socket.listen(32)
        if self.listen_tls:
            if self.cert_path is None or self.key_path is None:
                raise ValueError(
                    'TLS listener requires certificate and key paths.'
                )
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(self.cert_path, self.key_path)
            self._socket = context.wrap_socket(raw_socket, server_side=True)
        else:
            self._socket = raw_socket

        threading.Thread(
            target=self._accept_loop,
            daemon=True,
            name='rbolock-proxy',
        ).start()

    def stop(self) -> None:
        self._stopped.set()
        if self._socket is None:
            return
        try:
            self._socket.close()
        except OSError:
            pass
        self._socket = None

    def _pipe(
        self,
        source: socket.socket,
        target: socket.socket,
        done: threading.Event,
    ) -> None:
        try:
            while not self._stopped.is_set():
                payload = source.recv(4096)
                if not payload:
                    break
                target.sendall(payload)
        except OSError:
            pass
        finally:
            done.set()

    def _read_http_head(self, client_conn: socket.socket) -> bytes:
        buffer = bytearray()
        while b'\r\n\r\n' not in buffer and len(buffer) < 64 * 1024:
            chunk = client_conn.recv(4096)
            if not chunk:
                break
            buffer.extend(chunk)
        return bytes(buffer)

    def _handle(self, client_conn: socket.socket) -> None:
        target_host, target_port = self.get_target()
        try:
            raw_upstream = socket.create_connection(
                (target_host, target_port),
                timeout=10,
            )
            if self.upstream_tls:
                upstream_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                upstream_context.check_hostname = False
                upstream_context.verify_mode = ssl.CERT_NONE
                upstream_conn = upstream_context.wrap_socket(
                    raw_upstream,
                    server_hostname=target_host,
                )
            else:
                upstream_conn = raw_upstream
        except OSError:
            try:
                client_conn.sendall(
                    b'HTTP/1.1 502 Bad Gateway\r\n'
                    b'Content-Length: 0\r\n\r\n'
                )
            except OSError:
                pass
            client_conn.close()
            return

        try:
            request_head = self._read_http_head(client_conn)
            if request_head:
                upstream_conn.sendall(request_head)
        except OSError:
            for connection in (client_conn, upstream_conn):
                try:
                    connection.close()
                except OSError:
                    pass
            return

        done = threading.Event()
        threading.Thread(
            target=self._pipe,
            args=(upstream_conn, client_conn, done),
            daemon=True,
        ).start()
        self._pipe(client_conn, upstream_conn, done)
        done.wait(timeout=10)

        for connection in (client_conn, upstream_conn):
            try:
                connection.close()
            except OSError:
                pass

    def _accept_loop(self) -> None:
        assert self._socket is not None
        while not self._stopped.is_set():
            try:
                connection, _ = self._socket.accept()
            except OSError:
                if self._stopped.is_set():
                    break
                continue

            threading.Thread(
                target=self._handle,
                args=(connection,),
                daemon=True,
            ).start()


class RoblockProxyGroup:
    def __init__(self, *proxies: RoblockProxy) -> None:
        self._proxies = list(proxies)

    def set_target(self, host: str, port: int) -> None:
        for proxy in self._proxies:
            proxy.set_target(host, port)

    def stop(self) -> None:
        for proxy in self._proxies:
            proxy.stop()

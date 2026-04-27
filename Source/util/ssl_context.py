from __future__ import annotations

import functools
import os
import platform
import subprocess
import tempfile

import trustme

import logger


PROJECT_ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
PROJECT_SSL_DIR = os.path.join(PROJECT_ROOT_DIR, 'ssl')
RBOLOCK_REQUIRED_HOSTS = [
    '127.0.0.1 rbolock.tk',
    '127.0.0.1 www.rbolock.tk',
    '127.0.0.1 api.rbolock.tk',
    '127.0.0.1 apis.rbolock.tk',
    '127.0.0.1 auth.rbolock.tk',
    '127.0.0.1 avatar.rbolock.tk',
    '127.0.0.1 accountsettings.rbolock.tk',
    '127.0.0.1 assetgame.rbolock.tk',
    '127.0.0.1 assetdelivery.rbolock.tk',
    '127.0.0.1 catalog.rbolock.tk',
    '127.0.0.1 clientsettings.rbolock.tk',
    '127.0.0.1 clientsettingscdn.rbolock.tk',
    '127.0.0.1 develop.rbolock.tk',
    '127.0.0.1 economy.rbolock.tk',
    '127.0.0.1 ecsv2.rbolock.tk',
    '127.0.0.1 friends.rbolock.tk',
    '127.0.0.1 gameinternationalization.rbolock.tk',
    '127.0.0.1 gamejoin.rbolock.tk',
    '127.0.0.1 locale.rbolock.tk',
    '127.0.0.1 metrics.rbolock.tk',
    '127.0.0.1 notifications.rbolock.tk',
    '127.0.0.1 presence.rbolock.tk',
    '127.0.0.1 privatemessages.rbolock.tk',
    '127.0.0.1 realtime-signalr.rbolock.tk',
    '127.0.0.1 thumbnails.rbolock.tk',
    '127.0.0.1 usermoderation.rbolock.tk',
    '127.0.0.1 users.rbolock.tk',
]

RBOLOCK_SERVER_HOSTS = (
    'localhost',
    '127.0.0.1',
    '::1',
    'rbolock.tk',
    'www.rbolock.tk',
    'api.rbolock.tk',
    'apis.rbolock.tk',
    'auth.rbolock.tk',
    'avatar.rbolock.tk',
    'accountsettings.rbolock.tk',
    'assetgame.rbolock.tk',
    'assetdelivery.rbolock.tk',
    'catalog.rbolock.tk',
    'clientsettings.rbolock.tk',
    'clientsettingscdn.rbolock.tk',
    'develop.rbolock.tk',
    'economy.rbolock.tk',
    'ecsv2.rbolock.tk',
    'friends.rbolock.tk',
    'gameinternationalization.rbolock.tk',
    'gamejoin.rbolock.tk',
    'locale.rbolock.tk',
    'metrics.rbolock.tk',
    'notifications.rbolock.tk',
    'presence.rbolock.tk',
    'privatemessages.rbolock.tk',
    'realtime-signalr.rbolock.tk',
    'thumbnails.rbolock.tk',
    'usermoderation.rbolock.tk',
    'users.rbolock.tk',
    '*.rbolock.tk',
    '*.api.rbolock.tk',
)
RBLXHUB_CERT_CANDIDATES = (
    (
        os.path.join(PROJECT_SSL_DIR, 'wildcard.crt'),
        os.path.join(PROJECT_SSL_DIR, 'wildcard.key'),
        os.path.join(PROJECT_SSL_DIR, 'rbolock-ca.crt'),
    ),
)
LOCALHOST_CERT_CANDIDATES = (
    (
        os.path.join(PROJECT_ROOT_DIR, 'server.pem'),
        os.path.join(PROJECT_ROOT_DIR, 'server-key.pem'),
    ),
)


@functools.cache
def get_rblxhub_cert_paths() -> tuple[str, str, str] | None:
    for cert_path, key_path, ca_path in RBLXHUB_CERT_CANDIDATES:
        if not os.path.isfile(cert_path):
            continue
        if not os.path.isfile(key_path):
            continue
        if not os.path.isfile(ca_path):
            continue
        return (cert_path, key_path, ca_path)
    return None


@functools.cache
def get_localhost_cert_paths() -> tuple[str, str] | None:
    for cert_path, key_path in LOCALHOST_CERT_CANDIDATES:
        if not os.path.isfile(cert_path):
            continue
        if not os.path.isfile(key_path):
            continue
        return (cert_path, key_path)
    return None


def use_rblxhub_certs() -> bool:
    return get_rblxhub_cert_paths() is not None


def _get_ca_storage_dir() -> str:
    return os.path.join(os.path.expanduser('~'), '.rfd')


def _get_ca_paths() -> tuple[str, str]:
    storage_dir = _get_ca_storage_dir()
    return (
        os.path.join(storage_dir, 'ca.pem'),
        os.path.join(storage_dir, 'ca_key.pem'),
    )


class _PemBlob:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def bytes(self) -> bytes:
        return self._data

    def write_to_path(
        self,
        path: str,
        *,
        append: bool = False,
    ) -> None:
        mode = 'ab' if append else 'wb'
        with open(path, mode) as file:
            file.write(self._data)


@functools.cache
def _get_or_create_persistent_ca() -> tuple[bytes, bytes]:
    cert_path, key_path = _get_ca_paths()
    if os.path.isfile(cert_path) and os.path.isfile(key_path):
        with open(cert_path, 'rb') as file:
            cert_pem = file.read()
        with open(key_path, 'rb') as file:
            key_pem = file.read()
        return (cert_pem, key_pem)

    ca = trustme.CA(key_type=trustme.KeyType.RSA)
    cert_pem = ca.cert_pem.bytes()
    key_pem = ca.private_key_pem.bytes()

    os.makedirs(_get_ca_storage_dir(), exist_ok=True)
    with open(cert_path, 'wb') as file:
        file.write(cert_pem)
    with open(key_path, 'wb') as file:
        file.write(key_pem)
    return (cert_pem, key_pem)


@functools.cache
def get_shared_ca():
    cert_path, key_path = _get_ca_paths()
    if os.path.isfile(cert_path) and os.path.isfile(key_path):
        import datetime
        import ipaddress

        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        with open(key_path, 'rb') as file:
            ca_key = serialization.load_pem_private_key(
                file.read(),
                password=None,
                backend=default_backend(),
            )
        with open(cert_path, 'rb') as file:
            ca_cert = x509.load_pem_x509_certificate(
                file.read(),
                default_backend(),
            )

        def issue_cert(*hostnames: str):
            san_entries = []
            for hostname in hostnames:
                try:
                    san_entries.append(
                        x509.IPAddress(ipaddress.ip_address(hostname))
                    )
                except ValueError:
                    san_entries.append(x509.DNSName(hostname))

            key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend(),
            )
            cert = (
                x509.CertificateBuilder()
                .subject_name(x509.Name([
                    x509.NameAttribute(NameOID.COMMON_NAME, hostnames[0]),
                ]))
                .issuer_name(ca_cert.subject)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.datetime.now(datetime.UTC))
                .not_valid_after(
                    datetime.datetime.now(datetime.UTC) +
                    datetime.timedelta(days=365)
                )
                .add_extension(
                    x509.SubjectAlternativeName(san_entries),
                    critical=False,
                )
                .sign(ca_key, hashes.SHA256(), default_backend())
            )

            cert_pem = cert.public_bytes(serialization.Encoding.PEM)
            key_pem = key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
            chain = [
                cert_pem,
                _get_or_create_persistent_ca()[0],
            ]

            class Result:
                cert_chain_pems = [_PemBlob(blob) for blob in chain]
                private_key_pem = _PemBlob(key_pem)

            return Result()

        class PersistentCA:
            pass

        PersistentCA.cert_pem = property(
            lambda _self: _PemBlob(_get_or_create_persistent_ca()[0])
        )
        PersistentCA.private_key_pem = property(
            lambda _self: _PemBlob(_get_or_create_persistent_ca()[1])
        )
        PersistentCA.issue_cert = staticmethod(issue_cert)
        return PersistentCA()

    ca = trustme.CA(key_type=trustme.KeyType.RSA)
    os.makedirs(_get_ca_storage_dir(), exist_ok=True)
    with open(cert_path, 'wb') as file:
        file.write(ca.cert_pem.bytes())
    with open(key_path, 'wb') as file:
        file.write(ca.private_key_pem.bytes())
    return ca


def get_ca_pem_bytes() -> bytes:
    rblxhub_paths = get_rblxhub_cert_paths()
    if rblxhub_paths is not None:
        (_, _, ca_path) = rblxhub_paths
        with open(ca_path, 'rb') as file:
            return file.read()
    return _get_or_create_persistent_ca()[0]


@functools.cache
def get_server_cert_paths() -> tuple[str, str]:
    rblxhub_paths = get_rblxhub_cert_paths()
    if rblxhub_paths is not None:
        cert_path, key_path, _ = rblxhub_paths
        return (cert_path, key_path)

    temp_dir = tempfile.mkdtemp(prefix='rfd-certs-')
    cert_path = os.path.join(temp_dir, 'server.crt')
    key_path = os.path.join(temp_dir, 'server.key')

    cert = get_shared_ca().issue_cert(*RBOLOCK_SERVER_HOSTS)
    for index, blob in enumerate(cert.cert_chain_pems):
        blob.write_to_path(
            cert_path,
            append=index > 0,
        )
    cert.private_key_pem.write_to_path(key_path)
    return (cert_path, key_path)


def _host_present(existing_hosts: str, entry: str) -> bool:
    domain = entry.split(maxsplit=1)[1]
    for raw_line in existing_hosts.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if domain in line and '127.0.0.1' in line:
            return True
    return False


def _ensure_rbolock_hosts(log_filter: logger.obj_type) -> None:
    if platform.system() != 'Windows':
        return

    hosts_path = r'C:\Windows\System32\drivers\etc\hosts'
    try:
        with open(hosts_path, 'r', encoding='utf-8', errors='replace') as file:
            existing = file.read()
    except OSError:
        log_filter.log(
            'Cannot read hosts file. Add manually: ' + ', '.join(RBOLOCK_REQUIRED_HOSTS),
            logger.log_context.PYTHON_SETUP,
            is_error=True,
        )
        return

    missing = [
        line
        for line in RBOLOCK_REQUIRED_HOSTS
        if not _host_present(existing, line)
    ]
    if not missing:
        return

    log_filter.log(
        'Add these entries to your hosts file:\n  ' + '\n  '.join(missing),
        logger.log_context.PYTHON_SETUP,
        is_error=False,
    )


def _is_ca_already_installed() -> bool:
    if platform.system() != 'Windows':
        return False

    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend

        cert = x509.load_pem_x509_certificate(
            get_ca_pem_bytes(),
            default_backend(),
        )
        common_names = cert.subject.get_attributes_for_oid(
            x509.oid.NameOID.COMMON_NAME
        )
        if not common_names:
            return False

        subject_common_name = common_names[0].value
        result = subprocess.run(
            ['certutil', '-store', 'root'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return subject_common_name in result.stdout
    except Exception:
        return False


def install_ca_to_windows_root(log_filter: logger.obj_type) -> None:
    if platform.system() != 'Windows':
        return
    if _is_ca_already_installed():
        return

    temp_path = os.path.join(tempfile.gettempdir(), 'rfd-ca.pem')
    with open(temp_path, 'wb') as file:
        file.write(get_ca_pem_bytes())

    log_filter.log(
        (
            'Certificate authority is not installed in Windows Root store. '
            'Install manually if you want the browser to trust rbolock.tk without warnings:\n'
            f'  certutil -addstore root "{temp_path}"'
        ),
        logger.log_context.PYTHON_SETUP,
        is_error=False,
    )

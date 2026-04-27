# Standard library imports
from typing import IO, ClassVar, override
import dataclasses
import functools
import subprocess
import threading
import time
import json
import os
import uuid

# Local application imports
from config_type.types import wrappers
from routines.rcc import startup_scripts, log_action
import assets
from .. import _logic as logic
import util.const as const
import util.resource
import util.ssl_context
import util.versions
import logger


@dataclasses.dataclass(kw_only=True, unsafe_hash=True)
class obj_type(logic.bin_entry, logic.gameconfig_entry):
    '''
    Routine entry for newer clients. Launches RobloxStudioBeta.exe as the game
    server instead of RCCService.exe, which was not leaked past 2021.
    '''

    BIN_SUBTYPE = util.resource.bin_subtype.STUDIO
    DIRS_TO_ADD: ClassVar = ['logs', 'LocalStorage']

    track_file_changes: bool = True
    rcc_port: int

    place_iden: int = const.PLACE_IDEN_CONST
    parent_pid: int = dataclasses.field(init=False, default=0)
    parent_session_guid: str = dataclasses.field(init=False, default='')
    play_test_session_guid: str = dataclasses.field(init=False, default='')

    @dataclasses.dataclass(frozen=True)
    class launch_context:
        place_id: int
        universe_id: int
        creator_id: int
        creator_type: int

    @override
    def __post_init__(self) -> None:
        super().__post_init__()
        (
            self.web_port, self.rcc_port,
        ) = self.maybe_differenciate_web_and_rcc_stuff(
            self.web_port, self.rcc_port,
        )

    @override
    def get_base_url(self) -> str:
        if util.ssl_context.use_rblxhub_certs():
            return f'https://www.rbolock.tk:{self.web_port}'
        return f'https://{self.web_host}:{self.web_port}'

    @override
    def get_app_base_url(self) -> str:
        if util.ssl_context.use_rblxhub_certs():
            return f'https://www.rbolock.tk:{self.web_port}/'
        return f'https://localhost:{self.web_port}/'

    @override
    def retr_version(self) -> util.versions.rōblox:
        return self.game_config.game_setup.roblox_version

    @functools.cache
    def setup_place_local(self) -> str:
        '''
        Stages the place file to a stable local path without spaces.
        Newer Studio StartServer launches are fragile here and can fail to open
        direct local paths from arbitrary user directories.
        '''
        rbx_uri = self.game_config.server_core.place_file.rbxl_uri
        new_dir = util.resource.retr_full_path(
            util.resource.dir_type.MISC,
            'StudioServerCache',
        )
        os.makedirs(new_dir, exist_ok=True)
        new_path = os.path.join(
            new_dir,
            f'place_{self.place_iden}_{self.rcc_port}.rbxl',
        )

        if rbx_uri.uri_type == wrappers.uri_type.LOCAL:
            assert isinstance(rbx_uri.value, wrappers.path_str)
            with open(str(rbx_uri.value), 'rb') as f:
                rbxl_data = f.read()
        else:
            rbxl_data = rbx_uri.extract()

        if rbxl_data is None:
            raise Exception('RBXL was not found.')

        with open(new_path, 'wb') as f:
            f.write(rbxl_data)
        return os.path.normpath(new_path)

    def get_team_test_place_path(self) -> str:
        local_appdata = os.getenv('LOCALAPPDATA')
        if local_appdata is None:
            local_appdata = util.resource.retr_full_path(
                util.resource.dir_type.MISC,
            )
        roblox_dir = os.path.join(local_appdata, 'Roblox')
        os.makedirs(roblox_dir, exist_ok=True)
        return os.path.join(roblox_dir, 'server.rbxl')

    def save_team_test_place_file(self) -> str:
        place_uri = self.game_config.server_core.place_file.rbxl_uri
        if place_uri.uri_type == wrappers.uri_type.LOCAL:
            assert isinstance(place_uri.value, wrappers.path_str)
            with open(str(place_uri.value), 'rb') as f:
                raw_data = f.read()
        else:
            raw_data = place_uri.extract()

        if raw_data is None:
            raise Exception('RBXL was not found.')

        team_test_path = self.get_team_test_place_path()
        with open(team_test_path, 'wb') as f:
            f.write(raw_data)
        return os.path.normpath(team_test_path)

    def save_place_file(self) -> None:
        '''
        Parses and copies the place file to the asset cache so the player
        can fetch it via PlaceFetchUrl (asset/?id=1818).
        '''
        config = self.game_config
        place_uri = config.server_core.place_file.rbxl_uri
        cache = config.asset_cache
        raw_data = place_uri.extract()
        if raw_data is None:
            raise Exception(f'Failed to extract data from {place_uri}.')
        rbxl_data, _changed = assets.serialisers.parse(
            raw_data, {assets.serialisers.method.rbxl}
        )
        cache.add_asset(self.place_iden, rbxl_data)

    def save_thumbnail(self) -> None:
        config = self.game_config
        cache = config.asset_cache
        icon_uri = config.server_core.metadata.icon_uri
        if icon_uri is None:
            return
        try:
            thumbnail_data = icon_uri.extract() or bytes()
            cache.add_asset(const.THUMBNAIL_ID_CONST, thumbnail_data)
        except Exception:
            self.logger.log(
                text='Warning: thumbnail data not found.',
                context=logger.log_context.PYTHON_SETUP,
            )

    def resolve_launch_context(self) -> "obj_type.launch_context":
        place_id = int(self.place_iden)
        universe_id = 0
        creator_id = 0
        creator_type = 0

        storage = self.game_config.storage
        universe_row = None
        resolved_universe_id = storage.universe.get_id_from_root_place_id(place_id)
        if resolved_universe_id is not None:
            universe_id = int(resolved_universe_id)
            universe_row = storage.universe.check(universe_id)

        if universe_row is None:
            place_obj = storage.place.check_object(place_id)
            if place_obj is not None and place_obj.parent_universe_id is not None:
                universe_id = int(place_obj.parent_universe_id)
                universe_row = storage.universe.check(universe_id)

        if universe_row is not None:
            creator_id = int(universe_row[1])
            creator_type = int(universe_row[2])

        if creator_id <= 0:
            asset_obj = storage.asset.resolve_object(place_id)
            if asset_obj is not None:
                creator_id = int(asset_obj.creator_id)
                creator_type = int(asset_obj.creator_type)

        return self.launch_context(
            place_id=place_id,
            universe_id=universe_id,
            creator_id=creator_id,
            creator_type=creator_type,
        )

    def gen_cmd_args(self) -> tuple[str, ...]:
        launch_context = self.resolve_launch_context()
        return (
            '-placeVersion', '0',
            '-creatorId', str(launch_context.creator_id),
            '-task', 'StartServer',
            '-universeId', str(launch_context.universe_id),
            '-placeId', str(launch_context.place_id),
            '-port', str(self.rcc_port),
            '-creatorType', str(launch_context.creator_type),
            '-numTestServerPlayersUponStartup', '0',
            '-userid', '1',
            '-parentPid', str(self.parent_pid),
            '-parentSessionGuid', self.parent_session_guid,
            '-instanceId', 'StudioServer',
            '-playTestSessionGuid', self.play_test_session_guid
        )

    def read_server_output(self) -> None: # doesnt work
        '''
        Pipes Server.exe stdout to the logger, mirrors rcc.read_rcc_output.
        '''
        stdout: IO[bytes] = self.popen_mains[0].stdout  # pyright: ignore[reportAssignmentType]
        assert stdout is not None
        while True:
            line = stdout.readline()
            if not line:
                break
            self.logger.log(
                line.rstrip(b'\r\n'),
                context=logger.log_context.RCC_SERVER,
            )
            action = log_action.check(line)
            if action == log_action.LogAction.RESTART:
                threading.Thread(target=self.restart).start()
                break
            elif action == log_action.LogAction.TERMINATE:
                threading.Thread(target=self.kill).start()
                break
        stdout.flush()

    def run_injector(self) -> None:
        '''
        Runs Injector.exe against the already-started Server.exe process,
        injecting local_rcc.dll.  Mirrors the GUI launcher:
            Injector.exe --process-id <pid> --inject local_rcc.dll
        '''
        server_proc = self.popen_mains[0]
        if server_proc.pid is None:
            self.logger.log(
                'Warning: Server.exe PID unavailable, skipping injection.',
                context=logger.log_context.PYTHON_SETUP,
            )
            return

        injector_path = self.get_versioned_path('Injector.exe')
        dll_path      = self.get_versioned_path('local_rcc.dll')

        try:
            subprocess.run(
                [
                    injector_path,
                    '--process-id', str(server_proc.pid),
                    '--inject',     dll_path,
                ],
                check=True,
            )
        except FileNotFoundError:
            self.logger.log(
                'Warning: Injector.exe not found, skipping injection.',
                context=logger.log_context.PYTHON_SETUP,
            )
        except subprocess.CalledProcessError as e:
            self.logger.log(
                f'Warning: Injector.exe exited with code {e.returncode}.',
                context=logger.log_context.PYTHON_SETUP,
            )

    def make_popen_threads(self) -> None:
        self.init_popen(
            exe_path=self.get_versioned_path('RobloxStudioBeta.exe'),
            cmd_args=self.gen_cmd_args(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            # env={**os.environ, 'LOCAL_RCC_BYTECODE_ENCODER': 'legacy', 'LOCAL_RCC_BYTECODE_CONTAINER': "prehash-zero-trailer", 'LOCAL_RCC_DUMP_BYTECODE': 'true', 'LOCAL_RCC_TRACE_ALL_COMPILES': 'true', 'LOCAL_RCC_PROTECTED_STRING_FORMAT': '0x4'}
        )

        # Inject local_rcc.dll into the now-running Server.exe process,
        # matching what the GUI launcher's Injector.exe block does.
        self.run_injector()

        pipe_thread = threading.Thread(
            target=self.read_server_output,
            daemon=True,
        )
        pipe_thread.start()

        file_change_thread = threading.Thread(
            target=self.maybe_track_file_changes,
            daemon=True,
        )
        file_change_thread.start()

        self.threads.extend([pipe_thread, file_change_thread])

    def maybe_track_file_changes(self) -> None:
        config = self.game_config
        if not config.server_core.place_file.track_file_changes:
            return

        place_uri = config.server_core.place_file.rbxl_uri
        if place_uri.uri_type != wrappers.uri_type.LOCAL:
            return

        file_path = place_uri.value
        last_modified = os.path.getmtime(file_path)

        while self.is_running and not self.is_terminated:
            current_modified = os.path.getmtime(file_path)
            if current_modified == last_modified:
                time.sleep(1)
                continue
            threading.Thread(target=self.restart).start()
            return

    def patch_cacert_pem(self) -> None:
        '''Appends the RFD CA to ssl/cacert.pem so RobloxStudioBeta.exe trusts the local HTTPS web server.'''
        ca_pem = util.ssl_context.get_ca_pem_bytes()
        cacert_path = self.get_versioned_path('ssl', 'cacert.pem')
        if not os.path.isfile(cacert_path):
            return

        with open(cacert_path, 'rb') as f:
            existing = f.read()

        if ca_pem in existing:
            return

        with open(cacert_path, 'ab') as f:
            f.write(b'\n# RFD CA\n')
            f.write(ca_pem)

    @override
    def bootstrap(self) -> None:
        super().bootstrap()

        util.ssl_context.install_ca_to_windows_root(self.logger)
        if util.ssl_context.use_rblxhub_certs():
            util.ssl_context._ensure_rbolock_hosts(self.logger)

        type(self).setup_place_local.cache_clear()
        self.parent_pid = os.getpid()
        self.parent_session_guid = str(uuid.uuid4()).upper()
        self.play_test_session_guid = str(uuid.uuid4()).upper()
        self.patch_cacert_pem()
        self.save_place_file()
        self.save_thumbnail()
        staged_place_path = self.setup_place_local()
        team_test_place_path = self.save_team_test_place_file()

        self.logger.log(
            (
                f"{self.logger.bcolors.BOLD}[UDP %d]{self.logger.bcolors.ENDC}: "
                "initialising Rōblox Studio Server"
            ) % (self.rcc_port,),
            context=logger.log_context.PYTHON_SETUP,
        )

        self.logger.log(
            f"Using staged Studio server place file: {staged_place_path}",
            context=logger.log_context.PYTHON_SETUP,
        )
        self.logger.log(
            f"Using Studio team test place file: {team_test_place_path}",
            context=logger.log_context.PYTHON_SETUP,
        )
        launch_context = self.resolve_launch_context()
        self.logger.log(
            (
                "Resolved Studio server launch context: "
                f"placeId={launch_context.place_id}, "
                f"universeId={launch_context.universe_id}, "
                f"creatorId={launch_context.creator_id}, "
                f"creatorType={launch_context.creator_type}, "
                f"port={self.rcc_port}"
            ),
            context=logger.log_context.PYTHON_SETUP,
        )

        self.make_popen_threads()
import asyncio
import os
import signal
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

import flet as ft

from config_manager import ConfigManager
from mcp_client import MCPClient
from views.home_view import HomeView
from views.settings_view import SettingsView
from views.tool_view import ToolView


# --- サーバー管理クラス ---
class ServerManager:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        # サーバー名をキー、Popenオブジェクトを値とする辞書
        self.server_processes: Dict[str, Optional[subprocess.Popen]] = {}
        # サーバーごとの最終起動試行時刻
        self.last_start_attempt_times: Dict[str, float] = {}
        self.internal_mock_script = "mcp_server_mock.py"  # サーバー実行スクリプト名
        self.min_restart_interval = 5  # 最短再起動間隔(秒)

    def _get_server_command_and_cwd(self, server_key: str) -> Optional[Tuple[List[str], Optional[str]]]:
        """指定されたサーバーキーに対応する起動コマンドとCWDを取得する"""
        config = self.config_manager.get_config()

        if server_key == "internal_mock":
            mock_config = config.get("internal_mock_config", {})
            port = mock_config.get("port", 8001)
            python_executable = sys.executable
            script_path = os.path.abspath(self.internal_mock_script)
            script_dir = os.path.dirname(script_path)
            # uvicorn を直接起動するコマンド
            command = [
                python_executable,
                self.internal_mock_script,
                "--host",
                "localhost",
                "--port",
                str(port),
            ]
            return command, script_dir  # 内蔵モックはスクリプトのあるディレクトリをCWDとする
        elif server_key in config.get("mcpServers", {}):
            server_config = config["mcpServers"][server_key]
            command_name = server_config.get("command")
            args = server_config.get("args", [])
            cwd = server_config.get("cwd")  # None の可能性あり

            if not command_name:
                print(f"エラー: サーバー '{server_key}' に command が設定されていません。")
                return None

            # command が絶対パスか、PATHが通っている必要がある
            full_command = [command_name, *args]

            # cwd が相対パスの場合、config.jsonからの相対パス？ or main.pyから？
            # ここでは絶対パス指定を推奨とし、Noneなら Flet アプリの CWD を使う
            absolute_cwd = None
            if cwd and os.path.isabs(cwd):
                absolute_cwd = cwd
            elif cwd:  # 相対パスの場合 (main.py基準とする)
                absolute_cwd = os.path.abspath(cwd)
                if not os.path.isdir(absolute_cwd):
                    print(f"警告: サーバー '{server_key}' のCWD '{cwd}' が見つかりません。デフォルトCWDを使用します。")
                    absolute_cwd = None  # 見つからない場合はNoneに戻す

            return full_command, absolute_cwd
        else:
            print(f"エラー: 不明なサーバーキー '{server_key}' です。")
            return None

    async def start_server(self, server_key: str) -> bool:
        """指定されたキーのサーバーを起動する"""
        if self.is_running(server_key):
            # print(f"サーバー '{server_key}' は既に起動しています。")
            return True

        # --- 起動条件チェック ---
        config = self.config_manager.get_config()
        server_config = None
        should_be_enabled = False
        if server_key == "internal_mock":
            mock_config = config.get("internal_mock_config", {})
            should_be_enabled = mock_config.get("enabled", False)
            server_config = mock_config  # ダミーとして設定
        # elif server_key in config.get("mcpServers", {}):
        #     server_config = config["mcpServers"][server_key]
        #     should_be_enabled = server_config.get("enabled", False)

        if not server_config:
            print(f"サーバー '{server_key}' の設定が見つかりません。")
            return False
        if not should_be_enabled:
            # print(f"サーバー '{server_key}' は設定で無効になっています。")
            return False  # 起動しない

        # 頻繁な再起動を防ぐ
        current_time = time.time()
        last_attempt = self.last_start_attempt_times.get(server_key, 0)
        if current_time - last_attempt < self.min_restart_interval:
            print(f"サーバー '{server_key}' の再起動間隔が短すぎます。{self.min_restart_interval}秒待機します。")
            return False
        self.last_start_attempt_times[server_key] = current_time

        # --- コマンド取得と実行 ---
        command_info = self._get_server_command_and_cwd(server_key)
        if not command_info:
            return False
        command, cwd = command_info

        print(f"サーバー '{server_key}' を起動します: {' '.join(command)} (CWD: {cwd or os.getcwd()})")
        try:
            # shell=True はセキュリティリスクのため避ける
            # npx などは PATH が通っていれば直接実行できるはず
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            process = subprocess.Popen(
                command,
                cwd=cwd,
                # stdout=subprocess.PIPE, stderr=subprocess.PIPE, # ログをキャプチャする場合
                creationflags=creationflags,
            )
            self.server_processes[server_key] = process
            print(f"サーバー '{server_key}' プロセスを開始しました (PID: {process.pid})。")

            # 起動確認 (簡易)
            await asyncio.sleep(3)  # 起動待機時間 (サーバーによる)
            if process.poll() is not None:
                print(
                    f"エラー: サーバー '{server_key}' プロセスが起動直後に終了しました (コード: {process.returncode})。"
                )
                # ここで stderr を読み取って表示するとデバッグに役立つ
                self.server_processes[server_key] = None
                return False
            return True
        except FileNotFoundError:
            print(f"エラー: コマンド '{command[0]}' が見つかりません。PATHを確認してください。")
            self.server_processes[server_key] = None
            return False
        except Exception as e:
            print(f"サーバー '{server_key}' の起動中にエラーが発生しました: {e}")
            self.server_processes[server_key] = None
            return False

    async def stop_server(self, server_key: str):
        """指定されたキーのサーバープロセスを停止する"""
        process = self.server_processes.get(server_key)
        if process and process.poll() is None:
            print(f"サーバー '{server_key}' プロセス (PID: {process.pid}) を停止します...")
            try:
                # WindowsとUnix系でシグナルの送り方を使い分ける
                if sys.platform == "win32":
                    # Ctrl+Breakシグナルをプロセスグループに送る
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    # プロセスグループにSIGTERMを送る (preexec_fn=os.setsidが必要な場合も)
                    # ここではプロセス自体に送る
                    process.terminate()

                process.wait(timeout=5)
                print(f"サーバー '{server_key}' プロセスが正常に停止しました。")
            except subprocess.TimeoutExpired:
                print(f"サーバー '{server_key}' が時間内に停止しませんでした。強制終了します。")
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], check=False, capture_output=True)
                else:
                    process.kill()
                process.wait()
                print(f"サーバー '{server_key}' プロセスを強制終了しました。")
            except Exception as e:
                print(f"サーバー '{server_key}' 停止中にエラーが発生しました: {e}")
            finally:
                self.server_processes[server_key] = None

    async def stop_all_servers(self):
        """管理している全てのサーバープロセスを停止する"""
        print("管理中の全サーバーを停止します...")
        # 並行して停止処理を行う
        tasks = [self.stop_server(key) for key in list(self.server_processes.keys())]
        await asyncio.gather(*tasks)
        print("全サーバーの停止処理が完了しました。")

    def is_running(self, server_key: str) -> bool:
        """指定されたキーのサーバープロセスが実行中かどうかを確認する"""
        if server_key != "internal_mock":
            # internal_mock以外は常に実行中とみなす
            return True
        process = self.server_processes.get(server_key)
        return process is not None and process.poll() is None

    def get_running_servers(self) -> List[str]:
        """現在実行中のサーバーキーのリストを返す"""
        return [key for key, process in self.server_processes.items() if process and process.poll() is None]

    async def restart_server(self, server_key: str) -> bool:
        """指定されたサーバーを再起動する"""
        print(f"サーバー '{server_key}' を再起動します...")
        await self.stop_server(server_key)
        await asyncio.sleep(1)  # 停止後少し待つ
        return await self.start_server(server_key)

    async def sync_server_states(self):
        """設定に基づいて、不要なサーバーを停止し、必要なサーバーを起動する"""
        print("[Server Sync] サーバー状態を同期中...")
        config = self.config_manager.get_config()
        all_managed_keys = ["internal_mock", *list(config.get("mcpServers", {}).keys())]
        start_tasks = []
        stop_tasks = []

        for key in all_managed_keys:
            should_be_enabled = False
            if key == "internal_mock":
                should_be_enabled = config.get("internal_mock_config", {}).get("enabled", False)
            # elif key in config.get("mcpServers", {}):
            #     should_be_enabled = config["mcpServers"][key].get("enabled", False)

            is_currently_running = self.is_running(key)

            if should_be_enabled and not is_currently_running:
                print(f"[Server Sync] サーバー '{key}' を起動する必要があります。")
                start_tasks.append(self.start_server(key))  # 起動タスクを追加
            elif not should_be_enabled and is_currently_running:
                print(f"[Server Sync] サーバー '{key}' を停止する必要があります。")
                stop_tasks.append(self.stop_server(key))  # 停止タスクを追加

        # まず停止処理を並行実行
        if stop_tasks:
            await asyncio.gather(*stop_tasks)
            await asyncio.sleep(1)  # 停止後少し待つ

        # 次に起動処理を並行実行
        if start_tasks:
            results = await asyncio.gather(*start_tasks)
            print(f"サーバー起動結果: {results}")

        print("[Server Sync] サーバー状態の同期が完了しました。")


# --- Flet アプリケーションメイン関数 ---
async def main(page: ft.Page):
    page.title = "LLMエージェントになってみるアプリ"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.START

    # --- アプリケーションの状態管理 ---
    config_manager = ConfigManager()
    server_manager = ServerManager(config_manager)
    mcp_client = MCPClient()

    # --- サーバー状態表示 ---
    server_status_summary = ft.Text("管理サーバー: 計算中...", size=10, tooltip="管理対象サーバーの実行状態")
    active_server_status = ft.Text("アクティブ: 計算中...", size=10, tooltip="現在接続中のサーバー状態")

    async def update_server_status_ui():
        """UI上のサーバー状態表示を更新"""
        config = config_manager.get_config()
        enabled_servers = []
        if config.get("internal_mock_config", {}).get("enabled"):
            enabled_servers.append("internal_mock")
        # for key, conf in config.get("mcpServers", {}).items():
        #     if conf.get("enabled"):
        #         enabled_servers.append(key)

        num_enabled = len(enabled_servers)
        running_servers = server_manager.get_running_servers()
        num_running = len([s for s in running_servers if s in enabled_servers])  # 有効なサーバーのうち実行中のもの

        server_status_summary.value = f"管理サーバー: {num_running}/{num_enabled} 実行中"

        # アクティブサーバーの状態表示
        active_key = config_manager.get_active_server_key()
        active_status_str = "不明"
        active_tooltip = f"アクティブ: {active_key}"
        if active_key == "external":
            active_status_str = "外部URL"
            # 外部URLの場合は接続テスト等が必要だが、ここでは単純表示
        else:
            is_active_running = server_manager.is_running(active_key)
            active_status_str = "実行中" if is_active_running else "停止中"
            active_tooltip += f" ({active_status_str})"
            # # 有効になっていないのにアクティブな場合も考慮？
            # is_active_enabled = False
            # if active_key == "internal_mock":
            #     is_active_enabled = config.get("internal_mock_config", {}).get("enabled", False)
            # elif active_key in config.get("mcpServers", {}):
            #     is_active_enabled = config["mcpServers"][active_key].get("enabled", False)
            # if not is_active_enabled and active_key != "external":
            #     active_status_str += " (無効)"
            #     active_tooltip += " (ただし設定で無効)"

        active_server_status.value = f"アクティブ: {active_key} ({active_status_str})"
        active_server_status.tooltip = active_tooltip

        try:
            if page.controls or page.views:  # ページが描画されているか確認
                page.update()
        except Exception as e:
            print(f"サーバー状態UIの更新中にエラー: {e}")  # UI更新失敗は無視して継続

    # --- サーバー自動起動・状態監視 ---
    async def server_check_loop():
        """定期的にサーバーの状態を設定と同期し、UIを更新する"""
        while True:
            print("[Server Check] 実行中: サーバー状態の同期チェック...")
            try:
                # 設定に基づいてサーバーを起動/停止
                await server_manager.sync_server_states()
                # UI表示を更新
                await update_server_status_ui()
            except Exception as e:
                print(f"[Server Check] サーバーチェックループでエラー: {e}")
                # エラーが発生してもループは継続する
            await asyncio.sleep(30)  # 30秒ごとにチェック (同期処理があるので少し長め)

    # --- アプリ終了時の処理 ---
    async def on_disconnect(e):
        print("アプリケーションが切断されました。管理中の全サーバーを停止します。")
        if mcp_client.session is not None:
            try:
                await mcp_client.aclose()
            except Exception:
                print("MCPClientのクローズ中にエラーが発生しました。")
        await server_manager.stop_all_servers()  # 全サーバー停止に変更

    page.on_disconnect = on_disconnect  # Flet 0.21.0 以降

    async def update_mcp_client(route: str):
        nonlocal mcp_client
        active_server_type = config_manager.get_active_server_type()
        if active_server_type == "sse":
            active_mcp_url = config_manager.get_active_mcp_url()
            assert active_mcp_url is not None, "MCP URL must be set for SSE server type"
            print(f"MCPClientの接続先を更新: {mcp_client.server_command_or_server_url} -> {active_mcp_url}")
            print(f"MCPClient.sessionの状態: {mcp_client.session}")
            if mcp_client.session is None:
                await mcp_client.connect_to_server(
                    server_type=active_server_type, server_command_or_server_url=active_mcp_url
                )
                print("MCPClient接続完了")
            elif route == "/settings":
                pass  # 設定画面への遷移では接続先を変更しない
            else:
                try:
                    await mcp_client.aclose()
                except Exception:
                    print("MCPClientのクローズ中にエラーが発生しました。")
                await mcp_client.connect_to_server(
                    server_type=active_server_type, server_command_or_server_url=active_mcp_url
                )
                print("MCPClient接続完了")
        elif active_server_type == "stdio":
            active_server_key = config_manager.get_active_server_key()
            active_server_config = config_manager.get_server_config(active_server_key)
            assert active_server_key is not None, "MCP Server Key must be set for STDIO server type"
            print(f"MCPClientの接続先を更新: {mcp_client.stdio_server_key} -> {active_server_key}")
            print(f"MCPClient.sessionの状態: {mcp_client.session}")
            if mcp_client.session is None:
                if active_server_config:
                    server_command = active_server_config.get("command", None)
                    stdio_args = active_server_config.get("args", [])
                    stdio_env = active_server_config.get("env", {})
                    stdio_cwd = active_server_config.get("cwd", None)
                    if server_command:
                        await mcp_client.connect_to_server(
                            server_type=active_server_type,
                            server_command_or_server_url=server_command,
                            stdio_args=stdio_args,
                            stdio_env=stdio_env,
                            stdio_cwd=stdio_cwd,
                            stdio_server_key=active_server_key,
                        )
                        print("MCPClient接続完了")
                else:
                    print(f"エラー: サーバー '{active_server_key}' の設定が見つかりません。")
            elif route == "/settings":
                pass  # 設定画面への遷移では接続先を変更しない
            else:
                try:
                    await mcp_client.aclose()
                except Exception:
                    print("MCPClientのクローズ中にエラーが発生しました。")
                if active_server_config:
                    server_command = active_server_config.get("command", None)
                    stdio_args = active_server_config.get("args", [])
                    stdio_env = active_server_config.get("env", {})
                    stdio_cwd = active_server_config.get("cwd", None)
                    if server_command:
                        await mcp_client.connect_to_server(
                            server_type=active_server_type,
                            server_command_or_server_url=server_command,
                            stdio_args=stdio_args,
                            stdio_env=stdio_env,
                            stdio_cwd=stdio_cwd,
                            stdio_server_key=active_server_key,
                        )
                        print("MCPClient接続完了")
                else:
                    print(f"エラー: サーバー '{active_server_key}' の設定が見つかりません。")
        else:
            print(f"無効なサーバータイプ: {active_server_type}")

    # --- ルーティング処理 ---
    async def route_change(route: ft.RouteChangeEvent):
        print(f"Route change to: {route.route}")
        # ルート変更時にクライアントを最新のアクティブ設定に更新
        active_server_type = config_manager.get_active_server_type()
        if active_server_type and (mcp_client.server_type != active_server_type):
            await update_mcp_client(route.route)
        else:
            if active_server_type == "sse":
                active_mcp_url = config_manager.get_active_mcp_url()
                if active_mcp_url and mcp_client.server_command_or_server_url != active_mcp_url:
                    # URLが変更された場合のみ接続先を更新
                    await update_mcp_client(route.route)
            elif active_server_type == "stdio":
                active_server_key = config_manager.get_active_server_key()
                if active_server_key and mcp_client.stdio_server_key != active_server_key:
                    # サーバーキーが変更された場合のみ接続先を更新
                    await update_mcp_client(route.route)
            else:
                print(f"無効なサーバータイプ: {active_server_type}")

        page.views.clear()

        # --- ステータスバー表示用のコンテナ ---
        status_bar_content = ft.Row(
            [active_server_status, ft.VerticalDivider(width=10), server_status_summary],
            spacing=5,
            alignment=ft.MainAxisAlignment.END,
        )

        # --- 各ルートに対応するViewを生成 ---
        current_view = None
        if route.route == "/settings":
            settings_view = SettingsView(page, config_manager, mcp_client, server_manager)
            page.views.append(settings_view)
            current_view = settings_view
        elif route.route.startswith("/tool/"):
            tool_name = route.route.split("/")[-1]
            # ToolViewでは page オブジェクト経由でデータを渡すように修正済み
            tool_view = ToolView(page, mcp_client, tool_name)
            page.views.append(tool_view)
            current_view = tool_view
        else:  # デフォルトはホーム画面 ("/")
            home_view = HomeView(page, mcp_client)
            page.views.append(home_view)
            current_view = home_view
            # HomeViewが表示される前にツールリストを読み込む
            if mcp_client.session:  # URLが設定されていれば読み込み試行
                await home_view.initialize()
            else:
                # URLがない場合（外部URLが空でアクティブなど）、ホーム画面にメッセージ表示が必要
                home_view.status_text.value = (
                    "接続先のMCPサーバーが設定されていません。\n設定画面でアクティブなサーバーを選択してください。"
                )
                home_view.status_text.color = ft.Colors.AMBER
                home_view.status_text.visible = True

        # --- AppBarにステータスバーを追加 ---
        if current_view and current_view.appbar and isinstance(current_view.appbar, ft.AppBar):
            if current_view.appbar.actions is None:
                current_view.appbar.actions = []
            # 重複追加を防ぐ
            if not any(
                isinstance(action, ft.Container) and action.data == "status_bar"
                for action in current_view.appbar.actions
            ):
                status_container = ft.Container(
                    content=status_bar_content,
                    padding=ft.padding.only(right=10),
                    tooltip=f"{active_server_status.tooltip} | {server_status_summary.tooltip}",
                    data="status_bar",
                )
                current_view.appbar.actions.append(status_container)

        # --- 有効なURLがない場合のリダイレクト ---
        # (外部URLがアクティブだが空、またはアクティブキーが無効な場合など)
        # mcp_client.base_url が None かどうかで判定
        if not mcp_client.session and route.route != "/settings":
            print(
                "有効なMCP URLが見つからないため /settings へリダイレクトします"
                + f" (現在のキー: {config_manager.get_active_server_key()})。"
            )
            # SettingsViewを表示するように切り替え
            page.views.clear()
            settings_view = SettingsView(page, config_manager, mcp_client, server_manager)
            page.views.append(settings_view)
            # ステータスバーも追加
            if settings_view.appbar and isinstance(settings_view.appbar, ft.AppBar):
                if settings_view.appbar.actions is None:
                    settings_view.appbar.actions = []
                status_container = ft.Container(
                    content=status_bar_content,
                    padding=ft.padding.only(right=10),
                    tooltip=f"{active_server_status.tooltip} | {server_status_summary.tooltip}",
                    data="status_bar",
                )
                settings_view.appbar.actions.append(status_container)

        await update_server_status_ui()  # UIの状態を最新にする
        page.update()

    # --- View Pop処理 ---
    async def view_pop(view: ft.ViewPopEvent):
        page.views.pop()
        top_view_route = page.views[-1].route if page.views else "/"

        # Pop後のViewにもステータスバーを（念のため）追加/更新
        if page.views:
            current_view = page.views[-1]
            if current_view.appbar and isinstance(current_view.appbar, ft.AppBar):
                status_bar_content = ft.Row(
                    [active_server_status, ft.VerticalDivider(width=10), server_status_summary],
                    spacing=5,
                    alignment=ft.MainAxisAlignment.END,
                )
                status_container = ft.Container(
                    content=status_bar_content,
                    padding=ft.padding.only(right=10),
                    tooltip=f"{active_server_status.tooltip} | {server_status_summary.tooltip}",
                    data="status_bar",
                )
                # 既存のアクションからstatus_barを削除して新しいものを追加
                if current_view.appbar.actions:
                    current_view.appbar.actions = [
                        a
                        for a in current_view.appbar.actions
                        if not (isinstance(a, ft.Container) and a.data == "status_bar")
                    ]
                else:
                    current_view.appbar.actions = []
                current_view.appbar.actions.append(status_container)

        page.go(top_view_route)  # type: ignore # go を呼ぶと route_change がトリガーされる

    # --- イベントハンドラ設定 ---
    page.on_route_change = route_change
    page.on_view_pop = view_pop

    # --- アプリケーション開始時の処理 ---
    print("アプリケーション起動、初期設定とサーバーチェックを開始します...")

    # サーバー状態監視ループをバックグラウンドで開始
    _ = asyncio.create_task(server_check_loop())  # noqa: RUF006

    # ページが表示される前に一度状態を更新しておく
    await update_server_status_ui()

    # 初期ルートへの遷移
    page.go("/")


# --- アプリケーションの実行 ---
if __name__ == "__main__":
    # uvicorn サーバーが Windows で Ctrl+C を正しくハンドルするために必要
    # if sys.platform == "win32":
    #     asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    ft.app(target=main)
    # デバッグ用にポート指定など
    # ft.app(target=main, view=ft.AppView.WEB_BROWSER)

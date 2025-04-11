import asyncio

# ServerManager の型ヒント用にインポート（循環参照に注意）
# from __main__ import ServerManager # これは避けるべき
from typing import TYPE_CHECKING

import flet as ft

from config_manager import ConfigManager
from mcp_client import MCPClient

if TYPE_CHECKING:
    from main import ServerManager  # 実行時ではなく型チェック時にのみインポート


class SettingsView(ft.View):
    """MCPサーバー設定画面"""

    page: ft.Page

    def __init__(
        self, page: ft.Page, config_manager: ConfigManager, mcp_client: MCPClient, server_manager: "ServerManager"
    ):
        super().__init__(
            route="/settings",
            padding=ft.padding.all(20),
            scroll=ft.ScrollMode.ADAPTIVE,
        )
        self.page = page
        self.config_manager = config_manager
        self.mcp_client = mcp_client
        self.server_manager = server_manager  # ServerManagerインスタンスを受け取る

        # --- 現在の設定読み込み ---
        current_config = self.config_manager.get_config()
        self.active_server_key = current_config.get("active_server_key", "internal_mock")
        self.external_url = current_config.get("external_mcp_url", "")

        # --- UI コントロール ---
        # アクティブサーバー選択ドロップダウン
        self.server_selection_dd = ft.Dropdown(
            label="アクティブなMCPサーバー",
            options=self._build_server_options(),
            value=self.active_server_key,
            on_change=self.on_server_selection_change,
            tooltip="アプリが接続するMCPサーバーを選択します",
        )

        # 外部URL入力フィールド
        self.mcp_url_field = ft.TextField(
            label="外部 MCP Server URL",
            value=self.external_url,
            hint_text="例: http://some-mcp-server.com",
            visible=(self.active_server_key == "external"),  # 初期表示設定
            on_submit=self.save_settings,
        )
        self.test_button = ft.ElevatedButton(
            "接続テスト",
            on_click=self.test_external_connection,
            visible=(self.active_server_key == "external"),  # 初期表示設定
            disabled=not self.external_url,  # URLが空なら無効
        )

        # 各サーバーの情報表示エリア (アクティブサーバーに応じて表示)
        self.server_info_area = ft.Column(
            controls=self._build_server_info_controls(self.active_server_key),
            visible=(self.active_server_key != "external"),  # 外部以外の場合に表示
        )

        # ステータス/エラーメッセージ用
        self.status_text = ft.Text(value="", color=ft.Colors.ERROR, max_lines=3)
        self.save_button = ft.ElevatedButton("保存して戻る", on_click=self.save_settings)

        # URLフィールド変更時にテストボタンの状態更新
        self.mcp_url_field.on_change = lambda e: self.update_test_button_state()

        # --- レイアウト ---
        self.appbar = ft.AppBar(title=ft.Text("MCP設定"), bgcolor=ft.Colors.SURFACE)
        self.controls = [
            ft.Text("接続先サーバー設定", size=16, weight=ft.FontWeight.BOLD),
            self.server_selection_dd,
            self.mcp_url_field,  # 外部URLフィールド
            ft.Row(  # テストボタン行 (外部URL時のみ表示)
                [self.test_button], alignment=ft.MainAxisAlignment.END, visible=(self.active_server_key == "external")
            ),
            self.server_info_area,  # 選択されたサーバー情報
            ft.Divider(height=20),
            self.status_text,
            ft.Row([self.save_button], alignment=ft.MainAxisAlignment.END),
            ft.Divider(height=20),
            ft.Text("管理対象サーバー", size=16, weight=ft.FontWeight.BOLD),
            ft.Column(self._build_managed_server_list()),  # 管理対象サーバーリスト表示
        ]

    def _build_server_options(self) -> list:
        """アクティブサーバー選択Dropdownの選択肢を生成"""
        options = [
            ft.dropdown.Option(key="internal_mock", text="内蔵モックサーバー"),
            ft.dropdown.Option(key="external", text="外部URLを指定"),
        ]
        user_servers = self.config_manager.get_mcp_servers_config()
        for key in user_servers.keys():
            # キー名をそのまま表示（必要なら設定ファイルに表示名を追加しても良い）
            options.append(ft.dropdown.Option(key=key, text=f"管理サーバー: {key}"))
        return options

    def _build_server_info_controls(self, server_key: str) -> list:
        """選択されたサーバーに応じた情報コントロールを生成"""
        controls = []
        url = ""
        config = None

        if server_key == "internal_mock":
            config = self.config_manager.get_internal_mock_config()
            port = config.get("port", 8001)
            url = f"http://127.0.0.1:{port}"
            controls.append(ft.Text("内蔵モックサーバーが使用されます。", italic=True))
        elif server_key == "external":
            # 外部URLの場合はこのエリアは非表示になるので、ここでは何もしない
            pass
        else:  # ユーザー定義サーバー
            config = self.config_manager.get_server_config(server_key)
            if config:
                command = config.get("command", "N/A")
                args = config.get("args", [])
                controls.append(ft.Text(f"管理サーバー '{server_key}' が使用されます。", italic=True))
                controls.append(ft.Text(f"コマンド: {command} {' '.join(args)}", size=11))
            else:
                controls.append(
                    ft.Text(f"エラー: サーバー '{server_key}' の設定が見つかりません。", color=ft.Colors.ERROR)
                )

        if url:
            controls.append(ft.Text(f"接続URL: {url}", weight=ft.FontWeight.BOLD))

        # サーバーの実行状態を表示 (ServerManagerから取得)
        if config and server_key != "external":
            is_running = self.server_manager.is_running(server_key)
            if server_key == "internal_mock":
                status_text_str = "実行中" if is_running else "停止中"
                status_icon = ft.Icon(
                    name=ft.icons.CIRCLE if is_running else ft.icons.ERROR_OUTLINE,
                    color=ft.Colors.GREEN_ACCENT_700 if is_running else ft.Colors.RED_ACCENT_700,
                    tooltip=status_text_str,
                    size=16,
                )
            else:
                status_text_str = "認識中" if is_running else "不具合あり"
                status_icon = ft.Icon(
                    name=ft.icons.CIRCLE if is_running else ft.icons.ERROR_OUTLINE,
                    color=ft.Colors.YELLOW_ACCENT_700 if is_running else ft.Colors.RED_ACCENT_700,
                    tooltip=status_text_str,
                    size=16,
                )
            status_text = ft.Text(status_text_str, size=12)
            controls.append(ft.Row([status_icon, status_text], spacing=5))

        return controls

    def _build_managed_server_list(self) -> list:
        """管理対象サーバーの一覧と有効/無効スイッチを表示"""
        controls = []
        all_servers = self.config_manager.get_all_managed_servers()

        for key, config in all_servers:
            is_enabled = config.get("enabled", False) if isinstance(config, dict) else False
            is_running = self.server_manager.is_running(key)

            if key == "internal_mock":
                status_text_str = "実行中" if is_running else "停止中"
                status_icon = ft.Icon(
                    name=ft.icons.CIRCLE if is_running else ft.icons.ERROR_OUTLINE,
                    color=ft.Colors.GREEN_ACCENT_700 if is_running else ft.Colors.RED_ACCENT_700,
                    tooltip=status_text_str,
                    size=16,
                )
            else:
                status_text_str = "認識中" if is_running else "不具合あり"
                status_icon = ft.Icon(
                    name=ft.icons.CIRCLE if is_running else ft.icons.ERROR_OUTLINE,
                    color=ft.Colors.YELLOW_ACCENT_700 if is_running else ft.Colors.RED_ACCENT_700,
                    tooltip=status_text_str,
                    size=16,
                )

            # サーバー名と状態アイコン
            server_label = ft.Row(
                [
                    status_icon,
                    ft.Text(key, weight=ft.FontWeight.BOLD),
                ],
                spacing=5,
            )

            # 有効/無効スイッチ
            enable_switch = ft.Switch(
                value=is_enabled,
                data=key,  # スイッチにサーバーキーを紐付ける
                on_change=self.toggle_server_enabled,
                tooltip="アプリ起動時にこのサーバーを自動起動する",
            )

            # 説明 (コマンドなど)
            description = ""
            if key == "internal_mock":
                description = f"内蔵Pythonモック (ポート: {config.get('port', 8001)})"
            elif "command" in config:
                description = f"Cmd: {config['command']} {config.get('args', [])[:2]}..."  # 引数を少し表示
                if "port" in config:
                    description += f" (ポート: {config['port']})"

            if key == "internal_mock":
                controls.append(
                    ft.Row(
                        [
                            ft.Column([server_label, ft.Text(description, size=11, italic=True)], expand=True),
                            ft.Row([ft.Text("自動起動:", size=12), enable_switch], alignment=ft.MainAxisAlignment.END),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                )
            else:
                controls.append(
                    ft.Row(
                        [
                            ft.Column([server_label, ft.Text(description, size=11, italic=True)], expand=True),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                )
            controls.append(ft.Divider(height=5))

        return controls

    async def on_server_selection_change(self, e):
        """アクティブサーバーDropdownの選択が変更されたときの処理"""
        selected_key = self.server_selection_dd.value
        self.active_server_key = selected_key  # 内部状態を更新

        is_external = selected_key == "external"
        self.mcp_url_field.visible = is_external
        self.test_button.visible = is_external
        self.controls[3].visible = is_external  # テストボタンのRow
        self.server_info_area.visible = not is_external

        if not is_external and selected_key:
            # サーバー情報エリアの内容を更新
            self.server_info_area.controls = self._build_server_info_controls(selected_key)
        else:
            self.update_test_button_state()  # 外部URLの場合、テストボタン状態更新

        self.status_text.value = ""  # メッセージクリア
        self.page.update()

    async def toggle_server_enabled(self, e: ft.ControlEvent):
        """管理対象サーバーの有効/無効スイッチが変更されたときの処理"""
        server_key = e.control.data
        new_enabled_state = e.control.value
        print(f"サーバー '{server_key}' の有効状態を {new_enabled_state} に変更します。")

        # 設定ファイルに保存
        config = self.config_manager.get_config()
        save_needed = False
        if server_key == "internal_mock":
            if config["internal_mock_config"]["enabled"] != new_enabled_state:
                config["internal_mock_config"]["enabled"] = new_enabled_state
                save_needed = True
        elif server_key in config["mcpServers"]:
            if config["mcpServers"][server_key]["enabled"] != new_enabled_state:
                config["mcpServers"][server_key]["enabled"] = new_enabled_state
                save_needed = True

        if save_needed:
            if self.config_manager.save_config(config, merge_with_current=False):
                self.status_text.value = f"サーバー '{server_key}' の自動起動設定を更新しました。"
                self.status_text.color = ft.Colors.GREEN
                # ServerManagerに状態同期を促す (ここでは保存のみ、同期はメインループが行う)
                # await self.server_manager.sync_server_states() # ここで同期すると時間がかかるかも
            else:
                self.status_text.value = f"サーバー '{server_key}' の設定保存に失敗しました。"
                self.status_text.color = ft.Colors.ERROR
                # スイッチの状態を元に戻す？
                e.control.value = not new_enabled_state
        else:
            self.status_text.value = ""  # 変更なし

        # UIの管理対象サーバーリストを再描画して状態アイコンを更新 (少し遅延があるかも)
        # TODO: リスト全体を再描画するのではなく、該当行だけ更新したい
        self.controls[-1] = ft.Column(self._build_managed_server_list())  # リスト部分を再構築して差し替え

        self.page.update()

    def update_test_button_state(self):
        """外部URL入力時にテストボタンの有効/無効を更新"""
        self.test_button.disabled = not str(self.mcp_url_field.value).strip()
        self.page.update()  # 同期的に更新

    async def test_external_connection(self, e):
        """外部URLで接続テストを行う"""
        url = str(self.mcp_url_field.value).strip()
        if not url:
            self.status_text.value = "外部URLが入力されていません。"
            self.status_text.color = ft.Colors.ERROR
            self.page.update()
            return

        if not (url.startswith("http://") or url.startswith("https://")):
            self.status_text.value = "URLは http:// または https:// で始めてください。"
            self.status_text.color = ft.Colors.ERROR
            self.page.update()
            return

        self.status_text.value = "接続テスト中..."
        self.status_text.color = ft.Colors.BLUE
        self.test_button.disabled = True
        self.save_button.disabled = True
        self.page.update()

        temp_client = MCPClient()
        try:
            try:
                await temp_client.connect_to_server(server_type="sse", server_command_or_server_url=url)
                tools = await temp_client.get_tools()
                self.status_text.value = f"接続成功！ {len(tools)}個のツールが見つかりました。"
                self.status_text.color = ft.Colors.GREEN
            finally:
                await temp_client.aclose()
        except (ValueError, ConnectionError, TimeoutError, RuntimeError) as ex:
            self.status_text.value = f"接続失敗: {ex}"
            self.status_text.color = ft.Colors.ERROR
        except Exception as ex:
            self.status_text.value = f"予期しないエラー: {ex}"
            self.status_text.color = ft.Colors.ERROR
        finally:
            self.update_test_button_state()  # ボタン状態を更新
            self.save_button.disabled = False
            self.page.update()

    async def save_settings(self, e):
        """設定を保存し、前の画面（ホーム）に戻る"""
        new_active_key = self.server_selection_dd.value
        new_external_url = str(self.mcp_url_field.value).strip() if new_active_key == "external" else None

        # バリデーション
        if new_active_key == "external" and not new_external_url:
            self.status_text.value = "外部URLを選択した場合は、URLを入力してください。"
            self.status_text.color = ft.Colors.ERROR
            self.page.update()
            return
        if (
            new_active_key == "external"
            and new_external_url
            and not (new_external_url.startswith("http://") or new_external_url.startswith("https://"))
        ):
            self.status_text.value = "外部URLは http:// または https:// で始めてください。"
            self.status_text.color = ft.Colors.ERROR
            self.page.update()
            return

        # --- 設定を保存 ---
        config_changed = False
        if new_active_key and (self.config_manager.get_active_server_key() != new_active_key):
            self.config_manager.set_active_server_key(new_active_key)
            config_changed = True

        if new_active_key == "external" and self.config_manager.get_external_mcp_url() != new_external_url:
            self.config_manager.set_external_mcp_url(new_external_url)
            config_changed = True

        if config_changed:
            self.status_text.value = "設定を保存しました。"
            self.status_text.color = ft.Colors.GREEN

            self.page.update()
            await asyncio.sleep(1.5)
            self.page.go("/")  # ホーム画面に戻る
        else:
            # 変更がない場合はそのまま戻る
            self.page.go("/")

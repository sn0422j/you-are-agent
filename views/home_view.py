import flet as ft
from mcp import Tool

from mcp_client import MCPClient


class HomeView(ft.View):
    """ツールリスト表示画面"""

    page: ft.Page

    def __init__(self, page: ft.Page, mcp_client: MCPClient):
        super().__init__(
            route="/",
            padding=0,  # AppBarとListViewの間隔はListView側で調整
        )
        self.page = page
        self.mcp_client = mcp_client

        self.loading_indicator = ft.ProgressRing(visible=False)
        self.status_text = ft.Text(visible=False)  # エラーや情報表示用
        self.tool_list_view = ft.ListView(expand=True, spacing=5, padding=10)

        self.appbar = ft.AppBar(
            title=ft.Text("利用可能なMCPツール"),
            bgcolor=ft.Colors.SURFACE,
            actions=[
                ft.IconButton(ft.Icons.REFRESH, tooltip="リスト更新", on_click=self.load_tools),
                ft.IconButton(ft.Icons.SETTINGS, tooltip="設定", on_click=lambda _: self.page.go("/settings")),
            ],
        )
        self.controls = [
            self.loading_indicator,
            self.status_text,
            self.tool_list_view,
        ]

    async def initialize(self):
        """画面表示時にツールリストを読み込む"""
        await self.load_tools(None)  # 初回読み込み

    async def load_tools(self, e):
        """MCPサーバーからツールリストを取得して表示する"""
        self.tool_list_view.controls.clear()
        self.status_text.visible = False
        self.loading_indicator.visible = True
        self.page.update()

        if not self.mcp_client.session:
            self.status_text.value = "MCPサーバーに接続されていません。\n設定画面でMCPサーバーを設定してください。"
            self.status_text.visible = True
            self.loading_indicator.visible = False
            self.page.update()
            return

        try:
            tools = await self.mcp_client.get_tools()
            if not tools:
                self.status_text.value = "利用可能なツールが見つかりませんでした。"
                self.status_text.visible = True
            else:
                self.display_tools(tools)

        except (ValueError, ConnectionError, TimeoutError, RuntimeError) as ex:
            self.status_text.value = f"ツールリストの取得に失敗しました:\n{ex}"
            self.status_text.color = ft.Colors.ERROR
            self.status_text.visible = True
        except Exception as ex:
            self.status_text.value = f"予期しないエラーが発生しました:\n{ex}"
            self.status_text.color = ft.Colors.ERROR
            self.status_text.visible = True
        finally:
            self.loading_indicator.visible = False
            self.page.update()

    def display_tools(self, tools: list[Tool]):
        """取得したツールリストをListViewに表示する"""
        self.tool_list_view.controls.clear()
        for tool in tools:
            tool_name = tool.name
            tool_desc = tool.description or "説明がありません。"
            # input_schema を ToolView に渡すために保持
            # (toolオブジェクト全体を渡しても良いが、必要な情報だけにする方がメモリ効率が良い場合も)
            tool_info = tool  # toolオブジェクト全体を渡すことにする

            list_tile = ft.ListTile(
                title=ft.Text(tool_name),
                subtitle=ft.Text(tool_desc, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                trailing=ft.Icon(ft.icons.CHEVRON_RIGHT),
                data=tool_info,  # Fletコントロールにデータを付与できる
                on_click=self.go_to_tool_view,
                tooltip=f"{tool_name}: {tool_desc}",  # ホバーで詳細表示
            )
            self.tool_list_view.controls.append(list_tile)

    async def go_to_tool_view(self, e: ft.ControlEvent):
        """ListTileがクリックされたときにツール実行画面に遷移する"""
        selected_tool_info = e.control.data  # ListTileに付与したデータを取得
        assert isinstance(selected_tool_info, Tool), "選択されたツール情報が不正です。"
        tool_name = selected_tool_info.name
        if tool_name:
            # --- page オブジェクトに一時属性として格納 ---
            try:
                # page オブジェクトにカスタム属性を追加して情報を保持
                self.page.selected_tool_info_temp = selected_tool_info  # type: ignore
                print(f"ツール情報 ({tool_name}) を page オブジェクトの一時属性に格納しました。")

                # 画面遷移
                self.page.go(f"/tool/{tool_name}")
            except Exception as ex:
                print(f"ページ属性の設定または画面遷移中にエラー: {ex}")
        else:
            print("エラー：クリックされたツールに名前がありません。")

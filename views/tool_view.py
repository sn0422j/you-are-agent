from typing import TYPE_CHECKING, Any, Dict, Optional

import flet as ft

from mcp_client import MCPClient

if TYPE_CHECKING:
    from mcp import Tool


class ToolView(ft.View):
    """ツール実行画面"""

    page: ft.Page

    def __init__(self, page: ft.Page, mcp_client: MCPClient, tool_name: str):
        super().__init__(route=f"/tool/{tool_name}", scroll=ft.ScrollMode.ADAPTIVE, padding=ft.padding.all(20))
        self.page = page
        self.mcp_client = mcp_client
        self.tool_name = tool_name
        # HomeViewから渡されたツール情報を取得
        # --- page オブジェクトの一時属性から取得 ---
        self.tool_info: Optional[Tool] = None
        try:
            if hasattr(self.page, "selected_tool_info_temp"):
                self.tool_info = self.page.selected_tool_info_temp  # type: ignore
                print(f"page オブジェクトからツール '{tool_name}' の情報を取得しました。")
                # 取得したら一時属性を削除する
                delattr(self.page, "selected_tool_info_temp")
            else:
                print(f"警告: page オブジェクトに '{tool_name}' の一時情報が見つかりませんでした。")
        except Exception as ex:
            print(f"ページ属性の取得または削除中にエラー: {ex}")

        self.input_controls: Dict[str, ft.Control] = {}  # 入力コントロールを保持 {input_name: control}
        self.output_area = ft.TextField(
            label="出力",
            read_only=True,
            multiline=True,
            min_lines=5,
            max_lines=15,
            value="結果がここに表示されます。",
            expand=True,  # 縦にスペースを広げる
            text_size=16,  # 結果が見やすいように少し小さく
            border_color=ft.Colors.OUTLINE,
        )
        self.run_button = ft.ElevatedButton("Run", on_click=self.run_tool)
        self.status_text = ft.Text(value="", color=ft.Colors.ERROR)
        self.progress_ring = ft.ProgressRing(visible=False, width=16, height=16)  # 小さめのリング

        # AppBar
        self.appbar = ft.AppBar(
            title=ft.Text(f"ツール: {self.tool_name}"),
            bgcolor=ft.Colors.SURFACE,
            leading=ft.IconButton(ft.Icons.ARROW_BACK, tooltip="戻る", on_click=lambda _: self.page.go("/")),
        )

        # メインコンテンツ
        self.controls = self.build_layout()

    def build_layout(self) -> list:
        """画面レイアウトを構築する"""
        if not self.tool_info:
            return [ft.Text(f"エラー: ツール '{self.tool_name}' の情報が見つかりません。", color=ft.Colors.ERROR)]

        tool_description = self.tool_info.description or "説明がありません。"
        input_schema = self.tool_info.inputSchema or {}

        input_form_controls = self.create_input_form(input_schema)

        return [
            ft.Text(tool_description, weight=ft.FontWeight.BOLD, size=16),
            ft.Divider(height=10),
            ft.Text("入力:", weight=ft.FontWeight.BOLD),
            ft.Column(input_form_controls, spacing=15)
            if input_form_controls
            else ft.Text("このツールは入力を必要としません。"),
            ft.Divider(height=10),
            ft.Row(
                [
                    self.run_button,
                    self.progress_ring,
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            self.status_text,
            ft.Divider(height=10),
            # ft.Text("出力:", weight=ft.FontWeight.BOLD), # TextFieldにLabelがあるので不要かも
            ft.Container(  # 出力エリアを少し目立たせる
                content=self.output_area,
                expand=True,  # 残りのスペースを埋める
            ),
        ]

    def create_input_form(self, schema: Dict[str, Any]) -> list:
        """
        JSON Schema (input_schema) に基づいて Flet 入力コントロールを生成する。
        対応タイプ: string, boolean, integer, number, enum(string)
        """
        controls = []
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        if not properties:
            return []  # 入力がない場合は空リストを返す

        for name, prop_schema in properties.items():
            label = prop_schema.get("title", name)
            description = prop_schema.get("description")
            field_type = prop_schema.get("type", "string")
            default_value = prop_schema.get("default")
            is_required = name in required
            display_label = f"{label}{' *' if is_required else ''}"

            control: Optional[ft.Control] = None

            # --- 型に応じたコントロール生成 ---
            if "enum" in prop_schema and field_type == "string":  # 文字列のenumはDropdown
                options = [ft.dropdown.Option(key=str(enum_val)) for enum_val in prop_schema["enum"]]
                control = ft.Dropdown(
                    label=display_label,
                    hint_text=description or "選択してください",
                    options=options,
                    value=str(default_value) if default_value is not None else None,
                    tooltip=description,
                )
            elif field_type == "string":
                # 複数行かどうかの判定（例: format が textarea など）
                is_multiline = prop_schema.get("format") == "textarea"  # MCP仕様による
                control = ft.TextField(
                    label=display_label,
                    hint_text=description,
                    value=str(default_value) if default_value is not None else "",
                    multiline=is_multiline,
                    min_lines=3 if is_multiline else 1,
                    max_lines=5 if is_multiline else 1,
                    tooltip=description,
                )
            elif field_type == "boolean":
                control = ft.Checkbox(
                    label=display_label,
                    value=bool(default_value) if default_value is not None else False,
                    tooltip=description,
                )
            elif field_type == "integer":
                control = ft.TextField(
                    label=display_label,
                    hint_text=description,
                    value=str(default_value) if default_value is not None else "",
                    keyboard_type=ft.KeyboardType.NUMBER,
                    input_filter=ft.InputFilter(r"[0-9\-]"),  # 整数のみ許可 (マイナスも)
                    tooltip=description,
                )
            elif field_type == "number":
                control = ft.TextField(
                    label=display_label,
                    hint_text=description,
                    value=str(default_value) if default_value is not None else "",
                    keyboard_type=ft.KeyboardType.NUMBER,
                    # 小数点とマイナスを許可 (より厳密な正規表現も可能)
                    input_filter=ft.InputFilter(r"[0-9\.\-]"),
                    tooltip=description,
                )
            # --- 他の型 (array, object など) のサポートを追加する場合はここに記述 ---
            else:
                controls.append(ft.Text(f"未対応の入力タイプ '{field_type}' for '{name}'", color=ft.Colors.ORANGE))
                continue  # このフィールドは追加しない

            if control:
                self.input_controls[name] = control
                controls.append(control)

        return controls

    def _validate_inputs(self) -> Optional[Dict[str, Any]]:
        """入力値を取得し、バリデーションを行う。エラーがあればNone、なければ入力辞書を返す。"""
        inputs = {}
        errors = []
        input_schema = self.tool_info.inputSchema if (self.tool_info) and (self.tool_info.inputSchema) else {}
        properties = input_schema.get("properties", {})
        required_fields = input_schema.get("required", [])

        for name, control in self.input_controls.items():
            prop_schema = properties.get(name, {})
            field_type = prop_schema.get("type", "string")
            is_required = name in required_fields
            value = None
            error_msg = None

            # --- 値の取得と型変換 ---
            try:
                if isinstance(control, ft.TextField):
                    raw_value = control.value.strip() if control.value else ""
                    if not raw_value and is_required:
                        error_msg = "必須項目です。"
                    elif raw_value:  # 値がある場合のみ型変換
                        if field_type == "integer":
                            value = int(raw_value)
                        elif field_type == "number":
                            value = float(raw_value)
                        else:  # string
                            value = raw_value
                    elif not raw_value and not is_required and control.value is not None:  # 空文字を許容する場合
                        value = ""

                elif isinstance(control, ft.Checkbox):
                    value = control.value  # bool

                elif isinstance(control, ft.Dropdown):
                    value = control.value  # 文字列 (キー) or None
                    if value is None and is_required:
                        error_msg = "選択してください。"
                    # Dropdownの値は通常文字列なので型変換は不要 (enum定義による)

                # --- バリデーションメッセージの設定 ---
                if error_msg:
                    errors.append(f"'{prop_schema.get('title', name)}': {error_msg}")
                    if hasattr(control, "error_text"):
                        control.error_text = error_msg  # type: ignore
                elif hasattr(control, "error_text"):
                    control.error_text = None  # type: ignore # エラー解消

                # エラーがなければ値をinputsに追加（Noneでない場合 or booleanの場合）
                # MCPサーバーが空文字やnullをどう扱うかによる調整が必要な場合あり
                if error_msg is None and (value is not None or field_type == "boolean"):
                    inputs[name] = value

            except ValueError:
                error_msg = f"'{prop_schema.get('title', name)}' に有効な{field_type}値を入力してください。"
                errors.append(error_msg)
                if hasattr(control, "error_text"):
                    control.error_text = f"不正な{field_type}値"  # type: ignore

        if errors:
            self.status_text.value = "入力エラー:\n" + "\n".join(errors)
            self.status_text.color = ft.Colors.ERROR
            return None  # バリデーション失敗
        else:
            self.status_text.value = ""  # エラーメッセージクリア
            return inputs  # バリデーション成功

    async def run_tool(self, e):
        """Runボタンがクリックされたときの処理"""
        validated_inputs = self._validate_inputs()

        if validated_inputs is None:  # バリデーション失敗
            self.page.update()
            return

        self.run_button.disabled = True
        self.progress_ring.visible = True
        self.status_text.value = "実行中..."
        self.status_text.color = ft.Colors.BLUE
        self.output_area.value = ""  # 出力エリアをクリア
        self.page.update()

        try:
            result = await self.mcp_client.run_tool(self.tool_name, validated_inputs)
            # 結果を整形して表示
            try:
                for content in result.content:
                    self.output_area.value = content.text  # type: ignore
            except Exception:
                self.output_area.value = str(result.content)

            self.status_text.value = "実行が完了しました。"
            self.status_text.color = ft.Colors.GREEN

        except (ValueError, ConnectionError, TimeoutError, RuntimeError) as ex:
            self.status_text.value = f"ツールの実行に失敗しました:\n{ex}"
            self.status_text.color = ft.Colors.ERROR
            self.output_area.value = f"エラー:\n{ex}"  # エラー詳細も出力欄に表示
        except Exception as ex:
            self.status_text.value = f"予期しないエラーが発生しました:\n{ex}"
            self.status_text.color = ft.Colors.ERROR
            self.output_area.value = f"予期しないエラー:\n{ex}"
        finally:
            self.run_button.disabled = False
            self.progress_ring.visible = False
            self.page.update()

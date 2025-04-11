import json
import os
from typing import Any, Dict, List, Optional, Tuple


class ConfigManager:
    """設定ファイル (config.json) の読み書きを管理するクラス"""

    def __init__(self, config_file="config.json"):
        self.config_file = config_file
        # より詳細なデフォルト設定
        self.default_config = {
            "active_server_key": "internal_mock",  # デフォルトは内蔵モック
            "external_mcp_url": None,
            "internal_mock_config": {"enabled": True, "type": "sse", "port": 8001},
            "mcpServers": {},  # デフォルトは空
        }
        if not os.path.exists(self.config_file):
            self.save_config(self.default_config)
        else:
            # 既存ファイルがある場合、デフォルトにないキーを追加する
            self._ensure_config_keys()

    def _ensure_config_keys(self):
        """既存の設定ファイルにデフォルトのキーが存在するか確認し、なければ追加する"""
        config = self.load_config(apply_defaults=False)  # 生のデータをロード
        updated = False
        for key, default_value in self.default_config.items():
            if key not in config:
                config[key] = default_value
                updated = True
            # ネストされた辞書もチェック (例: internal_mock_config)
            elif isinstance(default_value, dict) and isinstance(config.get(key), dict):
                internal_updated = False
                for sub_key, sub_default_value in default_value.items():
                    if sub_key not in config[key]:
                        config[key][sub_key] = sub_default_value
                        internal_updated = True
                if internal_updated:
                    updated = True

        if updated:
            print("設定ファイルに不足しているキーを追加しました。")
            self.save_config(config, merge_with_current=False)  # 更新した内容で上書き

    def load_config(self, apply_defaults=True) -> Dict[str, Any]:
        """
        設定ファイルを読み込む.
        apply_defaults=Trueの場合、読み込んだデータにデフォルト値をマージする.
        apply_defaults=Falseの場合、ファイルの内容をそのまま返す.
        """
        config_data = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except json.JSONDecodeError:
                print(f"エラー: {self.config_file} のJSON形式が不正です。")
                # 不正な場合でもデフォルト適用のために空dictを返すか、例外を投げるか
            except Exception as e:
                print(f"設定ファイルの読み込み中にエラーが発生しました: {e}")

        if apply_defaults:
            # デフォルト値をベースに、読み込んだ値で上書きする形でマージ
            final_config = self.default_config.copy()
            # ネストされた辞書も適切にマージする (簡易的なディープマージ)
            for key, value in config_data.items():
                if key in final_config and isinstance(final_config[key], dict) and isinstance(value, dict):
                    final_config[key].update(value)
                else:
                    final_config[key] = value
            return final_config
        else:
            return config_data  # ファイルの内容そのまま

    def save_config(self, config_data: Dict[str, Any], merge_with_current=True) -> bool:
        """設定ファイルに書き込む. merge_with_current=Trueの場合、現在の設定とマージする."""
        try:
            data_to_save = config_data
            if merge_with_current:
                current_config = self.load_config()  # デフォルト適用済みの現在設定
                # current_config をベースに、引数の config_data で上書き
                for key, value in config_data.items():
                    if key in current_config and isinstance(current_config[key], dict) and isinstance(value, dict):
                        current_config[key].update(value)
                    else:
                        current_config[key] = value
                data_to_save = current_config

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"設定ファイルの保存中にエラーが発生しました: {e}")
            return False

    def get_config(self) -> Dict[str, Any]:
        """現在の全設定を取得する (デフォルト適用済み)"""
        return self.load_config()

    def set_config_value(self, key: str, value: Any) -> bool:
        """特定の設定値を更新する (トップレベルキーのみ)"""
        # ネストされたキーの更新は別途専用メソッドを用意するか、
        # get_config()で取得して変更し、save_config()で全体を保存する
        config = self.load_config()
        config[key] = value
        return self.save_config(config, merge_with_current=False)  # 更新した内容で上書き

    def get_active_server_key(self) -> str:
        """現在アクティブなサーバーのキーを取得する"""
        return self.get_config().get("active_server_key", "internal_mock")

    def set_active_server_key(self, key: str) -> bool:
        """アクティブなサーバーキーを設定する"""
        return self.set_config_value("active_server_key", key)

    def get_external_mcp_url(self) -> Optional[str]:
        """外部MCPサーバーのURLを取得する"""
        return self.get_config().get("external_mcp_url")

    def set_external_mcp_url(self, url: Optional[str]) -> bool:
        """外部MCPサーバーのURLを設定する"""
        return self.set_config_value("external_mcp_url", url)

    def get_internal_mock_config(self) -> Dict[str, Any]:
        """内蔵Pythonモックサーバーの設定を取得する"""
        return self.get_config().get("internal_mock_config", {"enabled": True, "port": 8001})

    def is_internal_mock_enabled(self) -> bool:
        return self.get_internal_mock_config().get("enabled", True)

    def get_internal_mock_port(self) -> int:
        return self.get_internal_mock_config().get("port", 8001)

    def get_mcp_servers_config(self) -> Dict[str, Dict[str, Any]]:
        """ユーザー定義のMCPサーバー設定リストを取得する"""
        return self.get_config().get("mcpServers", {})

    def get_server_config(self, server_key: str) -> Optional[Dict[str, Any]]:
        """指定されたキーのサーバー設定を取得する"""
        return self.get_mcp_servers_config().get(server_key)

    def get_server_config_by_key(self, server_key: str | None) -> Optional[Dict[str, Any]]:
        """指定されたキーのサーバー設定を取得 (internal_mock, external, mcpServers を網羅)"""
        config = self.get_config()
        if server_key == "internal_mock":
            # internal_mock_config を返す (type を含む)
            return config.get("internal_mock_config")
        elif server_key == "external":
            # 外部URLの場合は特別な設定オブジェクトを返す (type を含む)
            return {"type": "sse", "url": config.get("external_mcp_url")}
        elif server_key in config.get("mcpServers", {}):
            # mcpServers から該当キーの設定を返す
            return config["mcpServers"].get(server_key)
        else:
            return None

    def get_active_server_config(self) -> Optional[Dict[str, Any]]:
        """現在アクティブなサーバーの設定情報を取得する"""
        active_key = self.get_active_server_key()
        return self.get_server_config_by_key(active_key)

    def get_active_server_type(self) -> Optional[str]:
        """現在アクティブなサーバーのタイプ (sse or stdio) を取得する"""
        active_config = self.get_active_server_config()
        return active_config.get("type") if active_config else None

    def get_active_mcp_url(self) -> Optional[str]:
        """現在アクティブなMCPサーバーのURLを取得する"""
        config = self.get_config()
        active_key = config.get("active_server_key")

        active_config = self.get_server_config_by_key(active_key)
        if not active_config:
            print(f"警告: アクティブサーバーキー '{active_key}' の設定が見つかりません。")
            return None

        server_type = active_config.get("type")
        if server_type == "sse":
            if active_key == "internal_mock":
                mock_config = config.get("internal_mock_config", {})
                port = mock_config.get("port", 8001)
                return f"http://localhost:{port}/sse"
            elif active_key == "external":
                return config.get("external_mcp_url")
            elif active_key in config.get("mcpServers", {}):
                server_config = config["mcpServers"][active_key]
                host = server_config.get("host", "localhost")
                port = server_config.get("port")
                if port:
                    return f"http://{host}:{port}/sse"
                else:
                    print(f"警告: アクティブなサーバー '{active_key}' にポート番号が設定されていません。")
                    return None
            else:
                print(f"警告: 不明なアクティブサーバーキー '{active_key}' です。")
                return None  # 不明なキー or 未設定
        else:  # stdio や他のタイプの場合は URL はない
            return None

    def get_all_managed_servers(self) -> List[Tuple[str, Dict[str, Any]]]:
        """
        管理対象となる可能性のある全てのサーバー(内蔵モックとmcpServers)の
        設定情報をリストで返す (キー, 設定辞書) のタプル。
        enabled フラグは考慮しない。
        """
        servers = []
        # 内蔵モック
        mock_config = self.get_internal_mock_config()
        servers.append(("internal_mock", mock_config))

        # ユーザー定義サーバー
        user_servers = self.get_mcp_servers_config()
        for key, conf in user_servers.items():
            servers.append((key, conf))

        return servers

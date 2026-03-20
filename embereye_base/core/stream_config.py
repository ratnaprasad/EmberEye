import json
from datetime import datetime
import shutil
import os
from resource_helper import get_writable_path, copy_bundled_resource

class StreamConfig:
    CONFIG_FILE = get_writable_path("stream_config.json")
    
    @staticmethod
    def load_config():
        # Copy bundled config if it doesn't exist
        copy_bundled_resource('stream_config.json', StreamConfig.CONFIG_FILE)
        
        default_config = {
            "groups": ["Default"],
            "streams": []
        }
        try:
            if os.path.exists(StreamConfig.CONFIG_FILE):
                with open(StreamConfig.CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    return config if isinstance(config, dict) else default_config
            return default_config
        except Exception as e:
            print(f"Config load error: {str(e)}")
            return default_config

    @staticmethod
    def save_config(config):
        try:
            with open(StreamConfig.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=4)
            return True
        except Exception as e:
            print(f"Config save error: {str(e)}")
            return False
    
    @staticmethod
    def export_config(path):
        """Export configuration to specified path"""
        try:
            if not os.path.exists(StreamConfig.CONFIG_FILE):
                return False
            shutil.copyfile(StreamConfig.CONFIG_FILE, path)
            return True
        except Exception as e:
            print(f"Export error: {str(e)}")
            return False

    @staticmethod
    def import_config(path):
        """Import configuration from specified path"""
        try:
            # Validate file format
            with open(path, 'r') as f:
                config = json.load(f)
                if "groups" not in config or "streams" not in config:
                    return False
                
            # Create backup before overwriting
            backup_path = os.path.join(
                os.path.dirname(StreamConfig.CONFIG_FILE),
                f"config_backup_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
            )
            shutil.copyfile(StreamConfig.CONFIG_FILE, backup_path)
            
            # Replace with new config
            shutil.copyfile(path, StreamConfig.CONFIG_FILE)
            return True
        except Exception as e:
            print(f"Import error: {str(e)}")
            return False

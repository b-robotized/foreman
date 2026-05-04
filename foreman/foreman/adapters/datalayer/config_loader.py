import os
import yaml

class DatalayerConfigLoader:
    def __init__(self):
        self.snap_common = os.environ.get('SNAP_COMMON', '.')

        self.app_data_dir = os.path.join(
            self.snap_common, 
            'solutions', 
            'activeConfiguration', 
            'AppData', 
            'foreman'
        )
        
        self.config_file = os.path.join(self.app_data_dir, 'scenario.yaml')

    def save_config(self, config_dict):
        os.makedirs(self.app_data_dir, exist_ok=True)
        
        with open(self.config_file, 'w') as f:
            yaml.dump(config_dict, f)
        print(f"Saved config to {self.config_file}")

    def load_config(self):
        if not os.path.exists(self.config_file):
            print("No scenario.yaml found, using defaults.")
            return {}
            
        with open(self.config_file, 'r') as f:
            return yaml.safe_load(f)
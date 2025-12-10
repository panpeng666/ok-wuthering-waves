from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame
from qfluentwidgets import (
    ComboBox, PrimaryPushButton, StrongBodyLabel,
    BodyLabel, DoubleSpinBox, CardWidget,
    SwitchButton, TextEdit
)

from src.echo.stats import stats_manager
from src.echo.profile import coef_data

class EchoInterface(QWidget):
    """声骸强化工具的配置与交互界面"""
    
    config_changed = Signal(dict) # 配置变更信号

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.stats = stats_manager
        self.init_ui()
        self.load_config()
        
    def init_ui(self):
        self.main_layout = QHBoxLayout(self)
        
        # --- 左侧：配置区 ---
        self.settings_panel = CardWidget(self)
        self.settings_layout = QVBoxLayout(self.settings_panel)
        
        # 1. 角色选择
        self.role_label = StrongBodyLabel("目标角色", self)
        self.role_combo = ComboBox(self)
        # 加载角色列表 (从 coef_data)
        self.roles = sorted(list(coef_data.keys()))
        self.role_combo.addItems(self.roles)
        self.role_combo.currentTextChanged.connect(self._on_role_changed)
        
        # 2. 阈值设置
        self.threshold_label = StrongBodyLabel("评分阈值 (0.0 - 1.0)", self)
        self.threshold_spin = DoubleSpinBox(self)
        self.threshold_spin.setRange(0.0, 1.0)
        self.threshold_spin.setSingleStep(0.05)
        self.threshold_spin.valueChanged.connect(lambda v: self._save_conf('threshold', v))

        # 3. 功能开关
        self.auto_tune_switch = SwitchButton("自动调谐", self, indicatorPos=Qt.RightToLeft)
        self.auto_tune_switch.checkedChanged.connect(lambda v: self._save_conf('auto_tune', v))
        
        self.auto_next_switch = SwitchButton("自动翻页 (Next)", self, indicatorPos=Qt.RightToLeft)
        self.auto_next_switch.checkedChanged.connect(lambda v: self._save_conf('auto_next', v))

        # 4. 布局添加
        self.settings_layout.addWidget(self.role_label)
        self.settings_layout.addWidget(self.role_combo)
        self.settings_layout.addSpacing(10)
        self.settings_layout.addWidget(self.threshold_label)
        self.settings_layout.addWidget(self.threshold_spin)
        self.settings_layout.addSpacing(10)
        self.settings_layout.addWidget(self.auto_tune_switch)
        self.settings_layout.addWidget(self.auto_next_switch)
        self.settings_layout.addStretch(1)
        
        # --- 右侧：信息与日志 ---
        self.info_panel = QFrame(self)
        self.info_layout = QVBoxLayout(self.info_panel)
        
        # 推荐属性展示
        self.attr_card = CardWidget(self)
        self.attr_layout = QVBoxLayout(self.attr_card)
        self.attr_title = StrongBodyLabel("当前角色推荐属性权重", self)
        self.attr_desc = BodyLabel("请选择角色以查看...", self)
        self.attr_desc.setWordWrap(True)
        self.attr_layout.addWidget(self.attr_title)
        self.attr_layout.addWidget(self.attr_desc)
        
        # 日志/状态显示
        self.log_text = TextEdit(self)
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("等待任务启动...")
        
        self.info_layout.addWidget(self.attr_card)
        self.info_layout.addWidget(self.log_text)
        
        # --- 组装 ---
        self.main_layout.addWidget(self.settings_panel, 1)
        self.main_layout.addWidget(self.info_panel, 2)

    def load_config(self):
        """加载上次保存的配置"""
        last_role = self.stats.get_user_conf('target_role', 'Default')
        if last_role in self.roles:
            self.role_combo.setCurrentText(last_role)
            
        self.threshold_spin.setValue(self.stats.get_user_conf('threshold', 0.8))
        self.auto_tune_switch.setChecked(self.stats.get_user_conf('auto_tune', True))
        self.auto_next_switch.setChecked(self.stats.get_user_conf('auto_next', False))
        
        # 触发一次刷新
        self._on_role_changed(self.role_combo.currentText())

    def _save_conf(self, key, value):
        self.stats.set_user_conf(key, value)
        self.config_changed.emit(self.stats._user_config)

    def _on_role_changed(self, role_name):
        self._save_conf('target_role', role_name)
        
        # 更新右侧权重显示
        if role_name in coef_data:
            data = coef_data[role_name]
            dmg_source = data.get('dmg_source', 'Unknown')
            coefs = data.get('coef', {})
            
            # 格式化显示文本
            desc = f"伤害来源: {dmg_source}\n\n重要副词条权重:\n"
            sorted_coefs = sorted(coefs.items(), key=lambda x: x[1], reverse=True)
            for k, v in sorted_coefs:
                if v > 0:
                    # 获取中文名
                    stat_info = self.stats.get_stat(k)
                    name = stat_info['name'] if stat_info else k
                    desc += f"- {name}: {v}\n"
            
            self.attr_desc.setText(desc)

    def log(self, message: str):
        """追加日志到界面"""
        self.log_text.append(message)

import re
from typing import Dict, List, Optional, Tuple, Any
from src.echo.profile import EchoProfile
from src.echo.stats import stats_manager
from ok import Logger

logger = Logger.get_logger(__name__)

class EchoVision:
    def __init__(self, task_executor):
        """
        :param task_executor: BaseWWTask 的实例，用于提供 OCR 和截图能力
        """
        self.task = task_executor
        self.stats_manager = stats_manager

    def scan_echo_panel(self) -> Optional[EchoProfile]:
        """
        扫描当前屏幕上的声骸详情面板，返回 EchoProfile 对象。
        如果无法识别有效信息，返回 None。
        """
        # 1. 识别等级
        level = self._scan_level()
        
        # 2. 识别套装和名称 (用于确定是哪个声骸)
        name = self._scan_name()
        set_name = self._scan_set_name() # 虽然 Profile 暂时没存套装，但逻辑上需要
        
        # 3. 识别属性
        # 主属性通常固定，且对评分影响较小（除了属性伤害），这里重点识别副词条
        sub_stats = self._scan_sub_stats()
        
        if not sub_stats and level > 0:
            logger.warning("Detected level > 0 but no sub stats found, might be OCR error.")
        
        # 4. 构建 EchoProfile
        profile = EchoProfile(level=level, name=name)
        
        # 填充属性
        for key, value in sub_stats.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
            else:
                logger.warning(f"Unknown stat key: {key} with value {value}")
                
        return profile

    def _scan_level(self) -> int:
        """
        TODO: 识别声骸等级
        坐标范围: 需要调试确认
        """
        # 示例逻辑
        # box = self.task.box_of_screen(0.x, 0.y, 0.x, 0.y)
        # text = self.task.ocr(box=box, match=r'\+(\d+)')
        return 0

    def _scan_name(self) -> str:
        """
        TODO: 识别声骸名称
        """
        return ""

    def _scan_set_name(self) -> str:
        """
        TODO: 识别套装名称
        """
        return ""

    def _scan_sub_stats(self) -> Dict[str, float]:
        """
        识别副属性列表。
        返回字典: {'cri_rate': 6.3, 'atk_rate': 7.9}
        """
        results = {}
        
        # TODO: 定义副词条区域的 ROI
        # 假设副词条在一个固定的列表区域
        # box = self.task.box_of_screen(0.65, 0.4, 0.9, 0.8) 
        # texts = self.task.ocr(box=box)
        
        # 模拟 OCR 结果进行解析逻辑开发
        # texts = ["暴击 6.3%", "攻击 7.9%", "防御 40"]
        
        # for text in texts:
        #     key, value = self._parse_stat_text(text)
        #     if key:
        #         results[key] = value
                
        return results

    def _parse_stat_text(self, text: str) -> Tuple[Optional[str], float]:
        """
        解析单行属性文本，例如 "暴击 6.3%" -> ('cri_rate', 6.3)
        """
        # 1. 清洗文本
        text = text.replace(" ", "").replace(":", "").replace("：", "")
        
        # 2. 匹配数值
        # 匹配小数或整数
        num_match = re.search(r'(\d+\.?\d*)', text)
        if not num_match:
            return None, 0.0
        
        value_str = num_match.group(1)
        value = float(value_str)
        
        # 3. 匹配属性名
        # 遍历 stats_manager 中的所有属性名进行模糊匹配
        matched_key = None
        stats = self.stats_manager.get_all_stats()
        
        # 优先匹配长名字，防止 "攻击" 匹配到 "攻击加成"
        sorted_keys = sorted(stats.keys(), key=lambda k: len(stats[k]['name']), reverse=True)
        
        for key in sorted_keys:
            stat_name = stats[key]['name']
            # 简单的包含匹配
            if stat_name in text:
                matched_key = key
                break
        
        # 处理特殊情况或别名 (OCR 常见错误)
        if not matched_key:
            if "攻" in text and "%" in text: matched_key = "atk_rate"
            elif "攻" in text: matched_key = "atk_num"
            elif "防" in text and "%" in text: matched_key = "def_rate"
            elif "防" in text: matched_key = "def_num"
            elif "生" in text and "%" in text: matched_key = "hp_rate"
            elif "生" in text: matched_key = "hp_num"
            elif "爆" in text or "暴" in text:
                if "伤" in text: matched_key = "cri_dmg"
                else: matched_key = "cri_rate"
            elif "充" in text or "效" in text: matched_key = "resonance_eff"
        
        return matched_key, value

    def check_state(self) -> str:
        """
        判断当前界面状态。
        Returns:
            'CAN_ENHANCE': 可强化
            'CAN_TUNE': 可调谐 (有红点)
            'MAX_LEVEL': 已满级
            'UNKNOWN': 未知
        """
        # TODO: 基于按钮状态判断
        return "UNKNOWN"

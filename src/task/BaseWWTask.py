import math
import re
import time
from datetime import datetime, timedelta

import numpy as np

from ok import BaseTask, Logger, find_boxes_by_name, og, find_color_rectangles, mask_white
from ok import CannotFindException
import cv2

logger = Logger.get_logger(__name__)
number_re = re.compile(r'^(\d+)$')
stamina_re = re.compile(r'^(\d+)/(\d+)$')
f_white_color = {
    'r': (235, 255),  # Red range
    'g': (235, 255),  # Green range
    'b': (235, 255)  # Blue range
}
processed_feature = False


class BaseWWTask(BaseTask):
    """
    BaseWWTask: 所有鸣潮 (Wuthering Waves) 自动化任务的基类。
    
    该类继承自 ok-script 的 BaseTask，主要职责是：
    1.  **封装游戏交互**: 提供针对鸣潮客户端的特定操作，如缩放地图 (`zoom_map`)、检测战斗状态 (`in_combat`)、队伍检测 (`in_team`) 等。
    2.  **提供通用能力**: 实现了寻路 (`walk_to_box`)、拾取声骸 (`pick_echo`)、体力管理 (`use_stamina`) 等通用功能。
    3.  **状态管理**: 管理月卡检测、游戏语言识别等全局状态。
    
    所有具体的业务任务（如刷本、自动战斗）都应继承自此类或其子类（如 BaseCombatTask）。
    """
    map_zoomed = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 加载全局配置
        self.pick_echo_config = self.get_global_config('Pick Echo Config')
        self.monthly_card_config = self.get_global_config('Monthly Card Config')
        self.char_config = self.get_global_config('Character Config')
        self.key_config = self.get_global_config('Game Hotkey Config')  # 游戏热键配置
        self.next_monthly_card_start = 0
        self._logged_in = False

    def is_open_world_auto_combat(self):
        """
        判断当前任务是否属于大世界自动战斗任务。
        用于区分是在副本内战斗还是在野外战斗。
        """
        from src.task.AutoCombatTask import AutoCombatTask
        from src.task.TacetTask import TacetTask
        from src.task.DailyTask import DailyTask
        if isinstance(self, AutoCombatTask):
            if not self.in_realm(): # 如果不在副本(Realm)中，则认为在大世界
                return True
        elif isinstance(self, (TacetTask, DailyTask)):
            return True
        return False

    def zoom_map(self, esc=True):
        """
        将游戏内地图缩放到最大，方便进行图像识别定位。
        操作流程：按下M打开地图 -> 点击特定位置缩放 -> (可选)按下ESC退出地图。
        """
        if not self.map_zoomed:
            self.log_info('zoom map to max')
            self.map_zoomed = True
            self.send_key('m', after_sleep=1)
            self.click_relative(0.94, 0.33, after_sleep=0.5) # 点击缩放按钮
            if esc:
                self.send_key('esc', after_sleep=1)

    def validate(self, key, value):
        message = self.validate_config(key, value)
        if message:
            return False, message
        else:
            return True, None

    def absorb_echo_text(self, ignore_config=False):
        """
        返回用于识别“吸收声骸”提示的正则表达式，根据游戏语言动态调整。
        """
        if self.game_lang == 'zh_CN' or self.game_lang == 'en_US' or self.game_lang == 'zh_TW':
            return re.compile(r'(吸收|Absorb)')
        else:
            return None

    @property
    def absorb_echo_feature(self):
        return self.get_feature_by_lang('absorb')

    def get_feature_by_lang(self, feature):
        """
        根据当前游戏语言获取对应的特征图片名称。
        例如 feature='absorb' 且语言为 'zh_CN'，则查找 'absorb_zh_CN'。
        """
        lang_feature = feature + '_' + self.game_lang
        if self.feature_exists(lang_feature):
            return lang_feature
        else:
            return None

    def set_check_monthly_card(self, next_day=False):
        """
        设置下一次检查月卡弹窗的时间。
        通常设定为第二天的凌晨4点（游戏刷新时间）。
        """
        if self.monthly_card_config.get('Check Monthly Card'):
            now = datetime.now()
            hour = self.monthly_card_config.get('Monthly Card Time')
            # Calculate the next 4 o'clock in the morning
            next_four_am = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if now >= next_four_am or next_day:
                next_four_am += timedelta(days=1)
            next_monthly_card_start_date_time = next_four_am - timedelta(seconds=30)
            # Subtract 1 minute from the next 4 o'clock in the morning
            self.next_monthly_card_start = next_monthly_card_start_date_time.timestamp()
            logger.info('set next monthly card start time to {}'.format(next_monthly_card_start_date_time))
        else:
            self.next_monthly_card_start = 0

    @property
    def f_search_box(self):
        """
        定义搜索“F”交互键提示的屏幕区域。
        通过相对于某个固定UI元素（'pick_up_f_hcenter_vcenter'）的偏移来确定。
        """
        f_search_box = self.get_box_by_name('pick_up_f_hcenter_vcenter')
        f_search_box = f_search_box.copy(x_offset=-f_search_box.width * 0.3,
                                         width_offset=f_search_box.width * 0.65,
                                         height_offset=f_search_box.height * 6.5,
                                         y_offset=-f_search_box.height * 5,
                                         name='search_dialog')
        return f_search_box

    def find_f_with_text(self, target_text=None):
        """
        查找屏幕上带有特定文本的“F”交互提示。
        
        Args:
            target_text: 正则表达式或字符串，用于匹配交互提示旁边的文字（如“吸收”、“对话”）。
                         如果为None，则只查找是否有F键提示。
        
        Returns:
            Box对象（如果找到）或 None。
        """
        f = self.find_one('pick_up_f_hcenter_vcenter', box=self.f_search_box, threshold=0.8)
        if not f:
            return None
        if not target_text:
            return f

        # 二次确认：检查F键图标内部是否为白色，排除误识别
        start = time.time()
        percent = 0.0
        while time.time() - start < 1:
            percent = self.calculate_color_percentage(f_white_color, f)
            if percent > 0.5:
                break
            self.next_frame()
            self.log_debug(f'f white color percent: {percent} wait')
        if percent < 0.5:
            return None

        # 如果指定了文字，则在F键右侧区域进行OCR识别
        if target_text:
            search_text_box = f.copy(x_offset=f.width * 5, width_offset=f.width * 7, height_offset=4.5 * f.height,
                                     y_offset=-0.8 * f.height, name='search_text_box')
            text = self.ocr(box=search_text_box, match=target_text)
            logger.debug(f'found f with text {text}, target_text {target_text}')
            if text:
                # 简单的防抖/位置校验：文字应该在F键的下方或平行位置
                if text[0].y > search_text_box.y + f.height * 1:
                    logger.debug(f'found f with text {text} below, target_text {target_text}')
                    self.scroll_relative(0.5, 0.5, 1)
                return f
        else:
            return f

    def has_target(self):
        return False

    def walk_to_yolo_echo(self, time_out=8, update_function=None, echo_threshold=0.5):
        """
        控制角色走向通过 YOLO 模型识别到的声骸。
        
        Args:
            time_out: 最大寻路时间。
            update_function: 每次循环调用的回调函数（可选）。
            echo_threshold: YOLO 识别的置信度阈值。
        """
        last_direction = None
        start = time.time()
        no_echo_start = 0
        while time.time() - start < time_out:
            self.next_frame()
            # 1. 优先检查是否可以直接拾取 (F键)
            if self.pick_f():
                self.log_debug('pick echo success')
                self._stop_last_direction(last_direction)
                return True
            # 2. 如果进入战斗，停止寻路
            if self.in_combat():
                self.log_debug('pick echo has_target return fail')
                self._stop_last_direction(last_direction)
                return False
            
            # 3. 使用 YOLO 寻找屏幕上的声骸
            echos = self.find_echos(threshold=echo_threshold)
            if not echos:
                # 如果没看到声骸，尝试向前走几秒，如果还是没有则放弃
                if no_echo_start == 0:
                    no_echo_start = time.time()
                elif time.time() - no_echo_start > 3:
                    self.log_debug(f'walk front to_echo, no echos found, break')
                    break
                next_direction = 'w'
            else:
                # 4. 根据声骸在屏幕上的位置调整行走方向
                no_echo_start = 0
                echo = echos[0]
                center_distance = echo.center()[0] - self.width_of_screen(0.5)
                threshold = 0.05 if not last_direction else 0.15 # 迟滞阈值，防止左右反复横跳
                
                # 如果水平距离足够近，则向前(W)或向后(S)
                if abs(center_distance) < self.height_of_screen(threshold):
                    if echo.y + echo.height > self.height_of_screen(0.65): # 目标太靠下（太近或在身后），后退
                        next_direction = 's'
                    else:
                        next_direction = 'w'
                # 否则向左(A)或向右(D)调整
                elif center_distance > 0:
                    next_direction = 'd'
                else:
                    next_direction = 'a'
            last_direction = self._walk_direction(last_direction, next_direction)
            if update_function is not None:
                update_function()
        self._stop_last_direction(last_direction)

    def _walk_direction(self, last_direction, next_direction):
        """切换行走方向：松开旧按键，按下新按键"""
        if next_direction != last_direction:
            self._stop_last_direction(last_direction)
            if next_direction:
                self.send_key_down(next_direction)
        return next_direction

    def _stop_last_direction(self, last_direction):
        """停止当前的移动"""
        if last_direction:
            self.send_key_up(last_direction)
            self.sleep(0.01)
        return None

    def walk_to_box(self, find_function, time_out=30, end_condition=None, y_offset=0.05, x_threshold=0.07,
                    use_hook=False):
        """
        通用的寻路函数：根据 find_function 找到的目标不断调整位置，直到满足 end_condition。
        """
        start = time.time()
        while time.time() - start < time_out:
            if ended := self.do_walk_to_box(find_function, time_out=time_out - (time.time() - start),
                                            end_condition=end_condition, y_offset=y_offset,
                                            x_threshold=x_threshold, use_hook=use_hook):
                return ended

    def do_walk_to_box(self, find_function, time_out=30, end_condition=None, y_offset=0.05, x_threshold=0.07,
                       use_hook=False):
        """
        执行具体的寻路逻辑。
        
        Args:
            find_function: 返回当前目标 Box 的函数 (例如找到宝箱图标)。
            end_condition: 结束条件的函数 (例如出现“打开”提示)。
            y_offset: Y轴偏置，用于调整垂直对齐的目标点。
            x_threshold: X轴对齐的容忍度。
            use_hook: 是否在合适的时候使用钩锁 (T键)。
        """
        if find_function:
            # 等待目标出现
            self.wait_until(lambda: (not end_condition or end_condition()) or find_function(), raise_if_not_found=True,
                            time_out=time_out)
        last_direction = None
        start = time.time()
        ended = False
        running = False
        last_target = None
        centered = False
        while time.time() - start < time_out:
            self.next_frame()
            if end_condition:
                ended = end_condition()
                if ended:
                    break
            
            # 寻找目标
            treasure_icon = find_function()
            if isinstance(treasure_icon, list):
                if len(treasure_icon) > 0:
                    treasure_icon = treasure_icon[0]
                else:
                    treasure_icon = None
            if treasure_icon:
                last_target = treasure_icon
            
            # 导航逻辑
            if last_target is None:
                # 丢失目标，尝试反向寻找
                next_direction = self.opposite_direction(last_direction)
                self.log_info('find_function not found, change to opposite direction')
            else:
                x, y = last_target.center()
                y = max(0, y - self.height_of_screen(y_offset))
                x_abs = abs(x - self.width_of_screen(0.5))
                threshold = 0.04 if not last_direction else x_threshold
                
                # 判断是否水平对齐
                centered = centered or x_abs <= self.width_of_screen(threshold)
                if not centered:
                    # 未对齐，左右调整
                    if x > self.width_of_screen(0.5):
                        next_direction = 'd'
                    else:
                        next_direction = 'a'
                else:
                    # 已对齐，前后调整
                    if last_direction == 's':
                        center = 0.45
                    elif last_direction == 'w':
                        center = 0.6
                    else:
                        center = 0.5
                    if y > self.height_of_screen(center):
                        next_direction = 's'
                    else:
                        next_direction = 'w'
            
            # 执行按键操作
            if next_direction != last_direction:
                if last_direction:
                    self.send_key_up(last_direction)
                    self.sleep(0.001)
                last_direction = next_direction
                if next_direction:
                    self.send_key_down(next_direction)
            
            # 跑步控制 (Shift) - 当在墙上时自动爬墙
            if running:
                if not self.find_one('on_the_wall', threshold=0.7):
                    self.log_info('not on the wall, stop running')
                    self.mouse_up(key='right')
            else:
                if next_direction == 'w' and self.find_one('on_the_wall', threshold=0.7):
                    self.log_info('on the wall, start running')
                    running = True
                    self.mouse_down(key='right')
                    self.sleep(0.1)
            
            # 钩锁使用
            if use_hook and next_direction == 'w':
                if self.find_one('tool_teleport', 0.75):
                    self.send_key(self.key_config['Tool Key'])
                    self.sleep(3)
                    continue
        
        # 停止所有动作
        if last_direction:
            self.send_key_up(last_direction)
            self.sleep(0.001)
        if running:
            self.send_key_up('shift')
        if not end_condition:
            return last_direction is not None
        else:
            return ended

    def opposite_direction(self, direction):
        if direction == 'w':
            return 's'
        elif direction == 's':
            return 'w'
        elif direction == 'a':
            return 'd'
        elif direction == 'd':
            return 'a'
        else:
            return 'w'

    def get_direction(self, location_x, location_y, screen_width, screen_height, centered, current_direction):
        """
        根据目标点坐标，计算应该往哪个方向走 ('w', 'a', 's', 'd')。
        简单的象限判断逻辑。
        """
        if screen_width <= 0 or screen_height <= 0:
            # Handle invalid dimensions, default based on horizontal position
            return "a" if location_x < screen_width / 2 else "d"
        center_x = screen_width / 2
        center_y = screen_height / 2
        # Calculate vector from point towards the center
        delta_x = center_x - location_x
        delta_y = center_y - location_y
        # Determine dominant direction based on vector magnitude
        direction = None
        if (abs(delta_x) > abs(delta_y) or (not current_direction and abs(delta_x) > 0.05 * screen_height)
                or abs(delta_x) > 0.15 * screen_height):
            # More horizontal movement needed
            return "a" if delta_x > 0 else "d"

            # More vertical movement needed (or equal)
        return "w" if delta_y > 0 else "s"

    def find_treasure_icon(self):
        """在屏幕中央区域寻找宝箱图标"""
        return self.find_one('treasure_icon', box=self.box_of_screen(0.18, 0.1, 0.82, 0.81), threshold=0.7)

    def click(self, x=-1, y=-1, move_back=False, name=None, interval=-1, move=True, down_time=0.01, after_sleep=0,
              key="left"):
        """
        封装的点击函数。
        如果 x, y 为 -1，则点击屏幕中心。
        down_time 默认为 0.2s，模拟真实点击。
        """
        if x == -1 and y == -1:
            x = self.width_of_screen(0.5)
            y = self.height_of_screen(0.5)
            move = False
            down_time = 0.01
        else:
            down_time = 0.2
        return super().click(x, y, move_back, name, interval, move=move, down_time=down_time, after_sleep=after_sleep,
                             key=key)

    def check_for_monthly_card(self):
        """检查并处理月卡弹窗"""
        if self.should_check_monthly_card():
            start = time.time()
            logger.info(f'check_for_monthly_card start check')
            if self.in_combat():
                logger.info(f'check_for_monthly_card in combat return')
                return time.time() - start
            if self.in_team_and_world():
                logger.info(f'check_for_monthly_card in team send sleep until monthly card popup')
                monthly_card = self.wait_until(self.handle_monthly_card, time_out=120, raise_if_not_found=False)
                logger.info(f'wait monthly card end {monthly_card}')
                cost = time.time() - start
                return cost
        return 0

    def in_realm(self):
        """判断是否在副本 (Realm/Domain) 中"""
        return not bool(getattr(self, 'treat_as_not_in_realm', False)) and self.find_one('illusive_realm_exit',
                                                                                         threshold=0.7,
                                                                                         frame_processor=convert_bw) and self.in_team() and not self.find_one(
            'world_earth_icon', threshold=0.55,
            frame_processor=convert_bw)

    def in_world(self):
        """判断是否在大世界 (Overworld)"""
        return self.find_one('world_earth_icon', threshold=0.55,
                             frame_processor=convert_bw) and self.in_team() and not self.find_one('illusive_realm_exit',
                                                                                                  threshold=0.7,
                                                                                                  frame_processor=convert_bw)

    def in_illusive_realm(self):
        """判断是否在深塔/肉鸽 (Illusive Realm) 菜单"""
        return self.find_one('new_realm_4') and self.in_realm() and self.find_one('illusive_realm_menu', threshold=0.6)

    def walk_until_f(self, direction='w', time_out=1, raise_if_not_found=True, backward_time=0, target_text=None,
                     check_combat=False, running=False):
        """
        一直往某个方向走，直到出现 F 键提示。
        常用于“走到NPC面前对话”或“走到机关前操作”。
        """
        logger.info(f'walk_until_f direction {direction} target_text: {target_text}')
        if not self.find_f_with_text(target_text=target_text):
            # 视角复位到正前方
            self.middle_click(after_sleep=0.2)
            # 可选：先倒退一点距离 (backward_time)，防止离得太近F键反而不显示
            if backward_time > 0:
                if self.send_key_and_wait_f('s', raise_if_not_found, backward_time, target_text=target_text,
                                            running=running, check_combat=check_combat):
                    logger.info('walk backward found f')
                    return True
            if self.send_key_and_wait_f(direction, raise_if_not_found, time_out, target_text=target_text,
                                        running=running, check_combat=check_combat):
                logger.info('walk forward found f')
                return True
            return False
        else:
            return True

    def get_stamina(self):
        """
        使用 OCR 获取当前体力和备用体力。
        Returns: (当前体力, 备用体力, 总和)
        """
        boxes = self.wait_ocr(0.49, 0.0, 0.92, 0.10, raise_if_not_found=False,
                              match=[number_re, stamina_re])
        if not boxes:
            self.screenshot('stamina_error')
            return -1, -1, -1
        current_box = find_boxes_by_name(boxes, stamina_re)
        if current_box:
            current = int(current_box[0].name.split('/')[0])
        else:
            current = 0
        back_up_box = find_boxes_by_name(boxes, number_re)
        if back_up_box:
            back_up = int(back_up_box[0].name)
        else:
            back_up = 0
        self.info_set('current_stamina', current)
        self.info_set('back_up_stamina', back_up)
        return current, back_up, current + back_up

    def use_stamina(self, once, must_use=0):
        """
        使用体力（包括吃燃料）。
        
        Args:
            once: 每次副本消耗的体力 (如 40 或 60)。
            must_use: 必须消耗的体力值。
        Returns:
            can_continue: 是否有足够体力继续。
            used: 实际消耗的体力。
        """
        self.sleep(1)
        double = self.ocr(0.55, 0.56, 0.75, 0.69, match=[re.compile(str(once * 2))])
        current, back_up, total = self.get_stamina()
        y = 0.62
        # 判断是否有双倍掉落活动
        if not double:  # 找不到双倍数字, 说明有UP, 点击右边
            x = 0.67
            logger.info("找不到双倍数字, 说明有UP, 点击右边")
            used = once
        else:
            # 策略：如果体力足够或必须使用体力，则尝试使用双倍
            if current >= once * 2:
                used = once * 2
                x = 0.67
                logger.info(f"当前体力大于等于双倍, {current} >= {once * 2}")
            elif must_use > once and total >= once * 2:
                used = once * 2
                x = 0.67
                logger.info(f"当前加备用大于日常剩余所需, 使用双倍, {must_use} >= {once} and {total} >= {once * 2}")
            else:
                logger.info(f"使用单倍体力")
                used = once
                x = 0.32
        self.click(x, y, after_sleep=0.5)
        
        # 处理补充体力弹窗
        if self.wait_feature('gem_add_stamina', horizontal_variance=0.4, vertical_variance=0.05,
                             time_out=1):  # 看是否需要使用备用体力
            self.click(0.70, 0.71, after_sleep=0.5)  # 点击确认
            self.click(0.70, 0.71, after_sleep=1)
            self.back(after_sleep=0.5)
            self.click(x, y, after_sleep=0.5)

        current -= used
        must_use -= used
        total -= used
        
        # 判断是否还有足够体力进行下一次循环
        if total < once:
            logger.info(f"current stamina: {current} not enough to continue")
            can_continue = False
        elif must_use <= 0 and current < once:
            can_continue = False
            logger.info(f"current stamina: {current} must_use completed, no need to use back_up")
        else:
            can_continue = True
        return can_continue, used

    def send_key_and_wait_f(self, direction, raise_if_not_found, time_out, running=False, target_text=None,
                            check_combat=False):
        """
        辅助函数：按住方向键的同时等待 F 键出现。
        """
        if time_out <= 0:
            return
        self.send_key_down(direction)
        if running:
            self.sleep(0.1)
            self.mouse_down(key='right')
        f_found = self.wait_until(
            lambda: self.find_f_with_text(target_text=target_text) or (check_combat and self.in_combat()),
            time_out=time_out,
            raise_if_not_found=False)
        self.send_key_up(direction)
        if running:
            self.sleep(0.1)
            self.mouse_up(key='right')
        if not f_found:
            if raise_if_not_found:
                raise CannotFindException('cant find the f to enter')
            else:
                logger.warning(f"can't find the f to enter")
                return False
        return f_found

    def run_until(self, condiction, direction, time_out, raise_if_not_found=False, running=False):
        """
        一直跑直到满足某个条件 condiction() 为 True。
        """
        if time_out <= 0:
            return
        self.send_key_down(direction)
        if running:
            self.sleep(0.1)
            logger.debug(f'run_until condiction {condiction} direction {direction}')
            self.mouse_down(key='right')
        result = self.wait_until(condiction, time_out=time_out,
                                 raise_if_not_found=raise_if_not_found)
        self.send_key_up(direction)
        if running:
            self.sleep(0.1)
            self.mouse_up(key='right')

        return result

    def is_moving(self):
        return False

    def handle_claim_button(self):
        """处理领取奖励的弹窗"""
        while self.wait_until(self.has_claim, raise_if_not_found=False, time_out=1.5):
            self.sleep(0.5)
            self.send_key('esc')
            self.sleep(0.5)
            logger.info(f"handle_claim_button found a claim reward")
            return True

    def handle_claim_button_now(self):
        """立即尝试处理领取奖励"""
        if self.has_claim():
            self.sleep(0.5)
            self.send_key('esc')
            self.sleep(0.2)
            logger.info(f"handle_claim_button_now found a claim reward")
            return True

    def has_claim(self):
        """检测屏幕上是否有领取奖励的UI特征"""
        return not self.in_team()[0] and self.find_one('claim_cancel_button_hcenter_vcenter', horizontal_variance=0.05,
                                                       vertical_variance=0.1, threshold=0.8)

    def test_absorb(self):
        # self.set_image('tests/images/absorb.png')
        image = cv2.imread('tests/images/absorb.png')
        result = self.executor.ocr_lib(image, use_det=True, use_cls=False, use_rec=True)
        self.logger.info(f'ocr_result {result}')

    def find_echos(self, threshold=0.3):
        """
        使用 YOLO 模型查找屏幕上的声骸 (Echo)。
        
        Args:
            threshold: 置信度阈值。
        Returns:
            list: 包含声骸位置信息的 Box 列表。
        """
        # Load the ONNX model
        ret = og.my_app.yolo_detect(self.frame, threshold=threshold, label=0) # label=0 通常指声骸类

        # 调整 Box 位置，使其更贴近地面/脚部
        for box in ret:
            box.y += box.height * 1 / 3
            box.height = 1
        self.draw_boxes("echo", ret)
        return ret

    def yolo_find_all(self, threshold=0.3):
        """使用 YOLO 查找所有类别的物体"""
        # Load the ONNX model
        boxes = og.my_app.yolo_detect(self.frame, threshold=threshold, label=-1)
        ret = sorted(boxes, key=lambda detection: detection.confidence, reverse=True)
        return ret

    def pick_echo(self):
        """
        尝试拾取声骸。
        逻辑：检测是否有“吸收”字样的F键提示，如果有则按F。
        """
        if self.find_f_with_text(target_text=self.absorb_echo_text()):
            self.send_key('f')
            if not self.handle_claim_button():
                self.log_debug('found a echo picked')
                return True

    def pick_f(self, handle_claim=True):
        """
        通用的按F键拾取/交互。
        不检查文本，只要有F提示就按。
        """
        if self.find_one('pick_up_f_hcenter_vcenter', box=self.f_search_box, threshold=0.8):
            self.send_key('f', after_sleep=0.8)
            if not handle_claim:
                return True
            if not self.handle_claim_button():
                self.log_debug('found a echo picked')
                return True

    def walk_to_treasure(self, send_f=True, raise_if_not_found=True):
        """走到宝箱前并（可选）打开它"""
        if not self.walk_to_box(self.find_treasure_icon, end_condition=self.find_f_with_text):
            raise Exception(f'can not walk to treasure!')
        if send_f:
            self.walk_until_f(time_out=2, backward_time=0, raise_if_not_found=raise_if_not_found)
        self.sleep(1)

    def yolo_find_echo(self, use_color=False, turn=True, update_function=None, time_out=8, threshold=0.5):
        """
        寻找声骸的高级逻辑：
        1. 尝试直接拾取。
        2. 如果没找到，旋转视角 (turn) 并在四周寻找。
        3. 找到后走过去。
        """
        # if self.debug:
        #     self.screenshot('yolo_echo_start')
        max_echo_count = 0
        if self.pick_echo():
            self.sleep(0.5)
            return True, True
        front_box = self.box_of_screen(0.35, 0.35, 0.65, 0.53, hcenter=True)
        color_threshold = 0.02
        
        # 旋转 4 次，覆盖 360 度
        for i in range(4):
            if turn:
                self.center_camera() # 视角归中
            echos = self.find_echos(threshold=threshold)
            max_echo_count = max(max_echo_count, len(echos))
            self.log_debug(f'max_echo_count {max_echo_count}')
            if echos:
                self.log_info(f'yolo found echo {echos}')
                # 找到后走过去
                return self.walk_to_yolo_echo(update_function=update_function, time_out=time_out), max_echo_count > 1
            
            # (可选) 颜色识别作为兜底
            if use_color:
                color_percent = self.calculate_color_percentage(echo_color, front_box)
                self.log_debug(f'pick_echo color_percent:{color_percent}')
                if color_percent > color_threshold:
                    self.log_debug(f'found color_percent {color_percent} > {color_threshold}, walk now')
                    return self.walk_to_yolo_echo(update_function=update_function), max_echo_count > 1
            if not turn and i == 0:
                return False, max_echo_count > 1
            self.send_key('a', down_time=0.05) # 稍微转一点
            self.sleep(0.5)

        self.center_camera()
        return False, max_echo_count > 1

    def center_camera(self):
        """按下鼠标中键，重置视角朝向"""
        self.click(0.5, 0.5, down_time=0.2, key='middle')
        self.wait_until(self.in_combat, time_out=1)

    def turn_direction(self, direction):
        """转向特定方向 ('w', 'a', 's', 'd')"""
        if direction != 'w':
            self.send_key(direction, down_time=0.05, after_sleep=0.5)
        self.center_camera()

    def walk_find_echo(self, backward_time=1, time_out=3):
        """
        盲走寻找声骸模式：向前走并不断尝试按F。
        """
        if self.walk_until_f(time_out=time_out, backward_time=backward_time, target_text=self.absorb_echo_text(),
                             raise_if_not_found=False, check_combat=True):  # find and pick echo
            logger.debug(f'farm echo found echo move forward walk_until_f to find echo')
            return self.pick_f()

    def incr_drop(self, dropped):
        """统计掉落数和效率 (声骸/小时)"""
        if dropped:
            self.info['Echo Count'] = self.info.get('Echo Count', 0) + 1
            self.info['Echo per Hour'] = round(
                self.info.get('Echo Count', 0) / max(time.time() - self.start_time, 1) * 3600)

    def should_check_monthly_card(self):
        if self.next_monthly_card_start > 0:
            if 0 < time.time() - self.next_monthly_card_start < 120:
                return True
        return False

    def sleep(self, timeout):
        """
        重写的 sleep 方法。
        在 sleep 的同时，会检查是否到了每日刷新时间（月卡弹窗检查）。
        """
        return super().sleep(timeout - self.check_for_monthly_card())

    def wait_in_team_and_world(self, time_out=10, raise_if_not_found=True, esc=False):
        """等待直到进入游戏世界且队伍可见"""
        success = self.wait_until(self.in_team_and_world, time_out=time_out, raise_if_not_found=raise_if_not_found,
                                  post_action=lambda: self.back(after_sleep=2) if esc else None)
        if success:
            self.sleep(0.1)
        return success

    def ensure_main(self, esc=True, time_out=30):
        """
        确保当前处于游戏主界面。
        如果不确定，会尝试登录、处理弹窗、按ESC等操作。
        """
        self.info_set('current task', 'wait main')
        if not self.wait_until(lambda: self.is_main(esc=esc), time_out=time_out, raise_if_not_found=False):
            raise Exception('Please start in game world and in team!')
        self.info_set('current task', 'in main')

    def is_main(self, esc=True):
        """检查当前是否为主界面"""
        if self.in_team_and_world():
            self._logged_in = True
            return True
        if self.handle_monthly_card():
            return True
        if self.wait_login():
            return True
        if esc:
            self.back(after_sleep=1.5)

    def wait_login(self):
        """处理登录界面"""
        if not self._logged_in:
            if self.find_one('login_account', vertical_variance=0.1, threshold=0.7):
                self.wait_until(lambda: self.find_one('login_account', threshold=0.7) is None,
                                pre_action=lambda: self.click_relative(0.5, 0.9, after_sleep=3), time_out=30)
                self.wait_until(lambda: self.find_one('monthly_card', threshold=0.7) or self.in_team_and_world(),
                                pre_action=lambda: self.click_relative(0.5, 0.9, after_sleep=3), time_out=120)
                self.wait_until(lambda: self.in_team_and_world(),
                                post_action=lambda: self.click_relative(0.5, 0.9, after_sleep=3), time_out=5)
                self.log_info('Auto Login Success', notify=True)
                self._logged_in = True
                self.sleep(3)
                return True
            if login := self.ocr(0.3, 0.3, 0.7, 0.7, match="登录"):
                self.click(login)
                self.log_info('点击登录按钮!')
                return False

    def in_team_and_world(self):
        """同时检查在队伍中且在大世界（非菜单、非过场动画）"""
        return self.in_team()[
            0]  # and self.find_one(f'gray_book_button', threshold=0.7, canny_lower=50, canny_higher=150)

    def get_angle_between(self, my_angle, angle):
        """计算两个角度之间的差值"""
        if my_angle > angle:
            to_turn = angle - my_angle
        else:
            to_turn = -(my_angle - angle)
        if to_turn > 180:
            to_turn -= 360
        elif to_turn < -180:
            to_turn += 360
        return to_turn

    def get_my_angle(self):
        """获取当前角色在小地图上的朝向角度"""
        return self.rotate_arrow_and_find()[0]

    def rotate_arrow_and_find(self):
        """
        通过旋转小地图箭头模板，匹配当前箭头角度。
        这是判断角色朝向的关键技术。
        """
        arrow_template = self.get_feature_by_name('arrow')
        original_mat = arrow_template.mat
        max_conf = 0
        max_angle = 0
        max_target = None
        max_mat = None
        (h, w) = arrow_template.mat.shape[:2]
        # self.log_debug(f'turn_east h:{h} w:{w}')
        center = (w // 2, h // 2)
        target_box = self.get_box_by_name('arrow')
        # if self.debug:
        #     self.screenshot('arrow_original', original_ mat)
        for angle in range(0, 360):
            # Rotate the template image
            rotation_matrix = cv2.getRotationMatrix2D(center, -angle, 1.0)
            template = cv2.warpAffine(original_mat, rotation_matrix, (w, h))
            # mask = np.where(np.all(template == [0, 0, 0], axis=2), 0, 255).astype(np.uint8)

            target = self.find_one(box=target_box,
                                   template=template, threshold=0.01)
            # if self.debug and angle % 90 == 0:
            #     self.screenshot(f'arrow_rotated_{angle}', arrow_template.mat)
            if target and target.confidence > max_conf:
                max_conf = target.confidence
                max_angle = angle
                max_target = target
                # max_mat = template
        # arrow_template.mat = original_mat
        # arrow_template.mask = None
        # if self.debug and max_mat is not None:
        #     self.screenshot('max_mat',frame=max_mat)
        # self.log_debug(f'turn_east max_conf: {max_conf} {max_angle}')
        return max_angle, max_target

    def get_mini_map_turn_angle(self, feature, threshold=0.72, x_offset=0, y_offset=0):
        """
        在小地图上找到某个目标点，并计算需要转多少角度才能面向它。
        """
        box = self.get_box_by_name('box_minimap')
        target = self.find_one(feature, box=box, threshold=threshold)
        if not target:
            self.log_info(f'Can not find {feature} on minimap')
            return None
        else:
            self.log_debug(f'found {box} on minimap')
        target.x += target.width * x_offset
        target.y += target.height * y_offset
        direction_angle = calculate_angle_clockwise(box, target)
        my_angle = self.get_my_angle()
        to_turn = self.get_angle_between(my_angle, direction_angle)
        self.log_info(f'angle: {my_angle}, to_turn: {to_turn}')
        return to_turn

    def _stop_movement(self, current_direction):
        """Releases keys and mouse to stop character movement."""
        if current_direction is not None:
            self.mouse_up(key='right')
            self.send_key_up(current_direction)

    def _navigate_based_on_angle(self, angle, current_direction, current_adjust):
        """
        Core navigation logic to adjust movement based on a target angle.
        This contains the shared logic from the original functions.

        Returns a tuple: (new_direction, new_adjust, should_continue)
        - new_direction: The updated movement direction ('w', 'a', 's', 'd').
        - new_adjust: The updated adjustment state.
        - should_continue: A boolean indicating if the calling loop should `continue`.
        """
        # 1. Handle minor adjustments if already moving forward
        if current_direction == 'w':
            if 10 <= angle <= 80:
                minor_adjust = 'd'
            elif -80 <= angle <= -10:
                minor_adjust = 'a'
            else:
                minor_adjust = None

            if minor_adjust:
                self.send_key_down(minor_adjust)
                self.sleep(0.1)
                self.middle_click(down_time=0.1)
                self.send_key_up(minor_adjust)
                self.sleep(0.01)
                # Tell the caller to continue to the next loop iteration
                return current_direction, current_adjust, True

        # 2. Clean up any previous adjustments
        if current_adjust:
            self.send_key_up(current_adjust)
            current_adjust = None

        # 3. Determine the major new direction based on the angle
        if -45 <= angle <= 45:
            new_direction = 'w'
        elif 45 < angle <= 135:
            new_direction = 'd'
        elif -135 < angle <= -45:
            new_direction = 'a'
        else:
            new_direction = 's'

        # 4. Change direction if needed
        if current_direction != new_direction:
            self.log_info(f'changed direction {angle} {current_direction} -> {new_direction}')
            if current_direction:
                self.mouse_up(key='right')
                self.send_key_up(current_direction)
                self.wait_until(self.in_combat, time_out=0.2)
            self.turn_direction(new_direction)
            self.send_key_down('w')
            self.wait_until(self.in_combat, time_out=0.2)
            self.mouse_down(key='right')
            current_direction = 'w'  # After turning, we always move forward
            self.wait_until(self.in_combat, time_out=1)

        return current_direction, current_adjust, False

    def in_team(self):
        """
        检测右侧角色头像，判断是否在队伍中。
        Returns: (是否在队, 当前选中的角色索引, 队伍总人数)
        """
        c1 = self.find_one('char_1_text',
                           threshold=0.8)
        c2 = self.find_one('char_2_text',
                           threshold=0.8)
        c3 = self.find_one('char_3_text',
                           threshold=0.8)
        arr = [c1, c2, c3]
        # logger.debug(f'in_team check {arr}')
        current = -1
        exist_count = 0
        for i in range(len(arr)):
            if arr[i] is None:
                if current == -1:
                    current = i
            else:
                exist_count += 1
        if exist_count == 2 or exist_count == 1:
            self._logged_in = True
            return True, current, exist_count + 1
        else:
            return False, -1, exist_count + 1

        # Function to check if a component forms a ring

    def handle_monthly_card(self):
        """处理月卡弹窗的点击逻辑"""
        monthly_card = self.find_one('monthly_card', threshold=0.8)
        # self.screenshot('monthly_card1')
        if monthly_card is not None:
            # self.screenshot('monthly_card1')
            self.click_relative(0.50, 0.89)
            self.sleep(2)
            # self.screenshot('monthly_card2')
            self.click_relative(0.50, 0.89)
            self.sleep(2)
            self.wait_until(self.in_team_and_world, time_out=10,
                            post_action=lambda: self.click_relative(0.50, 0.89, after_sleep=1))
            # self.screenshot('monthly_card3')
            self.set_check_monthly_card(next_day=True)
        logger.debug(f'check_monthly_card {monthly_card}')
        return monthly_card is not None

    @property
    def game_lang(self):
        """通过窗口标题判断游戏语言"""
        if '鸣潮' in self.hwnd_title:
            return 'zh_CN'
        elif 'Wuthering' in self.hwnd_title:
            return 'en_US'
        elif '鳴潮' in self.hwnd_title:
            return 'zh_TW'
        return 'unknown_lang'

    def open_esc_menu(self):
        """打开ESC菜单"""
        self.send_key_down('alt')
        self.sleep(0.05)
        self.click_relative(0.95, 0.04)
        self.send_key_up('alt')
        self.sleep(0.5)

    def openF2Book(self, feature="gray_book_all_monsters", opened=False):
        """
        打开索敌指南/图鉴 (F2)。
        """
        if not opened:
            self.log_info('click f2 to open the book')
            self.send_key_down('alt')
            self.sleep(0.05)
            self.click_relative(0.77, 0.05)
            self.send_key_up('alt')
            self.sleep(1)
        gray_book_boss = self.wait_book(feature)
        if not gray_book_boss:
            self.log_error("can't find gray_book_boss, make sure f2 is the hotkey for book", notify=True)
            raise Exception("can't find gray_book_boss, make sure f2 is the hotkey for book")
        return gray_book_boss

    def click_traval_button(self):
        """点击传送按钮"""
        for feature_name in ['fast_travel_custom', 'gray_teleport', 'remove_custom']:
            if feature := self.find_one(feature_name, threshold=0.7):
                self.sleep(0.5)
                self.click(feature, after_sleep=1)
                if feature.name == 'fast_travel_custom':
                    if confirm := self.wait_feature(
                            ['confirm_btn_hcenter_vcenter', 'confirm_btn_highlight_hcenter_vcenter'],
                            raise_if_not_found=False,
                            threshold=0.6,
                            time_out=2):
                        self.click(0.49, 0.55, after_sleep=0.5)  # 点击不再提醒
                        self.click(confirm, after_sleep=0.5)
                        self.wait_click_feature(
                            ['confirm_btn_hcenter_vcenter', 'confirm_btn_highlight_hcenter_vcenter'],
                            relative_x=-1, raise_if_not_found=False,
                            threshold=0.6,
                            time_out=1)
                return True

    def wait_click_travel(self):
        self.wait_until(self.click_traval_button, raise_if_not_found=True, time_out=10)

    def wait_book(self, feature="gray_book_all_monsters", time_out=3):
        gray_book_boss = self.wait_until(
            lambda: self.find_one(feature, vertical_variance=0.8, horizontal_variance=0.05,
                                  threshold=0.3),
            time_out=time_out, settle_time=1)
        logger.info(f'found gray_book_boss {gray_book_boss}')
        # if self.debug:
        #     self.screenshot(feature)
        return gray_book_boss

    def check_main(self):
        """检查是否在主界面，如果不在尝试退出当前UI"""
        if not self.in_team()[0]:
            self.click_relative(0, 0)
            self.send_key('esc')
            self.sleep(1)
            if not self.in_team()[0]:
                raise Exception('must be in game world and in teams')
        return True

    def click_on_book_target(self, serial_number: int, total_number: int):
        """在图鉴列表中点击特定的BOSS/怪物"""
        double_bar_top = 333 / 1440
        bar_top = 268 / 1440
        bar_bottom = 1259 / 1440
        container_max_rows = 5
        default_container_display = 398 / 992 * 12
        index = serial_number - 1
        if serial_number <= container_max_rows:
            x = 0.88
            y = 0.28
            height = (0.85 - 0.28) / 4
            y += height * index
            self.click_relative(x, y, after_sleep=1)
        else:
            min_width = self.width_of_screen(475 / 2560)
            min_height = self.height_of_screen(40 / 1440)
            double = find_color_rectangles(self.frame, double_drop_color, min_width, min_height,
                                           box=self.box_of_screen(1990 / 2560, 170 / 1440, 2500 / 2560, 245 / 1440))
            if double:
                logger.info(f'double drop!')
                bar_top = double_bar_top
                self.draw_boxes('double_drop', double, color='blue')
            gap_per_index = (bar_bottom - bar_top) / total_number
            y = gap_per_index * (serial_number - container_max_rows + default_container_display) + bar_top
            self.click_relative(0.98, y)
            logger.info(f'scroll to target')
            btns = self.find_feature('boss_proceed', box=self.box_of_screen(0.94, 0.6, 0.97, 0.88), threshold=0.8)
            if btns is None:
                raise Exception("can't find boss_proceed")
            bottom_btn = max(btns, key=lambda box: box.y)
            self.click_box(bottom_btn, after_sleep=1)
        self.wait_feature(['fast_travel_custom', 'gray_teleport', 'remove_custom'], time_out=10, settle_time=0.5)

    def change_time_to_night(self):
        """将游戏时间调整到晚上（如刷某些特定怪物需要）"""
        logger.info('change time to night')
        self.send_key("esc")
        self.sleep(1)
        self.click_relative(0.71, 0.96)
        self.sleep(2)
        self.click_relative(0.19, 0.14)
        self.sleep(1)

        # 调整时间到晚上
        for _ in range(3):
            self.click_relative(0.82, 0.53)
            self.sleep(1)

        self.click_relative(0.52, 0.90)
        self.sleep(6)
        self.send_key("esc")
        self.sleep(1)
        self.send_key("esc")
        self.sleep(1)


double_drop_color = {
    'r': (140, 180),  # Red range
    'g': (120, 160),  # Green range
    'b': (70, 110)  # Blue range
}

echo_color = {
    'r': (200, 255),  # Red range
    'g': (150, 220),  # Green range
    'b': (130, 170)  # Blue range
}


def calculate_angle_clockwise(box1, box2):
    """
    Calculates angle (radians) from horizontal right to line (x1,y1)->(x2,y2).
    Positive clockwise, negative counter-clockwise.
    """
    x1, y1 = box1.center()
    x2, y2 = box2.center()
    dx = x2 - x1
    dy = y2 - y1
    # math.atan2(dy, dx) gives angle from positive x-axis, positive CCW.
    # Negate for positive CW convention.

    degree = math.degrees(math.atan2(dy, dx))
    if degree < 0:
        degree += 360
    return degree


lower_white = np.array([244, 244, 244], dtype=np.uint8)
lower_white_none_inclusive = np.array([243, 243, 243], dtype=np.uint8)
upper_white = np.array([255, 255, 255], dtype=np.uint8)
black = np.array([0, 0, 0], dtype=np.uint8)


def isolate_white_text_to_black(cv_image):
    """
    Converts pixels in the near-white range (244-255) to black,
    and all others to white.
    Args:
        cv_image: Input image (NumPy array, BGR).
    Returns:
        Black and white image (NumPy array), where matches are black.
    """
    match_mask = cv2.inRange(cv_image, black, lower_white_none_inclusive)
    output_image = cv2.cvtColor(match_mask, cv2.COLOR_GRAY2BGR)

    return output_image


def convert_bw(cv_image):
    match_mask = cv2.inRange(cv_image, lower_white, upper_white)
    output_image = cv2.cvtColor(match_mask, cv2.COLOR_GRAY2BGR)
    return output_image


lower_icon_white = np.array([210, 210, 210], dtype=np.uint8)
upper_icon_white = np.array([240, 240, 240], dtype=np.uint8)


def convert_dialog_icon(cv_image):
    match_mask = cv2.inRange(cv_image, lower_icon_white, upper_icon_white)
    output_image = cv2.cvtColor(match_mask, cv2.COLOR_GRAY2BGR)
    return output_image


def binarize_for_matching(image):
    """
    Converts a colored image to a binary image based on a brightness threshold.

    The rule is: pixels with a value of 240-255 become pure white (255),
    and all other pixels become pure black (0).

    Args:
        image (np.array): The input BGR image from OpenCV.

    Returns:
        np.array: The resulting binary image (single channel, 8-bit).
    """
    # Convert the image to grayscale for a single brightness value per pixel.
    # This is more robust than checking individual R, G, B channels.

    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Apply the binary threshold.
    # Pixels > 239 will be set to 255 (white).
    # Pixels <= 239 will be set to 0 (black).
    # cv2.THRESH_BINARY is the type of thresholding we want.
    _, binary_image = cv2.threshold(gray_image, 244, 255, cv2.THRESH_BINARY)
    return binary_image
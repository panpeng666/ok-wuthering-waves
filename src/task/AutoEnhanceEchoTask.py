from qfluentwidgets import FluentIcon

from ok import FindFeature, Logger
from ok import TriggerTask
from src.scene.WWScene import WWScene
from src.task.BaseWWTask import BaseWWTask
from src.echo.profile import EchoProfile, EntryCoef
from src.echo.calculate import calculator
from src.echo.stats import stats_manager
from src.echo.vision import EchoVision
from src.echo.actions import EchoAction

logger = Logger.get_logger(__name__)


class AutoEnhanceEchoTask(TriggerTask, BaseWWTask, FindFeature):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "Auto Enhance Echo"
        self.description = "Intelligently analyze, enhance and tune echoes based on scoring."
        self.icon = FluentIcon.SHOPPING_CART
        self.scene: WWScene | None = None
        self.default_config.update({
            '_enabled': False,
            'Legacy Mode': False
        })
        self.config_description = {
            'Legacy Mode': 'Use the old simple clicker mode (no smart analysis).'
        }

    def run(self):
        # Ensure we are not in the open world combat view (should be in inventory/echo menu)
        if self.scene.in_team(self.in_team_and_world):
            self.log_warning("Please open Echo details panel first (Inventory or Character Menu).")
            return

        if self.config.get('Legacy Mode'):
            self.log_info("Running in Legacy Mode.")
            return self.legacy_run()
        
        self.smart_enhance_run()

    def smart_enhance_run(self):
        vision = EchoVision(self)
        action = EchoAction(self)
        
        # Load user preferences
        target_role = stats_manager.get_user_conf('target_role', 'Default')
        threshold = stats_manager.get_user_conf('threshold', 0.8)
        auto_tune = stats_manager.get_user_conf('auto_tune', True)
        auto_next = stats_manager.get_user_conf('auto_next', False)
        
        coef = EntryCoef(target_role)
        self.log_info(f"Start Smart Enhance. Role: {target_role}, Threshold: {threshold:.2f}")

        # Safety loop limit to prevent infinite loops during testing
        loop_count = 0
        max_loops = 100 

        while loop_count < max_loops:
            loop_count += 1
            
            # 1. Scan
            profile = vision.scan_echo_panel()
            if not profile:
                self.log_warning("Failed to scan echo panel or OCR failed.")
                # If auto_next is on, maybe we should skip? But failing to scan is critical.
                # Let's try to next if enabled, assuming it might be a loading glitch or empty slot
                if auto_next:
                    self.log_info("Attempting to switch to next echo...")
                    action.next_echo()
                    self.sleep(1.5)
                    continue
                else:
                    break
            
            # 2. Evaluate
            current_score = calculator.get_score(profile, coef)
            expected_score = calculator.get_expected_score(profile, coef)
            
            # Estimate max potential score for a fresh echo (level 0)
            # This serves as the denominator for normalization
            max_potential = calculator.get_max_possible_score(EchoProfile(level=0), coef)
            if max_potential <= 0: max_potential = 1.0 # Avoid division by zero
            
            score_ratio = expected_score / max_potential
            
            self.log_info(f"Echo Lv.{profile.level} | Score: {current_score:.1f} | "
                          f"Exp. Score: {expected_score:.1f} ({score_ratio:.1%})")
            
            # 3. Decision
            if score_ratio < threshold:
                self.log_info(f"Decision: TRASH (Ratio {score_ratio:.2f} < {threshold})")
                if auto_next:
                    # TODO: Implement mark_as_trash if possible
                    action.next_echo()
                    self.sleep(1.5)
                    continue
                else:
                    self.log_info("Auto Next is disabled. Stopping.")
                    break
            else:
                self.log_info("Decision: KEEP")
                
                # 4. Action
                if profile.level < 25:
                    # Enhance step by step (e.g., +5 levels)
                    # For now, we assume one enhance action adds 5 levels or uses available mats
                    action.enhance(target_level_step=5)
                    
                    if auto_tune:
                        action.tune()
                    
                    # After enhancement, wait for animation and re-scan
                    self.sleep(2.0) 
                    continue
                else:
                    self.log_info("Echo is max level and meets the threshold.")
                    if auto_next:
                        action.next_echo()
                        self.sleep(1.5)
                        continue
                    else:
                        break
        
        self.log_info("Task finished.")

    # --- Legacy Functions for compatibility ---
    def find_echo_enhance(self):
        return self.find_one('echo_enhance_btn')

    def legacy_run(self):
        if enhance_button := self.scene.echo_enhance_btn(self.find_echo_enhance):
            wait = False
            while self.find_one('echo_enhance_to', horizontal_variance=0.01):
                self.click(enhance_button, after_sleep=0.5)
                wait = True
            if wait:
                handled = self.wait_until(lambda: self.do_handle_pop_up(1), time_out=6)
                if handled == 'exit':
                    return True

            if feature := self.wait_feature('red_dot', time_out=3) if wait else self.find_one('red_dot'):
                self.log_info(f'found red dot feature: {feature}')
                self.click(0.04, 0.29, after_sleep=0.5)
                if enhance_button := self.find_echo_enhance():
                    self.click(enhance_button, after_sleep=1)
                    self.wait_until(lambda: self.do_handle_pop_up(2), time_out=6)
            return True

    def do_handle_pop_up(self, step):
        if btn := self.find_one('echo_enhance_confirm'):
            self.click(btn, after_sleep=1)
        elif feature := self.find_one(['echo_enhance_btn', 'red_dot']):
            self.log_info(f'found do_handle_pop_up: {feature}')
            return 'ok'
        elif self.find_one('echo_merge'):
            return 'exit'
        elif step == 1:
            self.click(0.51, 0.87, after_sleep=0.5)
        else:
            self.click(0.04, 0.16, after_sleep=0.5)
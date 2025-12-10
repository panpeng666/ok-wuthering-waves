import math
from typing import Dict, List, Tuple
from collections import defaultdict
from itertools import combinations

from src.echo.stats import stats_manager
from src.echo.profile import EchoProfile, EntryCoef

class Calculator:
    def __init__(self):
        self.stats = stats_manager

    def get_score(self, profile: EchoProfile, coef: EntryCoef) -> float:
        """计算当前声骸的评分"""
        total_score = 0.0
        # 遍历 coef 中的所有属性权重
        for key, weight in coef.__dict__.items():
            if weight > 0 and hasattr(profile, key):
                value = getattr(profile, key)
                total_score += value * weight
        return total_score

    def get_max_possible_score(self, profile: EchoProfile, coef: EntryCoef) -> float:
        """计算当前状态下理论最大得分"""
        current_score = self.get_score(profile, coef)
        
        # 统计已有的副词条
        existing_sub_stats = []
        for key in self.stats.get_all_keys():
            if getattr(profile, key) > 0:
                existing_sub_stats.append(key)
        
        remaining_slots = 5 - len(existing_sub_stats)
        if remaining_slots <= 0:
            return current_score

        # 找出剩余可用的属性
        available_stats = []
        for key in self.stats.get_all_keys():
            if key not in existing_sub_stats:
                # 获取该属性的最大可能值
                dist = self.stats.get_distribution(key)
                if dist:
                    max_val = max(d['value'] for d in dist)
                    weight = getattr(coef, key, 0)
                    available_stats.append(max_val * weight)
        
        # 贪心选取收益最高的属性
        available_stats.sort(reverse=True)
        max_future_score = sum(available_stats[:remaining_slots])
        
        return current_score + max_future_score

    def prob_above_score(self, profile: EchoProfile, coef: EntryCoef, threshold: float) -> float:
        """
        计算声骸强化到满级后，评分超过阈值的概率。
        
        算法思路：
        1. 确定当前已有的属性和得分。
        2. 确定剩余槽位数 k 和可用属性池 pool。
        3. 遍历从 pool 中选取 k 个属性的所有组合。
        4. 对于每种属性组合，通过卷积计算其加权得分分布。
        5. 累加每种组合下超过阈值的概率。
        """
        # 1. 基础信息
        current_score = self.get_score(profile, coef)
        needed_score = threshold - current_score
        
        if needed_score <= 0:
            return 1.0

        existing_sub_stats = set()
        for key in self.stats.get_all_keys():
            if getattr(profile, key) > 0:
                existing_sub_stats.add(key)
        
        k = 5 - len(existing_sub_stats)
        if k <= 0:
            return 0.0 if needed_score > 0 else 1.0

        all_keys = set(self.stats.get_all_keys())
        pool = list(all_keys - existing_sub_stats)
        
        if len(pool) < k:
            # 理论上不会发生，除非配置文件有问题
            return 0.0

        # 2. 遍历所有可能的属性组合
        # 假设从属性池中抽取每个属性的概率是均等的（这是目前对游戏机制的通用假设）
        # 组合数 C(N, k)
        comb_iter = combinations(pool, k)
        
        total_valid_prob = 0.0
        total_combinations = math.comb(len(pool), k)
        
        # 预计算每个属性的得分分布 {score: probability}
        # 仅计算权重 > 0 的属性，权重为 0 的属性得分恒为 0
        attr_score_dists = {}
        for key in pool:
            weight = getattr(coef, key, 0)
            dist_list = self.stats.get_distribution(key)
            # {score: prob}
            score_dist = defaultdict(float)
            if weight == 0:
                score_dist[0.0] = 1.0
            else:
                for item in dist_list:
                    score = item['value'] * weight
                    prob = item['probability']
                    score_dist[score] += prob
            attr_score_dists[key] = score_dist

        # 3. 对每个组合进行计算
        for attrs_combo in comb_iter:
            # 初始化总分布：得分 0 的概率为 1
            current_combo_dist = {0.0: 1.0}
            
            # 逐步卷积
            for attr in attrs_combo:
                attr_dist = attr_score_dists[attr]
                new_dist = defaultdict(float)
                
                for s1, p1 in current_combo_dist.items():
                    for s2, p2 in attr_dist.items():
                        new_dist[s1 + s2] += p1 * p2
                
                current_combo_dist = new_dist
            
            # 统计当前组合下，得分 >= needed_score 的概率
            prob_ge = sum(p for s, p in current_combo_dist.items() if s >= needed_score - 1e-9) # 浮点误差处理
            
            total_valid_prob += prob_ge

        # 4. 平均概率
        return total_valid_prob / total_combinations

    def get_expected_score(self, profile: EchoProfile, coef: EntryCoef) -> float:
        """计算期望得分（简化版，仅计算平均期望）"""
        current_score = self.get_score(profile, coef)
        
        existing_sub_stats = set()
        for key in self.stats.get_all_keys():
            if getattr(profile, key) > 0:
                existing_sub_stats.add(key)
        
        k = 5 - len(existing_sub_stats)
        if k <= 0:
            return current_score
            
        all_keys = set(self.stats.get_all_keys())
        pool = list(all_keys - existing_sub_stats)
        
        # 计算池中剩余属性的平均期望得分
        # 期望 = Sum(属性i的平均值 * 权重i) / 属性总数
        pool_expected_sum = 0.0
        for key in pool:
            weight = getattr(coef, key, 0)
            if weight == 0:
                continue
            
            dist = self.stats.get_distribution(key)
            avg_val = sum(d['value'] * d['probability'] for d in dist)
            pool_expected_sum += avg_val * weight
            
        avg_expected_per_slot = pool_expected_sum / len(pool)
        
        return current_score + avg_expected_per_slot * k

# 全局单例
calculator = Calculator()

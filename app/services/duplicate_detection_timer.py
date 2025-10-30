"""
重复检测时间预估和倒计时服务
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from sqlalchemy.orm import Session
import threading
import statistics

from app.db.session import SessionLocal
from app.models.digest import Digest
from app.models.news import News
from app.models.duplicate_detection import DuplicateDetectionResult, DuplicateDetectionStatus
from app.services.duplicate_detector import DuplicateDetectorService
from app.config import get_logger

logger = get_logger(__name__)


@dataclass
class TimingRecord:
    """单次LLM调用的时间记录"""
    duration: float  # 秒
    timestamp: datetime
    model: str
    success: bool


@dataclass
class EstimationResult:
    """预估结果"""
    total_comparisons: int  # 总比较次数
    estimated_duration: float  # 预估总时间（秒）
    avg_llm_call_time: float  # 平均LLM调用时间
    current_news_count: int  # 当前新闻数量
    reference_news_count: int  # 参考新闻数量
    buffer_factor: float  # 缓冲因子
    estimated_completion_time: Optional[datetime] = None  # 预计完成时间


@dataclass
class ProgressInfo:
    """进度信息"""
    completed_comparisons: int  # 已完成比较次数
    total_comparisons: int  # 总比较次数
    elapsed_time: float  # 已消耗时间（秒）
    estimated_remaining_time: float  # 预计剩余时间（秒）
    current_progress: float  # 当前进度百分比
    estimated_completion_time: Optional[datetime] = None  # 预计完成时间


class DuplicateDetectionTimer:
    """重复检测时间预估和倒计时服务"""

    def __init__(self):
        self.timing_records: List[TimingRecord] = []
        self.max_records = 100  # 最多保存100条记录
        self.detector_service = DuplicateDetectorService()
        self.lock = threading.Lock()

        # 默认配置
        self.default_llm_call_time = 3.0  # 默认LLM调用时间（秒）
        self.buffer_factor = 1.3  # 缓冲因子，增加30%时间
        self.network_delay = 0.5  # 网络延迟（秒）

    def add_timing_record(self, duration: float, model: str, success: bool = True):
        """添加时间记录"""
        with self.lock:
            record = TimingRecord(
                duration=duration,
                timestamp=datetime.now(),
                model=model,
                success=success
            )
            self.timing_records.append(record)

            # 保持记录数量在限制范围内
            if len(self.timing_records) > self.max_records:
                self.timing_records = self.timing_records[-self.max_records:]

            logger.debug(f"添加时间记录: {duration:.2f}s, 模型: {model}, 成功: {success}")

    def get_average_llm_call_time(self, model: Optional[str] = None, recent_hours: int = 24) -> float:
        """获取平均LLM调用时间"""
        with self.lock:
            # 筛选有效记录
            cutoff_time = datetime.now() - timedelta(hours=recent_hours)
            valid_records = [
                record for record in self.timing_records
                if record.success and record.timestamp > cutoff_time
            ]

            # 按模型筛选
            if model:
                valid_records = [r for r in valid_records if r.model == model]

            if not valid_records:
                logger.info(f"没有找到有效的时间记录，使用默认值 {self.default_llm_call_time}s")
                return self.default_llm_call_time

            # 计算平均值，移除异常值
            durations = [r.duration for r in valid_records]

            if len(durations) >= 3:
                # 移除最高和最低的20%
                durations.sort()
                trim_count = max(1, len(durations) // 5)
                durations = durations[trim_count:-trim_count]

            avg_time = statistics.mean(durations)
            logger.info(f"计算平均LLM调用时间: {avg_time:.2f}s (基于 {len(durations)} 条记录)")
            return avg_time

    def estimate_detection_time(self, digest_id: int, db: Session) -> EstimationResult:
        """估计重复检测所需时间"""
        # 获取当前快报
        digest = db.query(Digest).filter(Digest.id == digest_id).first()
        if not digest:
            raise ValueError(f"快报 {digest_id} 不存在")

        # 获取当前快报的新闻数量
        current_news_count = len(digest.news_items)
        if current_news_count == 0:
            return EstimationResult(
                total_comparisons=0,
                estimated_duration=0,
                avg_llm_call_time=0,
                current_news_count=0,
                reference_news_count=0,
                buffer_factor=1.0
            )

        # 获取参考新闻数量
        reference_digests = self.detector_service.get_last_three_days_digests(db, digest_id)
        reference_news_list = self.detector_service.collect_reference_news(reference_digests)
        reference_news_count = len(reference_news_list)

        # 计算总比较次数
        total_comparisons = current_news_count * reference_news_count

        # 获取平均LLM调用时间
        model = self.detector_service.model
        avg_llm_call_time = self.get_average_llm_call_time(model)

        # 预估总时间 = (平均调用时间 + 网络延迟) × 比较次数 × 缓冲因子
        base_time = (avg_llm_call_time + self.network_delay) * total_comparisons
        estimated_duration = base_time * self.buffer_factor

        # 预计完成时间
        estimated_completion_time = datetime.now() + timedelta(seconds=estimated_duration)

        result = EstimationResult(
            total_comparisons=total_comparisons,
            estimated_duration=estimated_duration,
            avg_llm_call_time=avg_llm_call_time,
            current_news_count=current_news_count,
            reference_news_count=reference_news_count,
            buffer_factor=self.buffer_factor,
            estimated_completion_time=estimated_completion_time
        )

        logger.info(f"预估结果 - 快报: {digest_id}, 当前新闻: {current_news_count}, "
                   f"参考新闻: {reference_news_count}, 总比较: {total_comparisons}, "
                   f"预估时间: {estimated_duration:.1f}s ({estimated_duration/60:.1f}分钟)")

        return result

    def get_current_progress(self, digest_id: int, db: Session, start_time: Optional[datetime] = None) -> ProgressInfo:
        """获取当前检测进度"""
        # 获取检测结果
        detection_results = db.query(DuplicateDetectionResult).filter(
            DuplicateDetectionResult.digest_id == digest_id
        ).all()

        if not detection_results:
            return ProgressInfo(
                completed_comparisons=0,
                total_comparisons=0,
                elapsed_time=0,
                estimated_remaining_time=0,
                current_progress=0
            )

        # 获取参考新闻数量来计算实际比较次数
        reference_digests = self.detector_service.get_last_three_days_digests(db, digest_id)
        reference_news_list = self.detector_service.collect_reference_news(reference_digests)
        reference_news_count = len(reference_news_list)
        
        # 计算已完成的新闻数量
        completed_news_count = sum(1 for result in detection_results
                                 if result.status in [
                                     DuplicateDetectionStatus.DUPLICATE.value,
                                     DuplicateDetectionStatus.NO_DUPLICATE.value,
                                     DuplicateDetectionStatus.ERROR.value
                                 ])

        total_news_count = len(detection_results)

        # 计算实际的比较次数 (每条新闻 × 参考新闻数量)
        completed_comparisons = completed_news_count * reference_news_count
        total_comparisons = total_news_count * reference_news_count

        # 计算进度百分比
        current_progress = (completed_comparisons / total_comparisons * 100) if total_comparisons > 0 else 0

        # 计算已消耗时间
        elapsed_time = 0
        if start_time:
            elapsed_time = (datetime.now() - start_time).total_seconds()
        else:
            # 使用最早的检测记录时间作为开始时间
            earliest_record = min(detection_results, key=lambda x: x.created_at, default=None)
            if earliest_record:
                elapsed_time = (datetime.now() - earliest_record.created_at).total_seconds()

        # 预估剩余时间
        estimated_remaining_time = 0
        if completed_comparisons > 0 and current_progress < 100:
            avg_time_per_comparison = elapsed_time / completed_comparisons
            remaining_comparisons = total_comparisons - completed_comparisons
            estimated_remaining_time = avg_time_per_comparison * remaining_comparisons

        # 预计完成时间
        estimated_completion_time = None
        if estimated_remaining_time > 0:
            estimated_completion_time = datetime.now() + timedelta(seconds=estimated_remaining_time)

        progress_info = ProgressInfo(
            completed_comparisons=completed_comparisons,
            total_comparisons=total_comparisons,
            elapsed_time=elapsed_time,
            estimated_remaining_time=estimated_remaining_time,
            current_progress=current_progress,
            estimated_completion_time=estimated_completion_time
        )

        logger.debug(f"进度信息 - 快报: {digest_id}, 完成新闻: {completed_news_count}/{total_news_count}, "
                    f"完成比较: {completed_comparisons}/{total_comparisons}, "
                    f"进度: {current_progress:.1f}%, 剩余时间: {estimated_remaining_time:.1f}s")

        return progress_info

    def create_simulation_data(self, current_news_count: int, reference_news_count: int) -> List[TimingRecord]:
        """创建模拟数据用于测试"""
        import random

        simulation_data = []
        base_time = self.default_llm_call_time

        for i in range(min(50, current_news_count * reference_news_count)):
            # 模拟一些变化：80%的调用在平均时间的±50%范围内
            if random.random() < 0.8:
                duration = base_time * (0.5 + random.random())  # 0.5x - 1.5x
            else:
                # 20%的调用可能需要更长时间
                duration = base_time * (1.5 + random.random() * 2)  # 1.5x - 3.5x

            # 5%的调用失败
            success = random.random() > 0.05

            record = TimingRecord(
                duration=duration,
                timestamp=datetime.now() - timedelta(minutes=random.randint(1, 1440)),
                model="ark-deepseek-r1-250528",
                success=success
            )
            simulation_data.append(record)

        return simulation_data

    def load_simulation_data(self, current_news_count: int, reference_news_count: int):
        """加载模拟数据"""
        with self.lock:
            simulation_data = self.create_simulation_data(current_news_count, reference_news_count)
            self.timing_records.extend(simulation_data)
            logger.info(f"加载了 {len(simulation_data)} 条模拟时间记录")

    def clear_timing_records(self):
        """清空时间记录"""
        with self.lock:
            self.timing_records.clear()
            logger.info("已清空所有时间记录")

    def get_timing_statistics(self) -> Dict:
        """获取时间统计信息"""
        with self.lock:
            if not self.timing_records:
                return {
                    "total_records": 0,
                    "successful_records": 0,
                    "failed_records": 0,
                    "average_duration": 0,
                    "median_duration": 0,
                    "min_duration": 0,
                    "max_duration": 0
                }

            successful_records = [r for r in self.timing_records if r.success]
            durations = [r.duration for r in successful_records]

            stats = {
                "total_records": len(self.timing_records),
                "successful_records": len(successful_records),
                "failed_records": len(self.timing_records) - len(successful_records),
                "average_duration": statistics.mean(durations) if durations else 0,
                "median_duration": statistics.median(durations) if durations else 0,
                "min_duration": min(durations) if durations else 0,
                "max_duration": max(durations) if durations else 0
            }

            return stats


# 全局实例
detection_timer = DuplicateDetectionTimer()
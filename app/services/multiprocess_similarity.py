"""
多进程相似度计算服务
使用多进程并行计算新闻相似度，显著提升计算性能
"""

import logging
import multiprocessing as mp
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import os
import json
from concurrent.futures import ProcessPoolExecutor
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker

from app.models.news import News
from app.models.news_similarity import NewsSimilarity
from app.services.news_similarity import NewsSimilarityService
from app.db.session import SQLALCHEMY_DATABASE_URL

logger = logging.getLogger(__name__)


def calculate_similarity_batch(batch_data: Dict) -> List[Dict]:
    """
    计算一批新闻对的相似度（子进程执行）
    
    Args:
        batch_data: 包含新闻对信息和配置的字典
        
    Returns:
        相似度结果列表
    """
    try:
        # 在子进程中创建独立的数据库连接
        engine = create_engine(batch_data['database_url'])
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()
        
        # 创建相似度服务实例
        similarity_service = NewsSimilarityService()
        
        news_pairs = batch_data['news_pairs']
        results = []
        
        # 获取这一批次需要的所有新闻对象
        news_ids = set()
        for news_id_1, news_id_2 in news_pairs:
            news_ids.add(news_id_1)
            news_ids.add(news_id_2)
        
        # 批量查询新闻对象（减少数据库查询次数）
        news_objects = db.query(News).filter(News.id.in_(list(news_ids))).all()
        news_dict = {news.id: news for news in news_objects}
        
        logger.info(f"子进程 {os.getpid()} 开始处理 {len(news_pairs)} 个新闻对")
        
        for i, (news_id_1, news_id_2) in enumerate(news_pairs):
            try:
                news1 = news_dict.get(news_id_1)
                news2 = news_dict.get(news_id_2)
                
                if not news1 or not news2:
                    continue
                
                # 时间预筛选：只对72小时内的新闻进行比较
                time_diff = abs((news1.created_at - news2.created_at).total_seconds())
                if time_diff > 72 * 3600:
                    continue
                
                # 计算相似度
                similarity_score = similarity_service.calculate_overall_similarity(news1, news2)
                
                # 只保存有意义的相似度（阈值0.3以上）
                if similarity_score >= 0.3:
                    # 计算细分相似度
                    entities1 = similarity_service.extract_key_entities(news1)
                    entities2 = similarity_service.extract_key_entities(news2)
                    entity_similarity = similarity_service.calculate_entity_similarity(entities1, entities2)
                    
                    title1 = news1.generated_title or news1.title
                    title2 = news2.generated_title or news2.title
                    text_similarity = similarity_service.calculate_text_similarity(title1, title2)
                    
                    result = {
                        'news_id_1': news_id_1,
                        'news_id_2': news_id_2,
                        'similarity_score': similarity_score,
                        'entity_similarity': entity_similarity,
                        'text_similarity': text_similarity,
                        'is_same_event': similarity_score >= similarity_service.SIMILARITY_THRESHOLD,
                        'calculation_version': 'v1.0'
                    }
                    results.append(result)
                
            except Exception as e:
                logger.error(f"子进程 {os.getpid()} 计算新闻对 ({news_id_1}, {news_id_2}) 相似度时出错: {str(e)}")
                continue
        
        db.close()
        logger.info(f"子进程 {os.getpid()} 完成处理，生成 {len(results)} 个相似度记录")
        return results
        
    except Exception as e:
        logger.error(f"子进程 {os.getpid()} 执行失败: {str(e)}")
        return []


class MultiprocessSimilarityService:
    """多进程相似度计算服务"""
    
    def __init__(self, max_workers: int = None):
        """
        初始化多进程相似度计算服务
        
        Args:
            max_workers: 最大工作进程数，默认为CPU核心数
        """
        self.max_workers = max_workers or min(mp.cpu_count(), 8)  # 最多使用8个进程
        self.batch_size = 100  # 每个批次处理的新闻对数量
        
        logger.info(f"初始化多进程相似度服务，使用 {self.max_workers} 个工作进程")
    
    def compute_and_store_similarities_parallel(self, db: Session, hours: int = 48, 
                                              force_recalculate: bool = False,
                                              progress_callback: callable = None) -> Dict:
        """
        并行计算并存储新闻相似度
        
        Args:
            db: 数据库会话
            hours: 计算最近多少小时的新闻
            force_recalculate: 是否强制重新计算已存在的相似度
            progress_callback: 进度回调函数
            
        Returns:
            计算结果统计
        """
        logger.info(f"开始并行计算最近{hours}小时的新闻相似度，使用 {self.max_workers} 个进程")
        start_time = datetime.now()
        
        # 1. 获取需要处理的新闻
        time_threshold = datetime.now() - timedelta(hours=hours)
        news_list = db.query(News).filter(
            News.created_at >= time_threshold,
            News.is_processed == True
        ).order_by(News.created_at.desc()).all()
        
        if not news_list:
            logger.info("没有找到需要处理的新闻")
            return {"total_news": 0, "total_pairs": 0, "new_similarities": 0, "execution_time": 0}
        
        logger.info(f"找到 {len(news_list)} 条新闻需要处理")
        
        # 2. 清理旧记录（如果强制重新计算）
        if force_recalculate:
            news_ids = [news.id for news in news_list]
            deleted_count = db.query(NewsSimilarity).filter(
                or_(
                    NewsSimilarity.news_id_1.in_(news_ids),
                    NewsSimilarity.news_id_2.in_(news_ids)
                )
            ).delete(synchronize_session=False)
            db.commit()
            logger.info(f"已清理 {deleted_count} 条旧的相似度记录")
        
        # 3. 获取已存在的相似度记录
        existing_pairs = set()
        if not force_recalculate:
            existing_records = db.query(NewsSimilarity).filter(
                or_(
                    NewsSimilarity.news_id_1.in_([news.id for news in news_list]),
                    NewsSimilarity.news_id_2.in_([news.id for news in news_list])
                )
            ).all()
            
            for record in existing_records:
                pair = tuple(sorted([record.news_id_1, record.news_id_2]))
                existing_pairs.add(pair)
            
            logger.info(f"找到 {len(existing_pairs)} 个已存在的相似度记录")
        
        # 4. 生成需要计算的新闻对
        news_pairs = []
        n = len(news_list)
        total_theoretical_pairs = n * (n - 1) // 2
        
        for i, news1 in enumerate(news_list):
            for j, news2 in enumerate(news_list[i+1:], i+1):
                # 确保较小的ID在前面
                news_id_1, news_id_2 = sorted([news1.id, news2.id])
                pair = (news_id_1, news_id_2)
                
                # 跳过已存在的记录
                if pair not in existing_pairs:
                    news_pairs.append(pair)
        
        if not news_pairs:
            logger.info("没有新的新闻对需要计算")
            return {
                "total_news": len(news_list),
                "total_pairs": total_theoretical_pairs,
                "new_similarities": 0,
                "execution_time": (datetime.now() - start_time).total_seconds()
            }
        
        logger.info(f"需要计算 {len(news_pairs)} 个新闻对（共 {total_theoretical_pairs} 对）")
        
        # 5. 将新闻对分割成批次
        batches = []
        for i in range(0, len(news_pairs), self.batch_size):
            batch_pairs = news_pairs[i:i + self.batch_size]
            batch_data = {
                'news_pairs': batch_pairs,
                'database_url': SQLALCHEMY_DATABASE_URL,
                'batch_id': i // self.batch_size
            }
            batches.append(batch_data)
        
        logger.info(f"分割成 {len(batches)} 个批次，每批次最多 {self.batch_size} 个新闻对")
        
        # 6. 并行执行批次计算
        all_results = []
        processed_pairs = 0
        
        try:
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                # 提交所有批次任务
                future_to_batch = {
                    executor.submit(calculate_similarity_batch, batch_data): i 
                    for i, batch_data in enumerate(batches)
                }
                
                # 收集结果
                for future in future_to_batch:
                    try:
                        batch_id = future_to_batch[future]
                        batch_results = future.result(timeout=300)  # 5分钟超时
                        all_results.extend(batch_results)
                        
                        # 更新进度
                        processed_pairs += len(batches[batch_id]['news_pairs'])
                        if progress_callback:
                            progress_callback(
                                f"并行计算相似度 ({processed_pairs}/{len(news_pairs)})", 
                                processed_pairs, 
                                len(news_pairs),
                                {
                                    'completed_batches': batch_id + 1,
                                    'total_batches': len(batches),
                                    'calculated_similarities': len(all_results),
                                    'workers': self.max_workers
                                }
                            )
                        
                        logger.info(f"批次 {batch_id + 1}/{len(batches)} 完成，本批次生成 {len(batch_results)} 个相似度记录")
                        
                    except Exception as e:
                        logger.error(f"批次 {future_to_batch[future]} 执行失败: {str(e)}")
                        continue
        
        except Exception as e:
            logger.error(f"并行计算过程中出错: {str(e)}")
            return {
                "total_news": len(news_list),
                "total_pairs": total_theoretical_pairs,
                "new_similarities": 0,
                "execution_time": (datetime.now() - start_time).total_seconds(),
                "error": str(e)
            }
        
        # 7. 批量保存结果到数据库
        if all_results:
            logger.info(f"开始保存 {len(all_results)} 个相似度记录到数据库")
            
            # 转换为SQLAlchemy对象
            similarity_objects = []
            for result in all_results:
                similarity_objects.append(NewsSimilarity(**result))
            
            # 批量插入
            try:
                db.bulk_save_objects(similarity_objects)
                db.commit()
                logger.info(f"成功保存 {len(similarity_objects)} 个相似度记录")
            except Exception as e:
                logger.error(f"保存相似度记录时出错: {str(e)}")
                db.rollback()
                return {
                    "total_news": len(news_list),
                    "total_pairs": total_theoretical_pairs,
                    "new_similarities": 0,
                    "execution_time": (datetime.now() - start_time).total_seconds(),
                    "error": f"数据库保存失败: {str(e)}"
                }
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        result = {
            "total_news": len(news_list),
            "total_pairs": total_theoretical_pairs,
            "processed_pairs": len(news_pairs),
            "new_similarities": len(all_results),
            "execution_time": execution_time,
            "workers_used": self.max_workers,
            "batches_processed": len(batches)
        }
        
        logger.info(f"并行相似度计算完成: {result}")
        return result


# 全局实例
multiprocess_similarity_service = MultiprocessSimilarityService() 
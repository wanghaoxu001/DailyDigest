"""
新闻相似度存储服务
负责管理预计算的文章相似关系，提高前端响应速度
"""

import logging
import json
from typing import List, Dict, Set, Tuple, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from app.models.news import News
from app.models.news_similarity import NewsSimilarity, NewsEventGroup, NewsGroupMembership
from app.services.news_similarity import NewsSimilarityService
from app.services.multiprocess_similarity import multiprocess_similarity_service

logger = logging.getLogger(__name__)


class NewsSimilarityStorageService:
    """新闻相似度存储服务"""
    
    def __init__(self):
        self.similarity_service = NewsSimilarityService()
        self.calculation_version = "v1.0"
        
    def compute_and_store_similarities(self, db: Session, hours: int = 48, force_recalculate: bool = False, 
                                     progress_callback: callable = None, use_multiprocess: bool = True) -> Dict:
        """
        计算并存储新闻相似度
        
        Args:
            db: 数据库会话
            hours: 计算最近多少小时的新闻
            force_recalculate: 是否强制重新计算已存在的相似度
            progress_callback: 进度回调函数
            use_multiprocess: 是否使用多进程计算（默认True）
            
        Returns:
            计算结果统计
        """
        # 根据参数选择计算方式
        if use_multiprocess:
            logger.info(f"开始并行计算并存储最近{hours}小时的新闻相似度")
            return multiprocess_similarity_service.compute_and_store_similarities_parallel(
                db=db,
                hours=hours,
                force_recalculate=force_recalculate,
                progress_callback=progress_callback
            )
        
        # 单进程计算（保留原有逻辑作为备选）
        logger.info(f"开始单进程计算并存储最近{hours}小时的新闻相似度")
        start_time = datetime.now()
        
        # 获取最近的已处理新闻
        time_threshold = datetime.now() - timedelta(hours=hours)
        news_list = db.query(News).filter(
            News.created_at >= time_threshold,
            News.is_processed == True
        ).order_by(News.created_at.desc()).all()
        
        if not news_list:
            logger.info("没有找到需要处理的新闻")
            return {"total_news": 0, "total_pairs": 0, "new_similarities": 0, "execution_time": 0}
        
        logger.info(f"找到 {len(news_list)} 条新闻需要处理")
        
        # 清理旧的相似度记录（如果强制重新计算）
        if force_recalculate:
            news_ids = [news.id for news in news_list]
            db.query(NewsSimilarity).filter(
                or_(
                    NewsSimilarity.news_id_1.in_(news_ids),
                    NewsSimilarity.news_id_2.in_(news_ids)
                )
            ).delete(synchronize_session=False)
            db.commit()
            logger.info("已清理旧的相似度记录")
        
        # 获取已存在的相似度记录
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
        
        # 预计算总的文章对数
        n = len(news_list)
        total_theoretical_pairs = n * (n - 1) // 2
        logger.info(f"总共需要处理 {total_theoretical_pairs} 个文章对")
        
        # 计算新的相似度
        new_similarities = []
        processed_pairs = 0
        calculated_pairs = 0
        skipped_pairs = 0
        
        for i, news1 in enumerate(news_list):
            for j, news2 in enumerate(news_list[i+1:], i+1):
                processed_pairs += 1
                
                # 更新进度
                if progress_callback and processed_pairs % 100 == 0:  # 每100对更新一次进度
                    progress_callback(f"正在计算相似度 ({processed_pairs}/{total_theoretical_pairs})", 
                                    processed_pairs, total_theoretical_pairs, {
                                        'calculated_pairs': calculated_pairs,
                                        'skipped_pairs': skipped_pairs,
                                        'current_news1': news1.generated_title or news1.title[:50],
                                        'current_news2': news2.generated_title or news2.title[:50]
                                    })
                
                # 确保较小的ID在前面
                news_id_1, news_id_2 = sorted([news1.id, news2.id])
                pair = (news_id_1, news_id_2)
                
                # 跳过已存在的记录
                if pair in existing_pairs:
                    skipped_pairs += 1
                    continue
                
                # 时间预筛选：只对72小时内的新闻进行比较
                time_diff = abs((news1.created_at - news2.created_at).total_seconds())
                if time_diff > 72 * 3600:
                    skipped_pairs += 1
                    continue
                
                # 计算相似度
                try:
                    similarity_score = self.similarity_service.calculate_overall_similarity(news1, news2)
                    
                    # 计算细分相似度
                    entities1 = self.similarity_service.extract_key_entities(news1)
                    entities2 = self.similarity_service.extract_key_entities(news2)
                    entity_similarity = self.similarity_service.calculate_entity_similarity(entities1, entities2)
                    
                    title1 = news1.generated_title or news1.title
                    title2 = news2.generated_title or news2.title
                    text_similarity = self.similarity_service.calculate_text_similarity(title1, title2)
                    
                    # 只存储有意义的相似度（阈值0.3以上）
                    if similarity_score >= 0.3:
                        new_similarities.append(NewsSimilarity(
                            news_id_1=news_id_1,
                            news_id_2=news_id_2,
                            similarity_score=similarity_score,
                            entity_similarity=entity_similarity,
                            text_similarity=text_similarity,
                            is_same_event=(similarity_score >= self.similarity_service.SIMILARITY_THRESHOLD),
                            calculation_version=self.calculation_version
                        ))
                    
                    calculated_pairs += 1
                    
                    # 批量插入，避免内存占用过大
                    if len(new_similarities) >= 500:
                        db.bulk_save_objects(new_similarities)
                        db.commit()
                        new_similarities.clear()
                        logger.info(f"已保存一批相似度记录，进度: {processed_pairs}/{total_theoretical_pairs}")
                        
                        # 更新进度到批量保存
                        if progress_callback:
                            progress_callback(f"已保存相似度记录 ({processed_pairs}/{total_theoretical_pairs})", 
                                            processed_pairs, total_theoretical_pairs, {
                                                'calculated_pairs': calculated_pairs,
                                                'skipped_pairs': skipped_pairs,
                                                'saved_similarities': calculated_pairs
                                            })
                
                except Exception as e:
                    logger.error(f"计算新闻 {news1.id} 和 {news2.id} 相似度时出错: {str(e)}")
                    continue
        
        # 保存剩余的相似度记录
        if new_similarities:
            db.bulk_save_objects(new_similarities)
            db.commit()
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        result = {
            "total_news": len(news_list),
            "total_pairs": total_theoretical_pairs,
            "processed_pairs": processed_pairs,
            "calculated_pairs": calculated_pairs,
            "skipped_pairs": skipped_pairs,
            "new_similarities": calculated_pairs,
            "execution_time": execution_time
        }
        
        logger.info(f"相似度计算完成: {result}")
        return result
    
    def compute_and_store_event_groups(self, db: Session, hours: int = 48, force_recalculate: bool = False) -> Dict:
        """
        计算并存储事件分组
        
        Args:
            db: 数据库会话
            hours: 计算最近多少小时的新闻
            force_recalculate: 是否强制重新计算
            
        Returns:
            分组结果统计
        """
        logger.info(f"开始计算并存储最近{hours}小时的事件分组")
        start_time = datetime.now()
        
        # 获取最近的已处理新闻
        time_threshold = datetime.now() - timedelta(hours=hours)
        news_list = db.query(News).filter(
            News.created_at >= time_threshold,
            News.is_processed == True
        ).order_by(News.created_at.desc()).all()
        
        if not news_list:
            logger.info("没有找到需要分组的新闻")
            return {"total_news": 0, "groups_created": 0, "execution_time": 0}
        
        # 清理旧的分组记录（如果强制重新计算）
        if force_recalculate:
            # 清理分组成员关系
            news_ids = [news.id for news in news_list]
            db.query(NewsGroupMembership).filter(
                NewsGroupMembership.news_id.in_(news_ids)
            ).delete(synchronize_session=False)
            
            # 清理空的分组
            orphan_groups = db.query(NewsEventGroup).filter(
                ~NewsEventGroup.group_id.in_(
                    db.query(NewsGroupMembership.group_id).distinct()
                )
            ).all()
            
            for group in orphan_groups:
                db.delete(group)
            
            db.commit()
            logger.info("已清理旧的分组记录")
        
        # 使用相似度记录进行分组
        groups = self._create_groups_from_similarities(db, news_list)
        
        # 存储分组结果
        groups_created = 0
        for group_data in groups:
            try:
                # 创建或更新事件分组
                group_id = group_data['id']
                existing_group = db.query(NewsEventGroup).filter(
                    NewsEventGroup.group_id == group_id
                ).first()
                
                if existing_group and not force_recalculate:
                    continue  # 分组已存在，跳过
                
                if existing_group:
                    # 更新现有分组
                    event_group = existing_group
                else:
                    # 创建新分组
                    event_group = NewsEventGroup(group_id=group_id)
                    db.add(event_group)
                
                # 更新分组信息
                event_group.event_label = group_data['event_label']
                event_group.primary_news_id = group_data['primary'].id
                event_group.news_count = group_data['news_count']
                event_group.sources_count = len(group_data['sources'])
                event_group.key_entities = json.dumps(group_data['entities'], ensure_ascii=False, default=str)
                event_group.similarity_threshold = self.similarity_service.SIMILARITY_THRESHOLD
                event_group.calculation_version = self.calculation_version
                
                # 计算时间范围
                all_news = [group_data['primary']] + group_data.get('related', [])
                event_group.earliest_news_time = min(news.created_at for news in all_news)
                event_group.latest_news_time = max(news.created_at for news in all_news)
                
                # 清理该分组的旧成员关系
                db.query(NewsGroupMembership).filter(
                    NewsGroupMembership.group_id == group_id
                ).delete(synchronize_session=False)
                
                # 添加分组成员关系
                # 主要新闻
                primary_membership = NewsGroupMembership(
                    group_id=group_id,
                    news_id=group_data['primary'].id,
                    is_primary=True,
                    similarity_to_primary=1.0
                )
                db.add(primary_membership)
                
                # 相关新闻
                for related_news in group_data.get('related', []):
                    similarity_score = group_data.get('similarity_scores', {}).get(related_news.id, 0.0)
                    related_membership = NewsGroupMembership(
                        group_id=group_id,
                        news_id=related_news.id,
                        is_primary=False,
                        similarity_to_primary=similarity_score
                    )
                    db.add(related_membership)
                
                groups_created += 1
                
            except Exception as e:
                logger.error(f"保存分组 {group_data['id']} 时出错: {str(e)}")
                continue
        
        db.commit()
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        result = {
            "total_news": len(news_list),
            "groups_created": groups_created,
            "execution_time": execution_time
        }
        
        logger.info(f"事件分组计算完成: {result}")
        return result
    
    def _create_groups_from_similarities(self, db: Session, news_list: List[News]) -> List[Dict]:
        """
        基于存储的相似度记录创建分组
        """
        # 获取相关的相似度记录
        news_ids = [news.id for news in news_list]
        similarities = db.query(NewsSimilarity).filter(
            and_(
                or_(
                    NewsSimilarity.news_id_1.in_(news_ids),
                    NewsSimilarity.news_id_2.in_(news_ids)
                ),
                NewsSimilarity.similarity_score >= self.similarity_service.SIMILARITY_THRESHOLD
            )
        ).all()
        
        # 构建新闻ID到新闻对象的映射
        news_dict = {news.id: news for news in news_list}
        
        # 构建相似度图
        similarity_graph = defaultdict(list)
        for sim in similarities:
            if sim.news_id_1 in news_dict and sim.news_id_2 in news_dict:
                similarity_graph[sim.news_id_1].append((sim.news_id_2, sim.similarity_score))
                similarity_graph[sim.news_id_2].append((sim.news_id_1, sim.similarity_score))
        
        # 使用连通分量算法进行分组
        visited = set()
        groups = []
        
        for news in sorted(news_list, key=lambda n: n.created_at, reverse=True):
            if news.id in visited:
                continue
            
            # 找到连通分量
            component = []
            similarity_scores = {}
            stack = [news.id]
            
            while stack:
                node_id = stack.pop()
                if node_id in visited:
                    continue
                
                visited.add(node_id)
                component.append(node_id)
                
                # 添加相邻节点
                for neighbor_id, score in similarity_graph[node_id]:
                    if neighbor_id not in visited:
                        stack.append(neighbor_id)
                        similarity_scores[neighbor_id] = score
            
            # 创建分组
            if len(component) > 1:
                # 选择最新的新闻作为主要新闻
                component_news = [news_dict[nid] for nid in component]
                primary_news = max(component_news, key=lambda n: n.created_at)
                related_news = [n for n in component_news if n.id != primary_news.id]
                
                # 提取分组实体
                group_entities = defaultdict(set)
                for news_item in component_news:
                    entities = self.similarity_service.extract_key_entities(news_item)
                    for entity_type, values in entities.items():
                        group_entities[entity_type].update(values)
                
                # 转换为可序列化的格式
                serializable_entities = {}
                for entity_type, values in group_entities.items():
                    serializable_entities[entity_type] = list(values)
                
                group = {
                    'id': f'group_{len(groups)}_{int(datetime.now().timestamp())}',
                    'primary': primary_news,
                    'related': related_news,
                    'entities': serializable_entities,
                    'similarity_scores': similarity_scores,
                    'event_label': primary_news.generated_title or primary_news.title,
                    'news_count': len(component_news),
                    'sources': list(set(str(n.source_id) for n in component_news))
                }
                groups.append(group)
            else:
                # 独立新闻也作为单独的组
                single_news = news_dict[component[0]]
                entities = self.similarity_service.extract_key_entities(single_news)
                
                # 转换为可序列化的格式
                serializable_entities = {}
                for entity_type, values in entities.items():
                    serializable_entities[entity_type] = list(values)
                
                group = {
                    'id': f'standalone_{single_news.id}_{int(datetime.now().timestamp())}',
                    'primary': single_news,
                    'related': [],
                    'entities': serializable_entities,
                    'similarity_scores': {},
                    'event_label': single_news.generated_title or single_news.title,
                    'news_count': 1,
                    'sources': [str(single_news.source_id)],
                    'is_standalone': True
                }
                groups.append(group)
        
        return groups
    
    def get_precomputed_groups(self, db: Session, hours: int = 24, 
                              categories: List[str] = None, 
                              source_ids: List[int] = None,
                              exclude_used: bool = True) -> List[Dict]:
        """
        获取预计算的事件分组
        
        Args:
            db: 数据库会话
            hours: 获取最近多少小时的分组
            categories: 分类过滤
            source_ids: 新闻源过滤
            exclude_used: 是否排除已用于快报的新闻
            
        Returns:
            事件分组列表
        """
        time_threshold = datetime.now() - timedelta(hours=hours)
        
        # 构建查询
        query = db.query(NewsEventGroup).filter(
            NewsEventGroup.latest_news_time >= time_threshold
        )
        
        # 如果有过滤条件，需要通过新闻表进行筛选
        if categories or source_ids or exclude_used:
            # 获取符合条件的新闻ID
            news_query = db.query(News.id).filter(
                News.created_at >= time_threshold,
                News.is_processed == True
            )
            
            if categories:
                news_query = news_query.filter(News.category.in_(categories))
            
            if source_ids:
                news_query = news_query.filter(News.source_id.in_(source_ids))
            
            if exclude_used:
                news_query = news_query.filter(News.is_used_in_digest != True)
            
            valid_news_ids = [row.id for row in news_query.all()]
            
            if not valid_news_ids:
                return []
            
            # 查找包含这些新闻的分组
            valid_group_ids = db.query(NewsGroupMembership.group_id).filter(
                NewsGroupMembership.news_id.in_(valid_news_ids)
            ).distinct().all()
            
            if not valid_group_ids:
                return []
            
            group_ids = [row.group_id for row in valid_group_ids]
            query = query.filter(NewsEventGroup.group_id.in_(group_ids))
        
        # 按更新时间排序
        groups = query.order_by(NewsEventGroup.updated_at.desc()).all()
        
        # 构建返回结果
        result_groups = []
        for group in groups:
            # 获取分组成员
            memberships = db.query(NewsGroupMembership).filter(
                NewsGroupMembership.group_id == group.group_id
            ).all()
            
            # 获取新闻详情
            news_ids = [m.news_id for m in memberships]
            news_query = db.query(News).filter(News.id.in_(news_ids))
            
            # 应用过滤条件
            if categories:
                news_query = news_query.filter(News.category.in_(categories))
            if source_ids:
                news_query = news_query.filter(News.source_id.in_(source_ids))
            if exclude_used:
                news_query = news_query.filter(News.is_used_in_digest != True)
            
            group_news = news_query.all()
            
            if not group_news:
                continue  # 过滤后没有新闻，跳过这个分组
            
            news_dict = {news.id: news for news in group_news}
            
            # 分离主要新闻和相关新闻
            primary_news = None
            related_news = []
            similarity_scores = {}
            
            for membership in memberships:
                if membership.news_id not in news_dict:
                    continue  # 新闻被过滤掉了
                
                news_item = news_dict[membership.news_id]
                if membership.is_primary:
                    primary_news = news_item
                else:
                    related_news.append(news_item)
                    similarity_scores[news_item.id] = membership.similarity_to_primary
            
            if not primary_news:
                continue  # 主要新闻被过滤掉了
            
            # 解析实体信息
            try:
                entities = json.loads(group.key_entities) if group.key_entities else {}
            except:
                entities = {}
            
            result_group = {
                'id': group.group_id,
                'primary': primary_news,
                'related': related_news,
                'entities': entities,
                'similarity_scores': similarity_scores,
                'event_label': group.event_label,
                'news_count': len(group_news),
                'sources': list(set(str(news.source_id) for news in group_news)),
                'is_standalone': len(group_news) == 1,
                'created_at': group.created_at,
                'updated_at': group.updated_at
            }
            
            result_groups.append(result_group)
        
        return result_groups
    
    def cleanup_old_similarities(self, db: Session, days: int = 7) -> int:
        """
        清理旧的相似度记录
        
        Args:
            db: 数据库会话
            days: 保留最近多少天的记录
            
        Returns:
            删除的记录数
        """
        cutoff_time = datetime.now() - timedelta(days=days)
        
        # 删除旧的相似度记录
        deleted_similarities = db.query(NewsSimilarity).filter(
            NewsSimilarity.created_at < cutoff_time
        ).delete(synchronize_session=False)
        
        # 删除旧的分组成员关系
        deleted_memberships = db.query(NewsGroupMembership).filter(
            NewsGroupMembership.created_at < cutoff_time
        ).delete(synchronize_session=False)
        
        # 删除空的分组
        orphan_groups = db.query(NewsEventGroup).filter(
            ~NewsEventGroup.group_id.in_(
                db.query(NewsGroupMembership.group_id).distinct()
            )
        ).all()
        
        deleted_groups = len(orphan_groups)
        for group in orphan_groups:
            db.delete(group)
        
        db.commit()
        
        total_deleted = deleted_similarities + deleted_memberships + deleted_groups
        logger.info(f"清理完成: 删除了 {deleted_similarities} 条相似度记录, "
                   f"{deleted_memberships} 条成员关系, {deleted_groups} 个分组")
        
        return total_deleted


# 全局实例
news_similarity_storage_service = NewsSimilarityStorageService() 
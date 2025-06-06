import logging
import hashlib
import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models.event_group import EventGroup
from app.models.news import News, NewsCategory
from app.services.news_similarity import similarity_service

logger = logging.getLogger(__name__)


class EventGroupCacheService:
    """事件分组缓存服务"""

    def __init__(self):
        self.cache_validity_hours = 1  # 缓存有效期（小时）

    def _generate_cache_key(self, hours: int, categories: List[str], 
                          source_ids: List[int], exclude_used: bool) -> str:
        """生成缓存键"""
        # 将参数序列化为字符串
        key_data = {
            'hours': hours,
            'categories': sorted(categories) if categories else [],
            'source_ids': sorted(source_ids) if source_ids else [],
            'exclude_used': exclude_used
        }
        
        # 生成MD5哈希作为缓存键
        key_str = json.dumps(key_data, sort_keys=True)
        cache_key = hashlib.md5(key_str.encode()).hexdigest()
        
        return cache_key

    def _is_cache_valid(self, event_groups: List[EventGroup]) -> bool:
        """检查缓存是否仍然有效"""
        if not event_groups:
            return False
        
        # 获取最新的缓存时间
        latest_cache_time = max(group.created_at for group in event_groups)
        
        # 检查是否超过有效期
        validity_threshold = datetime.now() - timedelta(hours=self.cache_validity_hours)
        
        return latest_cache_time > validity_threshold

    def _clear_expired_cache(self, db: Session, cache_key: str):
        """清理过期缓存"""
        try:
            # 删除该缓存键的所有记录
            db.query(EventGroup).filter(
                EventGroup.group_id.like(f"{cache_key}_%")
            ).delete(synchronize_session=False)
            db.commit()
            logger.info(f"清理缓存键 {cache_key} 的过期记录")
        except Exception as e:
            logger.error(f"清理过期缓存失败: {str(e)}")
            db.rollback()

    def _save_groups_to_cache(self, db: Session, cache_key: str, groups: List[Dict]):
        """将分组结果保存到缓存"""
        try:
            # 先清理旧缓存
            self._clear_expired_cache(db, cache_key)
            
            # 保存新的分组结果
            for i, group in enumerate(groups):
                # 构建实体数据（将set转为list以便JSON序列化）
                entities_data = {}
                for entity_type, entity_set in group['entities'].items():
                    entities_data[entity_type] = list(entity_set)
                
                event_group = EventGroup(
                    group_id=f"{cache_key}_{i}",
                    event_label=group['event_label'],
                    news_count=group['news_count'],
                    sources=group['sources'],
                    primary_news_id=group['primary'].id,
                    related_news_ids=[news.id for news in group['related']],
                    similarity_scores=group['similarity_scores'],
                    entities=entities_data,
                    is_standalone=group.get('is_standalone', False)
                )
                
                db.add(event_group)
            
            db.commit()
            logger.info(f"保存了 {len(groups)} 个事件分组到缓存")
            
        except Exception as e:
            logger.error(f"保存分组到缓存失败: {str(e)}")
            db.rollback()
            raise

    def _load_groups_from_cache(self, db: Session, cache_key: str) -> Optional[List[Dict]]:
        """从缓存加载分组结果"""
        try:
            # 查询缓存记录
            cached_groups = db.query(EventGroup).filter(
                EventGroup.group_id.like(f"{cache_key}_%")
            ).order_by(EventGroup.id).all()
            
            if not cached_groups:
                return None
            
            # 检查缓存有效性
            if not self._is_cache_valid(cached_groups):
                logger.info("缓存已过期，将重新生成")
                self._clear_expired_cache(db, cache_key)
                return None
            
            # 重建分组结构
            groups = []
            
            for cached_group in cached_groups:
                # 获取主要新闻
                primary_news = db.query(News).filter(
                    News.id == cached_group.primary_news_id
                ).first()
                
                if not primary_news:
                    logger.warning(f"主要新闻 ID {cached_group.primary_news_id} 不存在，跳过该组")
                    continue
                
                # 获取相关新闻
                related_news = []
                if cached_group.related_news_ids:
                    related_news = db.query(News).filter(
                        News.id.in_(cached_group.related_news_ids)
                    ).all()
                
                # 重建实体数据（将list转回set）
                entities_data = {}
                for entity_type, entity_list in cached_group.entities.items():
                    entities_data[entity_type] = set(entity_list)
                
                # 构建分组数据
                group = {
                    'id': cached_group.group_id,
                    'primary': primary_news,
                    'related': related_news,
                    'entities': entities_data,
                    'similarity_scores': cached_group.similarity_scores or {},
                    'event_summary': None,
                    'event_label': cached_group.event_label,
                    'news_count': cached_group.news_count,
                    'sources': cached_group.sources or [],
                    'is_standalone': cached_group.is_standalone
                }
                
                groups.append(group)
            
            logger.info(f"从缓存加载了 {len(groups)} 个事件分组")
            return groups
            
        except Exception as e:
            logger.error(f"从缓存加载分组失败: {str(e)}")
            return None

    def get_or_generate_groups(self, db: Session, hours: int = 24, 
                             categories: List[str] = None, 
                             source_ids: List[int] = None,
                             exclude_used: bool = False,
                             force_refresh: bool = False) -> List[Dict]:
        """获取或生成事件分组"""
        
        # 生成缓存键
        cache_key = self._generate_cache_key(hours, categories or [], source_ids or [], exclude_used)
        
        # 如果不强制刷新，先尝试从缓存加载
        if not force_refresh:
            cached_groups = self._load_groups_from_cache(db, cache_key)
            if cached_groups is not None:
                return cached_groups
        
        logger.info("缓存未命中或强制刷新，重新生成事件分组")
        
        # 获取新闻数据
        news_list = self._fetch_news(db, hours, categories, source_ids, exclude_used)
        
        if not news_list:
            logger.info("没有找到符合条件的新闻")
            return []
        
        # 生成分组
        groups = similarity_service.group_similar_news(news_list)
        
        # 保存到缓存
        try:
            self._save_groups_to_cache(db, cache_key, groups)
        except Exception as e:
            logger.error(f"保存缓存失败，但继续返回结果: {str(e)}")
        
        return groups

    def _fetch_news(self, db: Session, hours: int, categories: List[str], 
                   source_ids: List[int], exclude_used: bool) -> List[News]:
        """获取新闻数据"""
        
        # 计算时间范围
        current_time = datetime.now()
        start_time = current_time - timedelta(hours=hours)
        
        # 构建查询
        query = db.query(News).filter(News.created_at >= start_time)
        
        if exclude_used:
            query = query.filter(News.is_used_in_digest == False)
        
        if source_ids:
            query = query.filter(News.source_id.in_(source_ids))
        
        if categories:
            # 将字符串转换为枚举值
            category_enums = []
            for cat_str in categories:
                for enum_item in NewsCategory:
                    if enum_item.value == cat_str:
                        category_enums.append(enum_item)
                        break
            
            if category_enums:
                query = query.filter(News.category.in_(category_enums))
            else:
                # 如果没有匹配的分类，返回空结果
                return []
        
        # 按创建时间倒序排序
        news_list = query.order_by(News.created_at.desc()).all()
        
        logger.info(f"获取到 {len(news_list)} 条新闻用于分组")
        return news_list

    def clear_all_cache(self, db: Session):
        """清理所有缓存"""
        try:
            deleted_count = db.query(EventGroup).delete(synchronize_session=False)
            db.commit()
            logger.info(f"清理了 {deleted_count} 条缓存记录")
        except Exception as e:
            logger.error(f"清理缓存失败: {str(e)}")
            db.rollback()
            raise

    def set_cache_validity_hours(self, hours: int):
        """设置缓存有效期"""
        self.cache_validity_hours = hours
        logger.info(f"设置缓存有效期为 {hours} 小时")


# 单例实例
event_group_cache_service = EventGroupCacheService() 
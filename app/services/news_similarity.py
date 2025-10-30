import logging
from typing import List, Dict, Set, Tuple, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import re
from difflib import SequenceMatcher

from sqlalchemy.orm import Session
from app.models.news import News

# 导入BGE模型和句子嵌入库
try:
    from FlagEmbedding import FlagModel
    import numpy as np
    BGE_AVAILABLE = True
except ImportError:
    BGE_AVAILABLE = False
    FlagModel = None

# 保持sentence-transformers作为备选
try:
    from sentence_transformers import SentenceTransformer
    from sentence_transformers.util import cos_sim
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None
    cos_sim = None

logger = logging.getLogger(__name__)


class NewsSimilarityService:
    """新闻相似度检测服务"""
    
    # 语义相似度模型（懒加载）
    _semantic_model = None
    _semantic_model_name = "BAAI/bge-base-zh-v1.5"
    _fallback_model_name = "paraphrase-multilingual-MiniLM-L12-v2"
    
    # 语义相似度缓存（避免重复计算）
    _semantic_cache = {}
    
    # 关键实体类型权重 - 只关注核心安全实体
    ENTITY_WEIGHTS = {
        # 最高权重：直接标识同一事件的实体
        'CVE': 5.0,           # CVE编号权重最高
        '漏洞编号': 5.0,      # 漏洞编号
        
        # 核心安全实体：用于判断是否同一事件
        '攻击者': 4.0,        # 攻击者
        '受害者': 4.0,        # 受害者
        '组织': 4.0,          # 组织（通常是受害组织）
        '攻击组织': 4.0,      # 攻击组织
        '黑客组织': 4.0,      # 黑客组织
        
        # 其他实体权重极低，基本不参与相似度判断
        '产品': 0.1,          # 产品
        '恶意软件': 0.1,      # 恶意软件
        '攻击方式': 0.1,      # 攻击方式
        '技术': 0.1,          # 技术
        '行业': 0.1,          # 行业
        '地区': 0.1,          # 地区
    }
    
    # 相似度阈值
    SIMILARITY_THRESHOLD = 0.75          # 主要相似度阈值 - 可调整：0.5(宽松) ~ 0.8(严格)
    HIGH_SIMILARITY_THRESHOLD = 0.8     # 高相似度阈值 - 可调整：0.7 ~ 0.9
    
    def __init__(self):
        pass
    
    @classmethod
    def get_semantic_model(cls):
        """懒加载语义相似度模型，优先使用BGE模型"""
        if cls._semantic_model is None:
            # 首先尝试加载BGE模型
            if BGE_AVAILABLE:
                try:
                    logger.info(f"Loading BGE semantic model: {cls._semantic_model_name}")
                    cls._semantic_model = FlagModel(
                        cls._semantic_model_name,
                        query_instruction_for_retrieval='为这个句子生成表示以用于检索相关文章：'
                    )
                    cls._semantic_model.model_type = 'bge'  # 标记模型类型
                    logger.info("BGE semantic similarity model loaded successfully")
                    return cls._semantic_model
                except Exception as e:
                    logger.warning(f"Failed to load BGE model: {e}, falling back to sentence-transformers")
            
            # 如果BGE模型加载失败，回退到sentence-transformers
            if SENTENCE_TRANSFORMERS_AVAILABLE:
                try:
                    logger.info(f"Loading fallback semantic model: {cls._fallback_model_name}")
                    cls._semantic_model = SentenceTransformer(cls._fallback_model_name)
                    cls._semantic_model.model_type = 'sentence_transformers'  # 标记模型类型
                    logger.info("Fallback semantic similarity model loaded successfully")
                except Exception as e:
                    logger.error(f"Failed to load fallback semantic model: {e}")
                    cls._semantic_model = None
            else:
                logger.warning("No semantic similarity libraries available, falling back to text similarity only")
                cls._semantic_model = None
        
        return cls._semantic_model
    
    @classmethod
    def get_cache_stats(cls) -> Dict[str, int]:
        """获取缓存统计信息"""
        return {
            'cache_size': len(cls._semantic_cache),
            'model_loaded': cls._semantic_model is not None
        }
    
    @classmethod
    def clear_cache(cls):
        """清空语义相似度缓存"""
        cls._semantic_cache.clear()
        logger.info("Semantic similarity cache cleared")
    
    def extract_key_entities(self, news: News) -> Dict[str, Set[str]]:
        """提取新闻的关键实体"""
        entities_by_type = defaultdict(set)
        
        if not news.entities:
            return entities_by_type
            
        # 处理实体列表
        if isinstance(news.entities, list):
            for entity in news.entities:
                if isinstance(entity, dict) and 'type' in entity and 'value' in entity:
                    entity_type = entity['type']
                    entity_value = str(entity['value']).strip()
                    if entity_value:
                        # 标准化实体值：去除标点、统一大小写
                        normalized_value = entity_value.lower()
                        # 去除常见的标点符号
                        import re
                        normalized_value = re.sub(r'[.,;:!?()"\'\s]+$', '', normalized_value)
                        normalized_value = re.sub(r'^[.,;:!?()"\'\s]+', '', normalized_value)
                        entities_by_type[entity_type].add(normalized_value)
        
        # 从标题和摘要中提取额外的关键信息
        text = f"{news.generated_title or news.title} {news.generated_summary or news.summary}"
        
        # 提取CVE编号
        cve_pattern = r'CVE-\d{4}-\d{4,}'
        cves = re.findall(cve_pattern, text, re.IGNORECASE)
        for cve in cves:
            entities_by_type['CVE'].add(cve.upper())
        
        # 提取IP地址
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        ips = re.findall(ip_pattern, text)
        for ip in ips:
            entities_by_type['IP地址'].add(ip)
        
        return entities_by_type
    
    def calculate_entity_similarity(self, entities1: Dict[str, Set[str]], 
                                  entities2: Dict[str, Set[str]]) -> Optional[float]:
        """
        计算两个新闻的实体相似度 - 要求所有关键实体都匹配
        
        返回值：
        - float (0.0-1.0): 实体相似度分数
        - None: 实体数量不足，无法基于实体判断相似度
        """
        if not entities1 or not entities2:
            logger.debug("实体为空，无法进行实体相似度判断")
            return None  # 改为返回None而不是0.0
        
        # 计算有效实体数量（排除error等无效实体）
        valid_entities1 = {k: v for k, v in entities1.items() if k != 'error' and v}
        valid_entities2 = {k: v for k, v in entities2.items() if k != 'error' and v}
        
        total_entities1 = sum(len(values) for values in valid_entities1.values())
        total_entities2 = sum(len(values) for values in valid_entities2.values())
        
        # 实体数量门槛：至少2个有效实体才进行判断
        # 如果实体不足，返回None表示无法判断（而不是直接返回0.0认为不相似）
        if total_entities1 < 2 or total_entities2 < 2:
            logger.debug(f"实体数量不足（新闻1: {total_entities1}个, 新闻2: {total_entities2}个），将依赖文本相似度判断")
            return None  # 改为返回None，让调用方决定如何处理
        
        # 只关注最核心的安全实体类型
        critical_entity_types = ['CVE', '漏洞编号', '攻击者', '受害者', '组织', '攻击组织', '黑客组织']
        
        # 找出两个新闻都有的关键实体类型
        entity_types_1 = set(valid_entities1.keys()) & set(critical_entity_types)
        entity_types_2 = set(valid_entities2.keys()) & set(critical_entity_types)
        
        # 如果两个新闻都没有关键实体，无法基于实体判断
        if not entity_types_1 or not entity_types_2:
            logger.debug(f"无关键实体类型，无法基于实体判断（新闻1类型: {entity_types_1}, 新闻2类型: {entity_types_2}）")
            return None  # 改为返回None，表示无法基于实体判断
        
        # 找出两个新闻共同拥有的关键实体类型
        common_critical_types = entity_types_1 & entity_types_2
        
        # 如果没有共同的关键实体类型，认为不相似（这里返回0.0是合理的）
        if not common_critical_types:
            logger.debug(f"实体相似度为0：没有共同的关键实体类型。新闻1实体类型: {entity_types_1}, 新闻2实体类型: {entity_types_2}")
            return 0.0  # 这里保持0.0，因为有实体但完全不同类型
        
        # 新逻辑：要求所有共同的关键实体类型都必须匹配
        weighted_score = 0.0
        total_weight = 0.0
        all_types_matched = True
        matched_types = []
        unmatched_types = []
        
        logger.debug(f"开始检查共同的关键实体类型: {common_critical_types}")
        
        for entity_type in common_critical_types:
            set1 = valid_entities1.get(entity_type, set())
            set2 = valid_entities2.get(entity_type, set())
            
            # 计算Jaccard相似度
            intersection = len(set1 & set2)
            union = len(set1 | set2)
            
            if intersection == 0:
                # 如果这个实体类型没有交集，则不相似
                unmatched_types.append(entity_type)
                logger.debug(f"实体类型 '{entity_type}' 没有匹配: 新闻1={list(set1)}, 新闻2={list(set2)}")
                all_types_matched = False
                break
            else:
                matched_types.append(entity_type)
                logger.debug(f"实体类型 '{entity_type}' 匹配成功: 交集={list(set1 & set2)}, 相似度={intersection/union:.3f}")
            
            if union > 0:
                similarity = intersection / union
                weight = self.ENTITY_WEIGHTS.get(entity_type, 0.05)
                weighted_score += similarity * weight
                total_weight += weight
        
        # 只有当所有共同的关键实体类型都有匹配时才返回相似度
        if not all_types_matched or total_weight == 0:
            logger.debug(f"实体相似度为0：要求所有关键实体都匹配，但有 {len(unmatched_types)} 个类型未匹配: {unmatched_types}")
            return 0.0
        
        logger.debug(f"所有关键实体类型都匹配成功: {matched_types}")
        logger.debug(f"最终实体相似度: {weighted_score/total_weight:.3f}")
        
        # 处理非关键实体类型（权重很低，不影响主要判断）
        non_critical_types = (set(valid_entities1.keys()) | set(valid_entities2.keys())) - set(critical_entity_types)
        for entity_type in non_critical_types:
            set1 = valid_entities1.get(entity_type, set())
            set2 = valid_entities2.get(entity_type, set())
            
            if set1 and set2:
                intersection = len(set1 & set2)
                union = len(set1 | set2)
                
                if union > 0 and intersection > 0:
                    similarity = intersection / union
                    weight = self.ENTITY_WEIGHTS.get(entity_type, 0.05)
                    weighted_score += similarity * weight
                    total_weight += weight
        
        final_similarity = weighted_score / total_weight
        return final_similarity
    
    def calculate_text_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度 - 混合策略（字符串匹配 + 语义相似度）"""
        if not text1 or not text2:
            return 0.0
        
        # 1. 快速字符串相似度检查
        char_similarity = SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
        
        # 如果字符串相似度已经很高，直接返回，节省计算
        if char_similarity >= 0.85:
            return char_similarity
        
        # 2. 语义相似度计算（当字符串相似度不够高时）
        semantic_similarity = self.calculate_semantic_similarity(text1, text2)
        
        # 3. 混合策略：优化BGE模型权重
        if semantic_similarity > 0:
            # BGE模型表现更好，提高语义相似度权重
            model = self.get_semantic_model()
            if hasattr(model, 'model_type') and model.model_type == 'bge':
                # BGE模型使用更高权重（0.95）
                return max(char_similarity, semantic_similarity * 0.91)
            else:
                # 其他模型保持原权重（0.9）
                return max(char_similarity, semantic_similarity * 0.9)
        else:
            # 如果语义相似度计算失败，只使用字符串相似度
            return char_similarity
    
    def calculate_semantic_similarity(self, text1: str, text2: str) -> float:
        """计算语义相似度（带缓存），优先使用BGE模型"""
        model = self.get_semantic_model()
        if model is None:
            return 0.0
        
        # 预处理文本
        clean_text1 = self.clean_text_for_semantic(text1)
        clean_text2 = self.clean_text_for_semantic(text2)
        
        # 创建缓存键（确保顺序一致性）
        texts_sorted = tuple(sorted([clean_text1, clean_text2]))
        cache_key = hash(texts_sorted)
        
        # 检查缓存
        if cache_key in self._semantic_cache:
            return self._semantic_cache[cache_key]
        
        try:
            # 根据模型类型选择不同的计算方法
            if hasattr(model, 'model_type') and model.model_type == 'bge':
                # BGE模型计算
                embeddings = model.encode([clean_text1, clean_text2])
                # 计算余弦相似度
                similarity = np.dot(embeddings[0], embeddings[1]) / (
                    np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
                )
            else:
                # SentenceTransformers模型计算
                embeddings = model.encode([clean_text1, clean_text2], convert_to_tensor=True)
                # 计算余弦相似度
                similarity = cos_sim(embeddings[0], embeddings[1]).item()
            
            similarity = max(0.0, min(1.0, float(similarity)))  # 确保在[0,1]范围内
            
            # 缓存结果（限制缓存大小避免内存泄漏）
            if len(self._semantic_cache) < 1000:
                self._semantic_cache[cache_key] = similarity
            
            return similarity
            
        except Exception as e:
            logger.warning(f"Semantic similarity calculation failed: {e}")
            return 0.0
    
    def clean_text_for_semantic(self, text: str) -> str:
        """清理文本用于语义相似度计算"""
        # 去除【微步】等机构前缀
        text = re.sub(r'^【[^】]+】', '', text)
        
        # 去除多余空格
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def calculate_overall_similarity(self, news1: News, news2: News) -> float:
        """
        计算两个新闻的综合相似度
        
        策略：
        1. CVE编号相同 -> 高度相似(0.9)
        2. 标题高度相似 -> 高度相似(0.9)
        3. 实体相似度判断（如果可用）
        4. 综合评分（实体+标题+摘要+时间因子）
        5. 实体不可用时，依赖文本相似度
        """
        # 提取实体
        entities1 = self.extract_key_entities(news1)
        entities2 = self.extract_key_entities(news2)
        
        # 计算实体相似度（可能返回None表示无法判断）
        entity_sim = self.calculate_entity_similarity(entities1, entities2)
        
        # 特殊情况1：如果有相同的CVE编号，直接认为高度相似
        if entities1.get('CVE') and entities2.get('CVE'):
            if entities1['CVE'] & entities2['CVE']:
                logger.debug(f"发现相同CVE: {entities1['CVE'] & entities2['CVE']}")
                return 0.9
        
        # 特殊情况2：标题高度相似（包括语义相似）认为是同一事件
        title1 = news1.generated_title or news1.title
        title2 = news2.generated_title or news2.title
        title_similarity = self.calculate_text_similarity(title1, title2)
        
        # 降低阈值，因为现在包含了语义相似度，更精确
        if title_similarity >= 0.8:
            logger.debug(f"标题高度相似: {title_similarity:.3f}")
            return 0.9
        
        # ========== 处理实体相似度 ==========
        # 如果实体相似度为None（实体数量不足或无关键实体），降级到纯文本相似度判断
        if entity_sim is None:
            logger.debug("实体相似度不可用，使用纯文本相似度判断")
            # 纯文本判断：标题60% + 摘要40%
            title_sim = title_similarity
            
            summary1 = news1.generated_summary or news1.summary
            summary2 = news2.generated_summary or news2.summary
            summary_sim = self.calculate_text_similarity(summary1[:200], summary2[:200]) if (summary1 and summary2) else 0.0
            
            # 时间因子
            time_diff = abs((news1.created_at - news2.created_at).total_seconds())
            time_factor = 1.0 if time_diff < 48 * 3600 else 0.8
            
            # 纯文本综合相似度
            text_only_similarity = (title_sim * 0.6 + summary_sim * 0.4) * time_factor
            logger.debug(f"纯文本相似度: {text_only_similarity:.3f} (标题:{title_sim:.3f}, 摘要:{summary_sim:.3f}, 时间因子:{time_factor:.2f})")
            return text_only_similarity
        
        # 如果实体相似度为0（没有关键实体匹配），直接返回不相似
        if entity_sim == 0.0:
            logger.debug("实体相似度为0，判定为不相似")
            return 0.0
        
        # 设置较低的门槛，因为已经确保有关键实体匹配
        ENTITY_SIMILARITY_THRESHOLD = 0.3
        if entity_sim < ENTITY_SIMILARITY_THRESHOLD:
            logger.debug(f"实体相似度过低: {entity_sim:.3f}")
            return 0.0
        
        # 只有实体相似度达到门槛才继续计算其他相似度
        # 使用之前计算的标题相似度（权重25%）
        title_sim = title_similarity
        
        # 计算摘要相似度（权重15%）
        summary1 = news1.generated_summary or news1.summary
        summary2 = news2.generated_summary or news2.summary
        summary_sim = self.calculate_text_similarity(summary1[:200], summary2[:200])
        
        # 时间因子（48小时内的新闻相似度不做衰减）
        time_diff = abs((news1.created_at - news2.created_at).total_seconds())
        time_factor = 1.0 if time_diff < 48 * 3600 else 0.8
        
        # 综合相似度
        overall_sim = (entity_sim * 0.6 + title_sim * 0.25 + summary_sim * 0.15) * time_factor
        
        return overall_sim
    
    def group_similar_news(self, news_list: List[News]) -> List[Dict]:
        """将相似的新闻分组（优化版本）"""
        if not news_list:
            return []
        
        # 初始化分组和独立新闻列表
        groups = []
        standalone_news = []
        processed = set()
        
        # 对新闻按时间排序（最新的在前）
        sorted_news = sorted(news_list, key=lambda n: n.created_at, reverse=True)
        
        # 预计算所有新闻的标题和时间用于快速预筛选
        news_data = []
        for i, news in enumerate(sorted_news):
            news_data.append({
                'index': i,
                'title': (news.generated_title or news.title).lower(),
                'time': news.created_at,
                'entities': None  # 懒加载
            })
        
        logger.info(f"开始分组 {len(sorted_news)} 条新闻...")
        processed_count = 0
        skipped_by_title = 0
        skipped_by_time = 0
        
        for i, news1 in enumerate(sorted_news):
            if i in processed:
                continue
            
            # 创建临时组来查找相似新闻
            temp_related = []
            temp_similarity_scores = {}
            
            # 懒加载实体提取
            if news_data[i]['entities'] is None:
                news_data[i]['entities'] = self.extract_key_entities(news1)
            temp_entities = news_data[i]['entities'].copy()
            
            processed.add(i)
            processed_count += 1
            title1 = news_data[i]['title']
            time1 = news_data[i]['time']
            
            # 查找相似的新闻 - 使用多层预筛选
            for j, news2 in enumerate(sorted_news[i+1:], i+1):
                if j in processed:
                    continue
                
                title2 = news_data[j]['title']
                time2 = news_data[j]['time']
                
                # 时间预筛选：只对72小时内的新闻进行比较
                time_diff = abs((time1 - time2).total_seconds())
                if time_diff > 72 * 3600:  # 72小时
                    skipped_by_time += 1
                    continue
                
                # 快速预筛选：只有标题字符串相似度 >= 0.4 才进行详细计算  
                char_similarity = SequenceMatcher(None, title1, title2).ratio()
                
                # 如果字符串相似度太低，直接跳过（节省大量计算）
                if char_similarity < 0.5:
                    skipped_by_title += 1
                    continue
                
                # 进行完整的相似度计算
                similarity = self.calculate_overall_similarity(news1, news2)
                
                if similarity >= self.SIMILARITY_THRESHOLD:
                    temp_related.append(news2)
                    temp_similarity_scores[news2.id] = similarity
                    processed.add(j)
                    
                    # 合并实体（懒加载）
                    if news_data[j]['entities'] is None:
                        news_data[j]['entities'] = self.extract_key_entities(news2)
                    entities2 = news_data[j]['entities']
                    for entity_type, values in entities2.items():
                        temp_entities[entity_type].update(values)
            
            # 只有当找到相关新闻时才创建事件组
            if temp_related:
                group = {
                    'id': f'group_{len(groups)}',
                    'primary': news1,  # 主要新闻（最新的）
                    'related': temp_related,     # 相关新闻
                    'entities': temp_entities,  # 组的关键实体
                    'similarity_scores': temp_similarity_scores,  # 相似度分数
                    'event_summary': None  # 事件摘要（可选）
                }
                groups.append(group)
                logger.debug(f"创建事件组，包含 {1 + len(temp_related)} 条新闻")
            else:
                # 没有相关新闻，作为独立新闻
                standalone_news.append(news1)
        
        # 为每个组生成事件标签
        for group in groups:
            group['event_label'] = self._generate_event_label(group)
            group['news_count'] = 1 + len(group['related'])
            group['sources'] = self._get_group_sources(group)
        
        # 将独立新闻转换为"事件组"格式以便统一处理
        for news in standalone_news:
            # 找到对应的预计算实体
            news_index = next(i for i, n in enumerate(sorted_news) if n.id == news.id)
            if news_data[news_index]['entities'] is None:
                news_data[news_index]['entities'] = self.extract_key_entities(news)
            
            standalone_group = {
                'id': f'standalone_{news.id}',
                'primary': news,
                'related': [],
                'entities': news_data[news_index]['entities'],
                'similarity_scores': {},
                'event_summary': None,
                'event_label': news.generated_title or news.title,
                'news_count': 1,
                'sources': [str(news.source_id)],
                'is_standalone': True  # 标记为独立新闻
            }
            groups.append(standalone_group)
        
        logger.info(f"分组完成：{len(groups)} 个组（{len(groups) - len(standalone_news)} 个事件组，{len(standalone_news)} 条独立新闻）")
        logger.info(f"性能统计：处理了 {processed_count} 条新闻，跳过 {skipped_by_time} 次时间筛选，{skipped_by_title} 次标题筛选")
        return groups
    
    def _generate_event_label(self, group: Dict) -> str:
        """为新闻组生成事件标签"""
        primary_news = group['primary']
        
        # 直接使用主要新闻的标题作为事件标题
        return primary_news.generated_title or primary_news.title
    
    def _get_group_sources(self, group: Dict) -> List[str]:
        """获取新闻组的所有来源"""
        sources = set()
        sources.add(str(group['primary'].source_id))
        
        for news in group['related']:
            sources.add(str(news.source_id))
        
        return sorted(sources)
    
    def find_similar_news(self, target_news: News, db: Session, 
                         hours: int = 48) -> List[Tuple[News, float]]:
        """查找与目标新闻相似的其他新闻"""
        # 获取时间范围内的新闻
        time_threshold = datetime.now() - timedelta(hours=hours)
        
        query = db.query(News).filter(
            News.created_at >= time_threshold,
            News.id != target_news.id,
            News.is_processed == True
        )
        
        # 如果目标新闻有分类，优先查找相同分类的
        if target_news.category:
            candidates = query.filter(News.category == target_news.category).all()
        else:
            candidates = query.all()
        
        # 计算相似度
        similar_news = []
        for candidate in candidates:
            similarity = self.calculate_overall_similarity(target_news, candidate)
            if similarity >= self.SIMILARITY_THRESHOLD:
                similar_news.append((candidate, similarity))
        
        # 按相似度排序
        similar_news.sort(key=lambda x: x[1], reverse=True)
        
        return similar_news

    def filter_similar_to_used_news(self, news_list: List[News], db: Session) -> List[News]:
        """过滤掉与已用于快报的新闻相似的文章（同一天的除外）"""
        if not news_list:
            return []
        
        # 获取所有已用于快报的新闻
        used_news = db.query(News).filter(
            News.is_used_in_digest == True,
            News.is_processed == True
        ).all()
        
        if not used_news:
            return news_list
        
        filtered_news = []
        today = datetime.now().date()
        
        for news in news_list:
            should_include = True
            news_date = news.created_at.date()
            
            # 检查是否与已使用的新闻相似
            for used in used_news:
                used_date = used.created_at.date()
                
                # 如果是同一天的新闻，不过滤（保持当天新闻稳定）
                if news_date == today and used_date == today:
                    continue
                
                # 计算与已使用新闻的相似度
                similarity = self.calculate_overall_similarity(news, used)
                
                # 如果相似度超过阈值，且不是同一天，则过滤掉
                if similarity >= self.SIMILARITY_THRESHOLD:
                    should_include = False
                    break
            
            if should_include:
                filtered_news.append(news)
        
        return filtered_news

    def group_todays_news_with_history_similar(self, news_list: List[News], db: Session) -> Dict[str, List[News]]:
        """
        将今日文章分组：今日新文章 vs 与历史快报文章相似的文章
        
        Returns:
            Dict with keys:
            - 'fresh_news': 今日新文章（与历史快报不相似）
            - 'similar_to_history': 与历史快报文章相似的文章
        """
        if not news_list:
            return {'fresh_news': [], 'similar_to_history': []}
        
        # 获取所有已用于快报的历史新闻（非当日）
        today = datetime.now().date()
        used_news = db.query(News).filter(
            News.is_used_in_digest == True,
            News.is_processed == True
        ).all()
        
        # 过滤出非当日的历史快报文章
        historical_used_news = [
            news for news in used_news 
            if news.created_at.date() != today
        ]
        
        if not historical_used_news:
            # 如果没有历史快报文章，所有文章都是新文章
            return {'fresh_news': news_list, 'similar_to_history': []}
        
        fresh_news = []
        similar_to_history = []
        
        for news in news_list:
            is_similar_to_history = False
            news_date = news.created_at.date()
            
            # 检查是否与历史快报文章相似
            for used in historical_used_news:
                similarity = self.calculate_overall_similarity(news, used)
                
                # 如果相似度超过阈值，标记为与历史相似
                if similarity >= self.SIMILARITY_THRESHOLD:
                    is_similar_to_history = True
                    break
            
            if is_similar_to_history:
                similar_to_history.append(news)
            else:
                fresh_news.append(news)
        
        return {
            'fresh_news': fresh_news,
            'similar_to_history': similar_to_history
        }


# 单例实例
similarity_service = NewsSimilarityService() 
"""
新闻重复检测服务
使用LLM分析新闻是否描述同一事件
包含轻量级预筛选以节省token和时间
"""

import asyncio
import threading
import os
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import pytz
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc

from app.db.session import SessionLocal
from app.models.news import News
from app.models.digest import Digest
from app.models.duplicate_detection import DuplicateDetectionResult, DuplicateDetectionStatus
from app.services import llm_processor
from app.services.news_similarity import similarity_service
from app.config import get_logger

logger = get_logger(__name__)


class DuplicateDetectorService:
    """重复检测服务"""

    def __init__(self):
        self.beijing_tz = pytz.timezone('Asia/Shanghai')
        # 从环境变量获取重复检测专用模型，默认使用 ark-deepseek-r1-250528
        self.model = os.getenv("OPENAI_DUPLICATE_DETECTOR_MODEL", "ark-deepseek-r1-250528")
        
        # 预筛选配置：阈值较低以确保不漏报
        self.enable_prefilter = os.getenv("ENABLE_DUPLICATE_PREFILTER", "true").lower() == "true"
        self.prefilter_threshold = float(os.getenv("DUPLICATE_PREFILTER_THRESHOLD", "0.35"))
        
        logger.info(f"重复检测服务初始化，使用模型: {self.model}")
        logger.info(f"预筛选: {'启用' if self.enable_prefilter else '禁用'}, 阈值: {self.prefilter_threshold}")

        # 延迟导入时间跟踪器以避免循环导入
        self._timer = None
        
        # 统计信息
        self.reset_statistics()

    @property
    def timer(self):
        """获取时间跟踪器实例"""
        if self._timer is None:
            from app.services.duplicate_detection_timer import detection_timer
            self._timer = detection_timer
        return self._timer
    
    def reset_statistics(self):
        """重置统计信息"""
        self.stats = {
            'total_comparisons': 0,        # 总比较对数
            'prefilter_skipped': 0,        # 预筛选跳过数
            'llm_calls': 0,                # 实际LLM调用数
            'duplicates_found': 0,         # 发现的重复数
            'time_saved_seconds': 0.0,     # 节省的时间（秒）
        }
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        stats = self.stats.copy()
        if stats['total_comparisons'] > 0:
            stats['skip_rate'] = stats['prefilter_skipped'] / stats['total_comparisons'] * 100
            stats['efficiency_gain'] = stats['prefilter_skipped'] / stats['total_comparisons'] * 100
        else:
            stats['skip_rate'] = 0
            stats['efficiency_gain'] = 0
        return stats
    
    def should_compare_with_llm(self, current_news: News, reference_news: News) -> Tuple[bool, float, str]:
        """
        预筛选：判断是否需要用LLM进行深度比较
        
        策略：
        1. CVE豁免规则：相同CVE编号强制进行LLM检测
        2. 文本相似度：标题和摘要的混合相似度
        3. 实体辅助判断：关键实体匹配时降低文本相似度要求
        
        Returns:
            Tuple[bool, float, str]: (是否需要LLM比较, 预筛选相似度, 跳过原因)
        """
        if not self.enable_prefilter:
            return True, 1.0, "预筛选未启用"
        
        try:
            # ============ 第一步：CVE豁免检查 ============
            # 提取CVE编号（从标题和摘要中）
            import re
            
            def extract_cve_numbers(news: News) -> set:
                """从新闻中提取CVE编号"""
                cve_set = set()
                
                # 从实体中提取
                if news.entities and isinstance(news.entities, list):
                    for entity in news.entities:
                        if isinstance(entity, dict) and entity.get('type') == 'CVE':
                            cve_set.add(entity.get('value', '').upper())
                
                # 从标题和摘要中提取
                text = f"{news.generated_title or news.title} {news.generated_summary or news.summary or ''}"
                cve_pattern = r'CVE-\d{4}-\d{4,}'
                cves = re.findall(cve_pattern, text, re.IGNORECASE)
                for cve in cves:
                    cve_set.add(cve.upper())
                
                return cve_set
            
            cve_set1 = extract_cve_numbers(current_news)
            cve_set2 = extract_cve_numbers(reference_news)
            
            # 如果有相同的CVE编号，强制进行LLM检测
            common_cves = cve_set1 & cve_set2
            if common_cves:
                logger.info(f"发现相同CVE编号 {common_cves}，强制进行LLM深度检测")
                return True, 1.0, f"CVE豁免：相同CVE编号 {common_cves}"
            
            # ============ 第二步：实体辅助判断 ============
            # 提取关键实体用于辅助判断
            entities1 = similarity_service.extract_key_entities(current_news)
            entities2 = similarity_service.extract_key_entities(reference_news)
            
            # 检查关键实体类型（攻击者、受害者、组织等）
            critical_entity_types = ['攻击者', '受害者', '组织', '攻击组织', '黑客组织', '漏洞编号']
            has_common_critical_entities = False
            
            for entity_type in critical_entity_types:
                set1 = entities1.get(entity_type, set())
                set2 = entities2.get(entity_type, set())
                if set1 and set2 and (set1 & set2):
                    has_common_critical_entities = True
                    logger.debug(f"发现相同的关键实体类型 '{entity_type}': {set1 & set2}")
                    break
            
            # ============ 第三步：文本相似度计算 ============
            # 计算标题相似度
            title1 = current_news.generated_title or current_news.title
            title2 = reference_news.generated_title or reference_news.title
            title_sim = similarity_service.calculate_text_similarity(title1, title2)
            
            # 计算摘要相似度
            summary1 = current_news.generated_summary or current_news.summary or ''
            summary2 = reference_news.generated_summary or reference_news.summary or ''
            summary_sim = 0.0
            if summary1 and summary2:
                summary_sim = similarity_service.calculate_text_similarity(summary1[:200], summary2[:200])
            
            # 混合策略：标题权重70%，摘要权重30%
            # 标题更能代表事件核心，权重更高
            if summary1 and summary2:
                text_similarity = title_sim * 0.7 + summary_sim * 0.3
            else:
                # 如果没有摘要，只用标题
                text_similarity = title_sim
            
            # ============ 第四步：综合判断 ============
            # 如果有共同的关键实体，降低文本相似度要求
            effective_threshold = self.prefilter_threshold
            if has_common_critical_entities:
                effective_threshold = max(0.25, self.prefilter_threshold - 0.1)
                logger.debug(f"有共同关键实体，降低阈值至 {effective_threshold:.2f}")
            
            # 判断是否需要LLM比较
            if text_similarity < effective_threshold:
                return False, text_similarity, \
                    f"文本相似度过低 (综合:{text_similarity:.3f}, 标题:{title_sim:.3f}, 摘要:{summary_sim:.3f}, 阈值:{effective_threshold:.2f})"
            
            # 相似度达到阈值，需要LLM深度分析
            return True, text_similarity, \
                f"文本相似度足够 (综合:{text_similarity:.3f}, 标题:{title_sim:.3f}, 摘要:{summary_sim:.3f}, 阈值:{effective_threshold:.2f})"
            
        except Exception as e:
            # 预筛选失败，保守起见进行LLM比较
            logger.warning(f"预筛选失败，将进行LLM比较: {e}")
            return True, 0.0, f"预筛选出错: {str(e)}"

    def get_last_three_days_digests(self, db: Session, current_digest_id: int = None) -> List[Digest]:
        """获取过去三天每天的最后一份快报（不包括当前快报的创建日期）"""
        try:
            # 如果提供了当前快报ID，以其创建时间为基准；否则使用当前时间
            if current_digest_id:
                current_digest = db.query(Digest).filter(Digest.id == current_digest_id).first()
                if current_digest and current_digest.created_at:
                    reference_date = current_digest.created_at.astimezone(self.beijing_tz).date()
                    logger.info(f"基于快报 {current_digest_id} 的创建时间 {reference_date} 进行重复检测")
                else:
                    logger.warning(f"无法获取快报 {current_digest_id} 的创建时间，使用当前时间")
                    reference_date = datetime.now(self.beijing_tz).date()
            else:
                reference_date = datetime.now(self.beijing_tz).date()

            # 计算过去三天的日期范围（不包括参考日期）
            yesterday = reference_date - timedelta(days=1)
            three_days_ago = reference_date - timedelta(days=4)  # 需要往前推4天才能获得3个完整的历史日期

            # 查询过去三天的所有快报按日期分组（排除参考日期）
            recent_dates = db.query(func.date(Digest.created_at)).filter(
                func.date(Digest.created_at) <= yesterday,
                func.date(Digest.created_at) > three_days_ago
            ).distinct().order_by(func.date(Digest.created_at).desc()).limit(3).all()

            last_digests = []
            for date_tuple in recent_dates:
                date_val = date_tuple[0]
                # 获取该日期的最后一份快报
                last_digest = db.query(Digest).filter(
                    func.date(Digest.created_at) == date_val
                ).order_by(Digest.created_at.desc()).first()

                if last_digest:
                    last_digests.append(last_digest)

            logger.info(f"获取到过去三天的快报数量: {len(last_digests)}（不包括参考日期 {reference_date}）")
            for digest in last_digests:
                digest_date = digest.created_at.date() if digest.created_at else "未知日期"
                logger.info(f"  - 快报 {digest.id}: {digest_date} ({len(digest.news_items)} 条新闻)")
            return last_digests

        except Exception as e:
            logger.error(f"获取过去三天快报失败: {e}")
            return []

    def collect_reference_news(self, digests: List[Digest]) -> List[News]:
        """从快报中收集所有新闻作为参考集合"""
        reference_news = []
        for digest in digests:
            if digest.news_items:
                reference_news.extend(digest.news_items)

        # 去重（基于news.id）
        unique_news = {}
        for news in reference_news:
            unique_news[news.id] = news

        result = list(unique_news.values())
        logger.info(f"收集到参考新闻数量: {len(result)}")
        return result

    def analyze_similarity_with_llm(self, current_news: News, reference_news: News) -> Tuple[bool, float, str]:
        """
        使用LLM分析两条新闻是否描述同一事件

        Returns:
            Tuple[bool, float, str]: (是否重复, 相似度分数, LLM推理过程)
        """
        try:
            # 优先使用翻译后的中文版本，如果没有则使用原始版本
            current_title = current_news.generated_title or current_news.title
            current_summary = current_news.generated_summary or current_news.summary or current_news.article_summary

            reference_title = reference_news.generated_title or reference_news.title
            reference_summary = reference_news.generated_summary or reference_news.summary or reference_news.article_summary

            # 构建优化后的提示词
            prompt = f"""
你是一个专业的网络安全事件分析师。请分析以下两条新闻是否描述的是同一个安全事件。

**重要说明：**
- 请重点关注事件的核心要素，而非文字表面相似性
- 即使用词不同，只要事件本质相同就应该识别为重复
- 特别关注：受影响的组织/公司名称、事件性质（如网络攻击、数据泄露等）、事件时间范围、影响程度

**新闻A：**
标题：{current_title}
摘要：{current_summary}
发布时间：{current_news.publish_date}

**新闻B：**
标题：{reference_title}
摘要：{reference_summary}
发布时间：{reference_news.publish_date}

**分析要求：**
1. 提取每条新闻的关键信息（公司/组织、事件类型、时间、影响）
2. 比较是否描述同一个事件的不同阶段或不同角度
3. 考虑事件的后续发展（如"延期"、"持续"等更新）

请按以下格式回答：
1. **关键信息提取：**
   - 新闻A核心信息：[公司、事件类型、时间、关键词]
   - 新闻B核心信息：[公司、事件类型、时间、关键词]
2. **相似度评分：** [0-10的数字，7-10表示同一事件的不同报道，4-6表示相关但不同事件，0-3表示无关]
3. **结论：** [是/否] - 是否描述同一安全事件
4. **判断理由：** [基于核心要素的详细说明]
"""

            # 调用LLM并记录时间
            start_time = time.time()
            try:
                response = llm_processor.openai_client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500
                )

                if not response or not response.choices:
                    # 记录失败的调用时间
                    elapsed_time = time.time() - start_time
                    self.timer.add_timing_record(elapsed_time, self.model, success=False)
                    return False, 0.0, "LLM调用失败"

                llm_response = response.choices[0].message.content.strip()

                # 记录成功的调用时间
                elapsed_time = time.time() - start_time
                self.timer.add_timing_record(elapsed_time, self.model, success=True)

            except Exception as e:
                # 记录失败的调用时间
                elapsed_time = time.time() - start_time
                self.timer.add_timing_record(elapsed_time, self.model, success=False)
                return False, 0.0, f"LLM调用出错: {str(e)}"

            # 解析LLM响应
            is_duplicate = False
            similarity_score = 0.0

            # 简单的解析逻辑 - 支持中英文冒号
            if "结论：是" in llm_response or "结论:是" in llm_response:
                is_duplicate = True

            # 尝试提取相似度评分
            import re
            score_match = re.search(r'相似度评分.*?(\d+(?:\.\d+)?)', llm_response)
            if score_match:
                try:
                    raw_score = float(score_match.group(1))
                    similarity_score = raw_score / 10.0  # 转换为0-1范围
                except:
                    pass

            # 如果评分高于0.7，认为是重复
            if similarity_score > 0.7:
                is_duplicate = True

            logger.info(f"LLM分析完成: 重复={is_duplicate}, 分数={similarity_score}")
            logger.info(f"LLM完整响应: {llm_response[:500]}...")  # 只显示前500个字符避免日志过长
            return is_duplicate, similarity_score, llm_response

        except Exception as e:
            logger.error(f"LLM分析失败: {e}")
            return False, 0.0, f"分析出错: {str(e)}"

    def detect_duplicates_for_digest(self, digest_id: int, selected_news_ids: List[int]):
        """
        为快报中的新闻检测重复
        这个方法会在后台异步运行
        """
        def run_detection():
            db = SessionLocal()
            try:
                # 更新状态为运行中并记录开始时间
                digest = db.query(Digest).filter(Digest.id == digest_id).first()
                if digest:
                    digest.duplicate_detection_status = 'running'
                    digest.duplicate_detection_started_at = datetime.now()
                    db.commit()

                logger.info(f"开始检测快报 {digest_id} 的重复新闻")

                # 获取过去三天的快报
                reference_digests = self.get_last_three_days_digests(db, digest_id)
                if not reference_digests:
                    logger.info("没有找到参考快报，跳过重复检测")
                    return

                # 收集参考新闻
                reference_news_list = self.collect_reference_news(reference_digests)
                if not reference_news_list:
                    logger.info("没有找到参考新闻，跳过重复检测")
                    return

                # 为每条选中的新闻创建检测记录
                for news_id in selected_news_ids:
                    try:
                        # 获取当前新闻
                        current_news = db.query(News).filter(News.id == news_id).first()
                        if not current_news:
                            logger.warning(f"新闻 {news_id} 不存在")
                            continue

                        # 创建检测记录
                        detection_result = DuplicateDetectionResult(
                            digest_id=digest_id,
                            news_id=news_id,
                            status=DuplicateDetectionStatus.CHECKING.value
                        )
                        db.add(detection_result)
                        db.commit()
                        db.refresh(detection_result)

                        logger.info(f"开始检测新闻 {news_id}: {current_news.title[:50]}...")

                        # 与参考新闻进行比较
                        best_match = None
                        best_score = 0.0
                        best_reasoning = ""
                        
                        # 统计变量
                        comparison_count = 0
                        skipped_count = 0
                        llm_call_count = 0

                        for ref_news in reference_news_list:
                            # 跳过自己
                            if ref_news.id == news_id:
                                continue

                            # 额外安全检查：跳过今天的新闻（虽然理论上不会出现）
                            if ref_news.created_at:
                                ref_news_date = ref_news.created_at.date()
                                today = datetime.now(self.beijing_tz).date()
                                if ref_news_date >= today:
                                    logger.debug(f"跳过今天的参考新闻: {ref_news.id}")
                                    continue
                            
                            comparison_count += 1
                            self.stats['total_comparisons'] += 1
                            
                            # 预筛选：判断是否需要LLM比较
                            should_compare, prefilter_sim, reason = self.should_compare_with_llm(
                                current_news, ref_news
                            )
                            
                            if not should_compare:
                                # 预筛选跳过
                                skipped_count += 1
                                self.stats['prefilter_skipped'] += 1
                                logger.debug(f"预筛选跳过: 新闻{news_id} vs 参考{ref_news.id}, {reason}")
                                continue

                            # 调用LLM分析
                            llm_call_count += 1
                            self.stats['llm_calls'] += 1
                            logger.debug(f"LLM比较: 新闻{news_id} vs 参考{ref_news.id}, {reason}")
                            
                            is_duplicate, score, reasoning = self.analyze_similarity_with_llm(
                                current_news, ref_news
                            )

                            # 更新最佳匹配
                            if is_duplicate and score > best_score:
                                best_match = ref_news
                                best_score = score
                                best_reasoning = reasoning

                        # 更新检测结果
                        if best_match:
                            detection_result.status = DuplicateDetectionStatus.DUPLICATE.value
                            detection_result.duplicate_with_news_id = best_match.id
                            detection_result.similarity_score = best_score
                            detection_result.llm_reasoning = best_reasoning
                            self.stats['duplicates_found'] += 1
                            logger.info(f"发现重复: 新闻 {news_id} 与新闻 {best_match.id} 重复, 相似度 {best_score}")
                        else:
                            detection_result.status = DuplicateDetectionStatus.NO_DUPLICATE.value
                            logger.info(f"无重复: 新闻 {news_id}")
                        
                        # 输出单条新闻的统计
                        skip_rate = (skipped_count / comparison_count * 100) if comparison_count > 0 else 0
                        logger.info(f"新闻 {news_id} 检测完成: 总比较{comparison_count}, "
                                  f"LLM调用{llm_call_count}, 预筛选跳过{skipped_count} ({skip_rate:.1f}%)")

                        detection_result.checked_at = datetime.now()
                        db.commit()

                    except Exception as e:
                        logger.error(f"检测新闻 {news_id} 时出错: {e}")
                        # 标记为错误状态
                        try:
                            detection_result.status = DuplicateDetectionStatus.ERROR.value
                            detection_result.llm_reasoning = f"检测出错: {str(e)}"
                            db.commit()
                        except:
                            pass

                logger.info(f"快报 {digest_id} 重复检测完成")
                
                # 输出整体统计信息
                stats = self.get_statistics()
                logger.info(f"========== 检测统计 ==========")
                logger.info(f"总比较次数: {stats['total_comparisons']}")
                logger.info(f"LLM调用次数: {stats['llm_calls']}")
                logger.info(f"预筛选跳过: {stats['prefilter_skipped']} ({stats['skip_rate']:.1f}%)")
                logger.info(f"发现重复: {stats['duplicates_found']}")
                if stats['prefilter_skipped'] > 0:
                    # 假设每次LLM调用平均3秒
                    estimated_time_saved = stats['prefilter_skipped'] * 3.0
                    logger.info(f"预计节省时间: {estimated_time_saved:.1f}秒 ({estimated_time_saved/60:.1f}分钟)")
                    logger.info(f"效率提升: {stats['efficiency_gain']:.1f}%")
                logger.info(f"==============================")

                # 更新状态为已完成
                digest = db.query(Digest).filter(Digest.id == digest_id).first()
                if digest:
                    digest.duplicate_detection_status = 'completed'
                    db.commit()

            except Exception as e:
                logger.error(f"重复检测过程出错: {e}")
                # 更新状态为失败
                try:
                    digest = db.query(Digest).filter(Digest.id == digest_id).first()
                    if digest:
                        digest.duplicate_detection_status = 'failed'
                        db.commit()
                except Exception:
                    pass
            finally:
                db.close()

        # 首先设置状态为pending（等待开始）
        db_session = SessionLocal()
        try:
            digest = db_session.query(Digest).filter(Digest.id == digest_id).first()
            if digest:
                digest.duplicate_detection_status = 'pending'
                db_session.commit()
        except Exception:
            pass
        finally:
            db_session.close()

        # 在后台线程中运行检测
        thread = threading.Thread(target=run_detection, daemon=True)
        thread.start()
        logger.info(f"已启动快报 {digest_id} 的后台重复检测")

    def get_duplicate_detection_status(self, digest_id: int, db: Session) -> Dict[int, Dict]:
        """获取快报的重复检测状态"""
        try:
            results = db.query(DuplicateDetectionResult).filter(
                DuplicateDetectionResult.digest_id == digest_id
            ).all()

            status_dict = {}
            for result in results:
                status_dict[result.news_id] = {
                    "status": result.status,
                    "duplicate_with_news_id": result.duplicate_with_news_id,
                    "similarity_score": result.similarity_score,
                    "llm_reasoning": result.llm_reasoning,
                    "checked_at": result.checked_at.isoformat() if result.checked_at else None
                }

            return status_dict

        except Exception as e:
            logger.error(f"获取重复检测状态失败: {e}")
            return {}


# 创建全局实例
duplicate_detector_service = DuplicateDetectorService()
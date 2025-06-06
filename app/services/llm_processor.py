import os
import openai
import logging
import json
import re
from typing import List, Tuple, Optional, Dict
from sqlalchemy.orm import Session
from lingua import Language, LanguageDetectorBuilder
from app.models.news import News, NewsCategory

# 获取日志记录器
from app.config import get_logger
logger = get_logger(__name__)

# 初始化lingua语言检测器
# 创建支持的语言列表，优先考虑常用的网络安全新闻语言
SUPPORTED_LANGUAGES = [
    Language.CHINESE,  # 中文
    Language.ENGLISH,  # 英文
    Language.RUSSIAN,  # 俄语
    Language.JAPANESE,  # 日语
    Language.KOREAN,  # 韩语
    Language.FRENCH,  # 法语
    Language.GERMAN,  # 德语
    Language.SPANISH,  # 西班牙语
    Language.PORTUGUESE,  # 葡萄牙语
    Language.ARABIC,  # 阿拉伯语
    Language.PERSIAN,  # 波斯语
    Language.DUTCH,  # 荷兰语
    Language.ITALIAN,  # 意大利语
    Language.POLISH,  # 波兰语
    Language.HEBREW,  # 希伯来语
    Language.TURKISH,  # 土耳其语
    Language.SWEDISH,  # 瑞典语
    Language.UKRAINIAN,  # 乌克兰语
]

# 构建语言检测器
language_detector = LanguageDetectorBuilder.from_languages(*SUPPORTED_LANGUAGES).build()

# 配置OpenAI API
api_key = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
# 为翻译和总结任务添加专用模型配置
translation_model = os.getenv("OPENAI_TRANSLATION_MODEL", model)
summarization_model = os.getenv("OPENAI_SUMMARIZATION_MODEL", model)
api_base = os.getenv("OPENAI_API_BASE", "")

# 初始化OpenAI客户端
if api_base:
    # 使用自定义API基础URL
    openai_client = openai.OpenAI(api_key=api_key, base_url=api_base)
    logger.info(f"使用自定义OpenAI API基础URL: {api_base}")
else:
    # 使用默认官方API
    openai_client = openai.OpenAI(api_key=api_key)
    logger.info("使用OpenAI官方API")

# 记录模型配置
logger.info(f"默认模型: {model}")
logger.info(f"翻译模型: {translation_model}")
logger.info(f"总结模型: {summarization_model}")


def parse_llm_response(response_text, expected_format="json"):
    """
    通用的LLM响应解析函数，处理各种格式的返回结果

    参数:
    - response_text: LLM返回的原始文本
    - expected_format: 期望的返回格式，默认为"json"

    返回:
    - 解析后的数据，或在解析失败时返回备用值
    """
    if not response_text:
        logger.error("LLM返回了空响应")
        return None

    # 记录原始响应前100个字符用于调试
    logger.debug(f"原始LLM响应: {response_text[:100]}...")

    # 对于JSON格式的处理
    if expected_format == "json":
        # 1. 首先尝试提取代码块中的JSON
        json_content = response_text
        # 匹配Markdown代码块
        code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response_text)
        if code_block_match:
            json_content = code_block_match.group(1).strip()
            logger.debug("从代码块中提取JSON内容")

        # 2. 尝试解析JSON
        try:
            data = json.loads(json_content)
            logger.debug(f"成功解析JSON: {type(data)}")
            return data
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败: {str(e)}，尝试备用解析方法")

            try:
                # 3. 尝试修复常见JSON格式问题
                # 移除可能的注释
                cleaned_json = re.sub(r"//.*?$", "", json_content, flags=re.MULTILINE)
                # 尝试再次解析
                data = json.loads(cleaned_json)
                logger.debug("使用清理后的JSON成功解析")
                return data
            except json.JSONDecodeError:
                pass

            # 4. 尝试通过正则表达式提取JSON对象或数组
            try:
                # 尝试匹配JSON数组
                array_match = re.search(r"(\[\s*\{.*\}\s*\])", response_text, re.DOTALL)
                if array_match:
                    data = json.loads(array_match.group(1))
                    logger.debug("通过正则表达式成功提取JSON数组")
                    return data

                # 尝试匹配JSON对象
                obj_match = re.search(r'(\{\s*".*"\s*:.*\})', response_text, re.DOTALL)
                if obj_match:
                    data = json.loads(obj_match.group(1))
                    logger.debug("通过正则表达式成功提取JSON对象")
                    return data
            except Exception as e:
                logger.error(f"正则表达式提取JSON失败: {str(e)}")

            # 5. 最后返回错误信息
            logger.error(f"所有JSON解析方法均失败。原始内容: {response_text}")
            return None

    # 对于纯文本格式的处理
    elif expected_format == "text":
        # 移除可能的代码块标记
        text_content = response_text
        code_block_match = re.search(r"```(?:text)?\s*([\s\S]*?)\s*```", response_text)
        if code_block_match:
            text_content = code_block_match.group(1).strip()

        return text_content

    # 其他格式的处理可以在这里扩展
    else:
        logger.warning(f"不支持的预期格式: {expected_format}")
        return response_text


def preprocess_text_for_detection(text):
    """预处理文本以提高语言检测的准确性"""
    if not text:
        return ""

    # 确保文本是Unicode字符串
    if isinstance(text, bytes):
        try:
            # 尝试以utf-8解码
            text = text.decode("utf-8")
        except UnicodeDecodeError:
            try:
                # 尝试以gbk解码(常见中文编码)
                text = text.decode("gbk")
            except UnicodeDecodeError:
                try:
                    # 容错模式
                    text = text.decode("utf-8", errors="replace")
                except:
                    return ""

    # 非字符串类型转换为字符串
    if not isinstance(text, str):
        try:
            text = str(text)
        except:
            return ""

    # 删除URL
    text = re.sub(r"https?://\S+", "", text)

    # 删除HTML标签
    text = re.sub(r"<.*?>", "", text)

    # 删除特殊符号（保留基本标点）
    text = re.sub(
        r'[^\w\s,.;:!?()[\]{}\'\"，。；：！？（）【】「」""' "]",
        "",
        text,
        flags=re.UNICODE,
    )

    return text.strip()


def detect_language(text):
    """使用lingua库检测文本语言"""
    if not text:
        return "unknown"

    # 确保输入是字符串
    if not isinstance(text, (str, bytes)):
        try:
            text = str(text)
        except:
            return "unknown"

    if len(str(text).strip()) < 10:
        return "unknown"

    processed_text = preprocess_text_for_detection(text)
    if not processed_text:
        return "unknown"

    try:
        # 尝试先从文本和内容结合检测，提高准确性
        if hasattr(text, "title") and hasattr(text, "content"):
            combined_text = f"{text.title} {text.content[:1000]}"
            combined_text = preprocess_text_for_detection(combined_text)
            if combined_text:
                lingua_result = language_detector.detect_language_of(combined_text)
                if lingua_result:
                    return lingua_result.iso_code_639_1.name.lower()

        # 单独检测提供的文本
        lingua_result = language_detector.detect_language_of(processed_text)
        if lingua_result:
            detected_lang = lingua_result.iso_code_639_1.name.lower()
            return detected_lang

        # 如果lingua未检测出结果
        logger.warning("lingua未能检测出语言")
        return "unknown"

    except Exception as e:
        logger.error(f"语言检测失败: {str(e)}")
        return "unknown"


def convert_completion_usage_to_dict(usage):
    """
    将CompletionUsage对象转换为普通字典，只提取实际的tokens计数值
    """
    if not usage:
        return None

    # 如果是字典类型，清理非必要字段
    if isinstance(usage, dict):
        # 只保留重要的token计数字段
        clean_dict = {}
        # 基本token计数
        if "completion_tokens" in usage:
            clean_dict["completion_tokens"] = usage["completion_tokens"]
        if "prompt_tokens" in usage:
            clean_dict["prompt_tokens"] = usage["prompt_tokens"]
        if "total_tokens" in usage:
            clean_dict["total_tokens"] = usage["total_tokens"]

        # 处理completion_tokens_details
        if "completion_tokens_details" in usage and usage["completion_tokens_details"]:
            details = usage["completion_tokens_details"]
            if isinstance(details, dict):
                clean_details = {}
                for key in [
                    "reasoning_tokens",
                    "accepted_prediction_tokens",
                    "rejected_prediction_tokens",
                ]:
                    if key in details and details[key] is not None:
                        clean_details[key] = details[key]
                if clean_details:
                    clean_dict["completion_tokens_details"] = clean_details

        # 处理prompt_tokens_details
        if "prompt_tokens_details" in usage and usage["prompt_tokens_details"]:
            details = usage["prompt_tokens_details"]
            if isinstance(details, dict):
                clean_details = {}
                for key in ["audio_tokens", "cached_tokens"]:
                    if key in details and details[key] is not None:
                        clean_details[key] = details[key]
                if clean_details:
                    clean_dict["prompt_tokens_details"] = clean_details

        return clean_dict

    # 如果是对象（如CompletionUsage）
    if hasattr(usage, "__dict__"):
        # 创建一个基本字典
        clean_dict = {}

        # 提取基本token计数
        for key in ["completion_tokens", "prompt_tokens", "total_tokens"]:
            if hasattr(usage, key):
                value = getattr(usage, key)
                if value is not None:
                    clean_dict[key] = value

        # 提取completion_tokens_details
        if hasattr(usage, "completion_tokens_details") and getattr(
            usage, "completion_tokens_details"
        ):
            details = getattr(usage, "completion_tokens_details")
            clean_details = {}
            for key in [
                "reasoning_tokens",
                "accepted_prediction_tokens",
                "rejected_prediction_tokens",
            ]:
                if hasattr(details, key):
                    value = getattr(details, key)
                    if value is not None:
                        clean_details[key] = value
            if clean_details:
                clean_dict["completion_tokens_details"] = clean_details

        # 提取prompt_tokens_details
        if hasattr(usage, "prompt_tokens_details") and getattr(
            usage, "prompt_tokens_details"
        ):
            details = getattr(usage, "prompt_tokens_details")
            clean_details = {}
            for key in ["audio_tokens", "cached_tokens"]:
                if hasattr(details, key):
                    value = getattr(details, key)
                    if value is not None:
                        clean_details[key] = value
            if clean_details:
                clean_dict["prompt_tokens_details"] = clean_details

        return clean_dict

    # 如果既不是字典也不是含有__dict__的对象，返回None
    return None


def translate_to_chinese(text, source_lang):
    """将文本翻译为中文"""
    if not text:
        return "", None

    # 如果已经是中文，则直接返回
    if source_lang == "zh" or source_lang.startswith("zh-"):
        return text, None

    # 如果是未知语言，尝试使用OpenAI直接翻译
    try:
        response = openai_client.chat.completions.create(
            model=translation_model,  # 使用专门的翻译模型
            messages=[
                {
                    "role": "system",
                    "content": """你是一名多语翻译专家，擅长将{{from_lang}}内容地道自然地翻译成流畅{{to_lang}}。译文应忠实原意，语言表达符合{{to_lang}}习惯，不带翻译腔的母语级别，风格口吻贴合上下文场景。

翻译原则：

- 按文本类型调整语气风格：技术/文档用语严谨，论坛/评论风格口语
- 按需调整语序，使语言更符合{{to_lang}}表达逻辑
- 用词流畅，本地化表达，恰当使用成语、流行语等{{to_lang}}特色词语和句式
- 直接给我翻译结果，不添加任何说明！！！

输出规范（绝对遵守）：，不添加任何说明、注释、标记或原文。""".replace(
                        "{{from_lang}}", source_lang
                    ).replace(
                        "{{to_lang}}", "中文"
                    ),
                },
                {
                    "role": "user",
                    "content": f"请将以下文本翻译成中文，保持专业性：\n\n{text}",
                },
            ],
            temperature=0.3,
        )

        # 记录tokens使用情况
        tokens_usage = None
        if hasattr(response, "usage") and response.usage:
            tokens_usage = convert_completion_usage_to_dict(response.usage)
            # logger.info(f"翻译tokens使用: {tokens_usage}")

        return response.choices[0].message.content, tokens_usage
    except Exception as e:
        logger.error(f"翻译失败: {str(e)}")
        return text, None


def extract_entities(content):
    """从内容中提取实体"""
    try:
        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的实体提取助手。请从文本中提取关键实体信息，包括组织、人物、产品、技术、漏洞、攻击方式等。为每个实体提供类型和值。",
                },
                {
                    "role": "user",
                    "content": f"请从以下网络安全新闻中提取关键实体，返回标准格式的JSON数组。每个实体包含'type'和'value'两个字段。例如:[{{'type':'组织','value':'微软'}},{{'type':'漏洞','value':'CVE-2023-1234'}}]。请至少提取5个实体：\n\n{content}",
                },
            ],
            temperature=0.3,
        )

        # 记录tokens使用情况
        tokens_usage = None
        if hasattr(response, "usage") and response.usage:
            tokens_usage = convert_completion_usage_to_dict(response.usage)
            logger.info(f"实体提取tokens使用: {tokens_usage}")

        result = response.choices[0].message.content
        logger.info(f"实体提取返回结果: {result[:100]}...")

        # 处理返回的JSON
        try:
            # 使用通用解析函数
            parsed_result = parse_llm_response(result, expected_format="json")
            if parsed_result is None:
                return [{"type": "error", "value": "无法解析实体JSON"}], tokens_usage

            # 确保entities是数组格式
            entities = parsed_result
            if not isinstance(entities, list):
                # 如果是对象，尝试转换为数组格式
                if isinstance(entities, dict):
                    # 情况1: {"entities": [...]} 格式
                    if "entities" in entities and isinstance(
                        entities["entities"], list
                    ):
                        entities = entities["entities"]
                    # 情况2: {"entity1": "value1", "entity2": "value2"} 格式
                    else:
                        transformed = []
                        for entity_type, entity_value in entities.items():
                            if entity_type != "error":
                                transformed.append(
                                    {"type": entity_type, "value": entity_value}
                                )
                        entities = transformed

            # 标准化实体数组中的每个对象，确保都有type和value字段
            standardized_entities = []
            for entity in entities:
                if isinstance(entity, dict):
                    if "type" in entity and "value" in entity:
                        standardized_entities.append(
                            {"type": entity["type"], "value": entity["value"]}
                        )
                    elif len(entity) == 1:
                        # 处理 {"组织": "微软"} 格式
                        for entity_type, entity_value in entity.items():
                            standardized_entities.append(
                                {"type": entity_type, "value": entity_value}
                            )
                elif isinstance(entity, str):
                    # 处理纯字符串格式
                    standardized_entities.append({"type": "关键词", "value": entity})

            return standardized_entities, tokens_usage
        except Exception as e:
            logger.error(f"解析实体结果失败: {str(e)}")
            return [{"type": "error", "value": f"解析失败: {str(e)}"}], tokens_usage
    except Exception as e:
        logger.error(f"提取实体失败: {str(e)}")
        return [{"type": "error", "value": f"API调用失败: {str(e)}"}], None


def categorize_news(title, content):
    """对新闻进行分类"""
    try:
        # 准备分类描述
        category_desc = {
            "金融业网络安全事件": "与金融行业相关的网络安全事件",
            "重大网络安全事件": "具有广泛影响的重大网络安全事件",
            "重大数据泄露事件": "涉及数据泄露的安全事件",
            "重大漏洞风险提示": "关于软件、系统漏洞的风险提示",
            "其他": "不属于上述类别的其他网络安全新闻",
        }

        # 拼接所有分类描述为一个提示文本
        categories_prompt = "\n".join(
            [f"- {key}: {value}" for key, value in category_desc.items()]
        )

        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": f"你是一个网络安全新闻分类专家，请根据文本内容将新闻分为以下类别之一：\n{categories_prompt}",
                },
                {
                    "role": "user",
                    "content": f"请将以下网络安全新闻分类为上述类别之一，只返回类别名称，不需要解释：\n标题：{title}\n\n内容：{content[:1000]}",
                },
            ],
            temperature=0.3,
        )

        # 记录tokens使用情况
        tokens_usage = None
        if hasattr(response, "usage") and response.usage:
            tokens_usage = convert_completion_usage_to_dict(response.usage)
            logger.info(f"分类tokens使用: {tokens_usage}")

        result = response.choices[0].message.content.strip()

        # 映射到枚举类型
        category_mapping = {
            "金融业网络安全事件": NewsCategory.FINANCIAL,
            "重大网络安全事件": NewsCategory.MAJOR,
            "重大数据泄露事件": NewsCategory.DATA_LEAK,
            "重大漏洞风险提示": NewsCategory.VULNERABILITY,
            "其他": NewsCategory.OTHER,
        }

        # 找到最匹配的分类
        for key in category_mapping.keys():
            if key in result:
                return category_mapping[key], tokens_usage

        # 默认分类
        return NewsCategory.OTHER, tokens_usage
    except Exception as e:
        logger.error(f"分类失败: {str(e)}")
        return NewsCategory.OTHER, None


def summarize_article(content):
    """生成文章的详细总结"""
    if not content or len(content) < 100:
        return content, None

    try:
        # 截断过长的内容
        max_length = 4000
        if len(content) > max_length:
            # 保留开头和结尾，截断中间部分
            trimmed_content = (
                content[: max_length // 2]
                + f"\n\n[内容过长，已截断约{len(content) - max_length}字符]\n\n"
                + content[-max_length // 2 :]
            )
            logger.info(
                f"内容已截断：原始长度{len(content)}字符，截断后{len(trimmed_content)}字符"
            )
            content = trimmed_content

        response = openai_client.chat.completions.create(
            model=summarization_model,  # 使用专门的总结模型
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的网络安全新闻编辑，擅长制作网络安全事件的新闻总结。你的工作是把助手找来的事件内容总结成一段文字，不要给我任何解释，直接给我一段总结性文字，所有总结内容都在一个自然段里。这段总结会直接刊登在网站上，所以请用中文写，不要用英文。不要使用“本文描述了”等开头，呈现给用户的是一个完整的新闻总结。",
                },
                {
                    "role": "user",
                    "content": f"""请对以下网络安全新闻内容生成一个详细的新闻总结，直接给我一段总结性文字，总结需包含以下部分：
1. 事件概述（简明扼要描述事件要点）
2. 技术细节（如有，列出技术要点，漏洞信息，攻击方式等）
3. 影响范围（如有，描述受影响的组织、系统或用户）
4. 安全建议（如有，提供相关的安全防范措施）

# 注意事项
1. 直接输出综述内容，不要加入任何与综述无关的回应性语句
2. 保持专业的编辑视角，注重新闻价值的提炼
3. 不要给我任何解释，你的回复就是一段总结性文字，所有总结内容都在一个自然段里。

原文内容：
{content}""",
                },
            ],
            temperature=0.2,
        )

        # 记录tokens使用情况
        tokens_usage = None
        if hasattr(response, "usage") and response.usage:
            tokens_usage = convert_completion_usage_to_dict(response.usage)
            logger.info(f"文章总结tokens使用: {tokens_usage}")

        summary = response.choices[0].message.content

        return summary, tokens_usage
    except Exception as e:
        logger.error(f"生成文章总结失败: {str(e)}")
        return "", None


def ensure_serializable(data):
    """
    递归处理数据，确保所有内容都是可JSON序列化的。
    将不可序列化的对象转换为字符串或过滤掉。
    """
    if data is None:
        return None

    # 基本类型直接返回
    if isinstance(data, (str, int, float, bool)):
        return data

    # 处理列表
    if isinstance(data, list):
        return [ensure_serializable(item) for item in data]

    # 处理字典
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            # 跳过类似'model_'开头的Pydantic内部字段
            if isinstance(key, str) and (
                key.startswith("model_") or key == "model_computed_fields"
            ):
                continue

            # 递归处理值
            serialized_value = ensure_serializable(value)
            if serialized_value is not None:
                result[key] = serialized_value
        return result

    # 尝试将对象转换为字典
    if hasattr(data, "__dict__"):
        obj_dict = {}
        for key, value in data.__dict__.items():
            # 跳过私有属性和Pydantic内部字段
            if key.startswith("_") or key.startswith("model_"):
                continue
            serialized_value = ensure_serializable(value)
            if serialized_value is not None:
                obj_dict[key] = serialized_value
        return obj_dict

    # 其他情况尝试转换为字符串
    try:
        return str(data)
    except:
        return None


def process_news(news_item: News, db: Session = None):
    """处理新闻文章，生成标题、摘要、分类和实体"""
    logger.info(f"开始处理新闻: ID {news_item.id}, 标题: {news_item.title}")

    # 初始化tokens使用统计
    tokens_usage_stats = {}

    # 获取新闻源配置
    source = None
    if db and news_item.source_id:
        from app.models.source import Source

        source = db.query(Source).filter(Source.id == news_item.source_id).first()

    # 检测语言
    logger.info(f"检测文章语言...")
    original_language = detect_language(news_item.title)
    news_item.original_language = original_language
    logger.info(f"检测到语言: {original_language}")

    # 翻译（如果不是中文）
    translated_content = news_item.content
    translated_title = news_item.title
    generated_summary = ""
    article_summary = ""
    summary_source = "generated"

    if original_language != "zh" and not original_language.startswith("zh-"):
        logger.info(f"翻译内容（从 {original_language} 到中文）...")

        # 直接翻译标题
        translated_title, title_tokens = translate_to_chinese(
            news_item.title, original_language
        )
        if title_tokens:
            tokens_usage_stats["title_translation"] = title_tokens
        logger.info(f"标题翻译完成: {translated_title[:30]}...")

        # 检查是否有预先提取的摘要，并判断其质量
        # 同时检查源配置是否允许使用RSS摘要
        has_quality_summary = False
        use_rss_summary = True  # 默认使用RSS摘要

        if source and hasattr(source, "use_rss_summary"):
            use_rss_summary = source.use_rss_summary
            logger.info(f"源配置: use_rss_summary = {use_rss_summary}")

        if (
            use_rss_summary
            and hasattr(news_item, "summary")
            and news_item.summary
            and len(news_item.summary.strip()) > 100
            and "..." not in news_item.summary.strip()
        ):
            # 认为长度超过100的摘要可能有足够信息量
            has_quality_summary = True
            logger.info(
                "检测到高质量摘要且源配置允许使用RSS摘要，将只翻译摘要不翻译全文"
            )

            # 翻译摘要
            translated_summary, summary_tokens = translate_to_chinese(
                news_item.summary, original_language
            )
            if summary_tokens:
                tokens_usage_stats["summary_translation"] = summary_tokens
            generated_summary = translated_summary
            article_summary = translated_summary
            summary_source = "original"  # 标记为原文摘要
            logger.info(f"摘要翻译完成，长度: {len(translated_summary)} 字符")

            # 摘要内容加入到translated_content供实体提取和分类使用
            # 但不替换原始内容，以保留完整信息
            translated_content = f"{translated_title}\n\n{translated_summary}"
        else:
            # 如果没有高质量摘要或源配置不允许使用RSS摘要，则翻译全文
            if not use_rss_summary:
                logger.info("源配置不允许使用RSS摘要，将翻译全文并生成摘要")
            else:
                logger.info("未检测到高质量摘要，将翻译全文")
            translated_content_result, content_tokens = translate_to_chinese(
                news_item.content, original_language
            )
            if content_tokens:
                tokens_usage_stats["content_translation"] = content_tokens
            translated_content = translated_content_result
            logger.info("全文翻译完成")

            # 生成文章详细总结
            logger.info(f"生成文章总结...")
            article_summary_result, summary_tokens = summarize_article(
                translated_content
            )
            if summary_tokens:
                tokens_usage_stats["article_summary"] = summary_tokens
            article_summary = article_summary_result
            generated_summary = article_summary_result
            summary_source = "generated"  # 标记为生成的总结
            logger.info(f"总结生成完成，长度: {len(article_summary)} 字符")
    else:
        # 中文内容不需要翻译，直接进行总结
        logger.info("内容为中文，无需翻译")

        # 检查是否有预先提取的摘要以及源配置
        use_rss_summary = True  # 默认使用RSS摘要

        if source and hasattr(source, "use_rss_summary"):
            use_rss_summary = source.use_rss_summary
            logger.info(f"源配置: use_rss_summary = {use_rss_summary}")

        if (
            use_rss_summary
            and hasattr(news_item, "summary")
            and news_item.summary
            and len(news_item.summary.strip()) > 50
        ):
            logger.info("使用现有摘要作为总结")
            article_summary = news_item.summary
            generated_summary = news_item.summary
            summary_source = "original"  # 标记为原文摘要
        else:
            # 生成文章详细总结
            if not use_rss_summary:
                logger.info("源配置不允许使用RSS摘要，将生成新摘要")
            else:
                logger.info("未检测到高质量摘要，将生成新摘要")
            logger.info(f"生成文章总结...")
            article_summary_result, summary_tokens = summarize_article(
                translated_content
            )
            if summary_tokens:
                tokens_usage_stats["article_summary"] = summary_tokens
            article_summary = article_summary_result
            generated_summary = (
                article_summary[:300] if len(article_summary) > 300 else article_summary
            )
            summary_source = "generated"  # 标记为生成的总结
            logger.info(f"总结生成完成，长度: {len(article_summary)} 字符")
            news_item.is_processed = True

    # 分类
    logger.info(f"对文章进行分类...")
    category, category_tokens = categorize_news(translated_title, translated_content)
    if category_tokens:
        tokens_usage_stats["category"] = category_tokens
    logger.info(f"分类结果: {category.value}")

    # 提取实体
    logger.info(f"提取实体信息...")
    entities, entity_tokens = extract_entities(translated_content)
    if entity_tokens:
        tokens_usage_stats["entities"] = entity_tokens
    entity_count = len(entities) if isinstance(entities, list) else 0
    logger.info(f"提取到 {entity_count} 个实体")

    # 确保tokens_usage_stats可序列化
    serializable_tokens_usage = {}
    for key, usage in tokens_usage_stats.items():
        # 获取清理过的数据
        clean_usage = convert_completion_usage_to_dict(usage)
        # 额外确保可序列化
        serializable_tokens_usage[key] = ensure_serializable(clean_usage)

    # 计算总tokens使用量和分别的输入、输出tokens
    total_tokens = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    
    for usage_type, usage_data in serializable_tokens_usage.items():
        if usage_data and isinstance(usage_data, dict):
            if "total_tokens" in usage_data:
                total_tokens += usage_data["total_tokens"]
            if "prompt_tokens" in usage_data:
                total_prompt_tokens += usage_data["prompt_tokens"]
            if "completion_tokens" in usage_data:
                total_completion_tokens += usage_data["completion_tokens"]

    logger.info(f"tokens使用量统计 - 总计: {total_tokens}, 输入: {total_prompt_tokens}, 输出: {total_completion_tokens}")

    # 更新新闻对象
    news_item.generated_title = translated_title  # 使用翻译后的标题作为生成标题
    news_item.generated_summary = generated_summary
    news_item.article_summary = article_summary
    news_item.summary_source = summary_source  # 设置摘要来源
    news_item.category = category
    news_item.entities = entities
    news_item.is_processed = True
    news_item.tokens_usage = serializable_tokens_usage

    # 更新订阅源的token使用统计
    if db and source and total_tokens > 0:
        logger.info(f"更新源ID {source.id} 的token使用统计...")
        
        # 累计总token使用量
        if hasattr(source, "tokens_used") and source.tokens_used is not None:
            source.tokens_used += total_tokens
        else:
            source.tokens_used = total_tokens
            
        # 累计输入token使用量
        if hasattr(source, "prompt_tokens") and source.prompt_tokens is not None:
            source.prompt_tokens += total_prompt_tokens
        else:
            source.prompt_tokens = total_prompt_tokens
            
        # 累计输出token使用量
        if hasattr(source, "completion_tokens") and source.completion_tokens is not None:
            source.completion_tokens += total_completion_tokens
        else:
            source.completion_tokens = total_completion_tokens
            
        logger.info(f"源ID {source.id} 的累计token使用量 - 总计: {source.tokens_used}, 输入: {source.prompt_tokens}, 输出: {source.completion_tokens}")

    # 如果提供了数据库会话，则保存更改
    if db:
        logger.info(f"保存处理结果到数据库...")
        db.commit()
        logger.info(f"新闻处理完成: ID {news_item.id}")

    return news_item


def generate_event_name(primary_title: str, related_titles: List[str], entities: Dict[str, set]) -> Tuple[str, Optional[Dict]]:
    """为事件组生成合适的事件名称"""
    try:
        # 构建实体信息字符串
        entity_info = ""
        if entities:
            key_entities = []
            for entity_type in ['CVE', '漏洞', '组织', '受害者', '产品', '攻击者']:
                if entity_type in entities and entities[entity_type]:
                    key_entities.extend(list(entities[entity_type])[:2])  # 每种类型最多取2个
            
            if key_entities:
                entity_info = f"关键实体: {', '.join(key_entities[:5])}"  # 最多显示5个实体
        
        # 构建相关标题列表
        all_titles = [primary_title] + related_titles[:3]  # 最多使用4个标题
        titles_text = "\n".join([f"- {title}" for title in all_titles])
        
        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": """你是一个专业的新闻编辑，擅长为网络安全事件生成简洁准确的事件标题。
要求：
1. 事件名称要简洁明了，不超过20个字符
2. 突出事件的核心要素（如受影响组织、漏洞类型、攻击类型等）
3. 避免使用"事件"、"新闻"等冗余词汇
4. 如果涉及CVE漏洞，优先在名称中体现

必须遵守：直接回复我事件名称，不要任何过程的解释和解读"""
                },
                {
                    "role": "user",
                    "content": f"""基于以下相关新闻标题和实体信息，生成一个简洁的事件名称：

新闻标题：
{titles_text}

{entity_info}

请生成一个简洁的事件名称："""
                }
            ],
            temperature=0.3,
            max_tokens=50
        )
        
        # 记录tokens使用情况
        tokens_usage = None
        if hasattr(response, "usage") and response.usage:
            tokens_usage = convert_completion_usage_to_dict(response.usage)
        
        event_name = response.choices[0].message.content.strip()
        
        # 清理事件名称，移除引号和多余空格
        event_name = event_name.strip('"').strip("'").strip()
        
        return event_name, tokens_usage
        
    except Exception as e:
        logger.error(f"生成事件名称失败: {str(e)}")
        # 返回默认名称
        if entities.get('CVE'):
            return f"漏洞 {list(entities['CVE'])[0]}", None
        elif entities.get('受害者'):
            return f"{list(entities['受害者'])[0]} 安全事件", None
        elif entities.get('组织'):
            return f"{list(entities['组织'])[0]} 相关事件", None
        else:
            return "网络安全事件", None

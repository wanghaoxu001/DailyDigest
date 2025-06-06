import logging
import nltk

# 获取日志记录器
from app.config import get_logger
logger = get_logger(__name__)


# 初始化NLTK资源
def init_nltk_resources():
    """初始化和检查必要的NLTK资源"""
    nltk_resources = [
        "punkt",  # 用于标记化
        "punkt_tab",  # 标记化相关
        "stopwords",  # 停用词
        "wordnet",  # 词义词典
        "averaged_perceptron_tagger",  # 词性标注
    ]

    for resource in nltk_resources:
        try:
            if resource.startswith("punkt"):
                # punkt相关资源在tokenizers目录下
                nltk.data.find(f"tokenizers/{resource}")
            else:
                # 其他资源在corpora目录下
                nltk.data.find(f"corpora/{resource}")
            logger.info(f"NLTK资源 {resource} 已存在")
        except LookupError:
            logger.info(f"正在下载NLTK资源 {resource}...")
            try:
                nltk.download(resource)
                logger.info(f"NLTK资源 {resource} 下载完成")
            except Exception as e:
                logger.warning(f"下载NLTK资源 {resource} 失败: {str(e)}")


# 应用启动时初始化NLTK资源
try:
    init_nltk_resources()
except Exception as e:
    logger.error(f"初始化NLTK资源时出错: {str(e)}")
    # 即使NLTK资源初始化失败，也不要阻止应用启动

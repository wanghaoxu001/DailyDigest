"""
数据库迁移：添加新闻相似度存储表
用于预计算和存储文章相似关系，提高前端响应速度
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


def upgrade():
    """创建相似度相关表"""
    
    # 创建新闻相似度关系表
    op.create_table(
        'news_similarity',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('news_id_1', sa.Integer(), nullable=False, comment='新闻1的ID'),
        sa.Column('news_id_2', sa.Integer(), nullable=False, comment='新闻2的ID'),
        sa.Column('similarity_score', sa.Float(), nullable=False, comment='综合相似度分数(0-1)'),
        sa.Column('entity_similarity', sa.Float(), default=0.0, comment='实体相似度分数'),
        sa.Column('text_similarity', sa.Float(), default=0.0, comment='文本相似度分数'),
        sa.Column('group_id', sa.String(50), nullable=True, comment='事件分组ID'),
        sa.Column('is_same_event', sa.Boolean(), default=False, comment='是否为同一事件'),
        sa.Column('calculation_version', sa.String(20), default='v1.0', comment='计算算法版本'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建索引
    op.create_index('ix_news_similarity_pair', 'news_similarity', ['news_id_1', 'news_id_2'], unique=True)
    op.create_index('ix_news_similarity_score', 'news_similarity', ['similarity_score'])
    op.create_index('ix_news_similarity_group', 'news_similarity', ['group_id'])
    op.create_index('ix_news_similarity_created_at', 'news_similarity', ['created_at'])
    op.create_index('ix_news_similarity_news1_score', 'news_similarity', ['news_id_1', 'similarity_score'])
    op.create_index('ix_news_similarity_news2_score', 'news_similarity', ['news_id_2', 'similarity_score'])
    
    # 创建新闻事件分组表
    op.create_table(
        'news_event_groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.String(50), nullable=False, comment='事件分组唯一ID'),
        sa.Column('event_label', sa.String(500), nullable=False, comment='事件标签/标题'),
        sa.Column('primary_news_id', sa.Integer(), nullable=False, comment='主要新闻ID'),
        sa.Column('news_count', sa.Integer(), default=1, comment='包含的新闻数量'),
        sa.Column('sources_count', sa.Integer(), default=1, comment='涉及的新闻源数量'),
        sa.Column('key_entities', sa.Text(), nullable=True, comment='关键实体信息(JSON)'),
        sa.Column('similarity_threshold', sa.Float(), default=0.75, comment='使用的相似度阈值'),
        sa.Column('calculation_version', sa.String(20), default='v1.0', comment='计算算法版本'),
        sa.Column('earliest_news_time', sa.DateTime(timezone=True), nullable=True, comment='最早新闻时间'),
        sa.Column('latest_news_time', sa.DateTime(timezone=True), nullable=True, comment='最新新闻时间'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建索引
    op.create_index('ix_news_event_groups_group_id', 'news_event_groups', ['group_id'], unique=True)
    op.create_index('ix_news_event_groups_primary_news', 'news_event_groups', ['primary_news_id'])
    op.create_index('ix_news_event_groups_created_at', 'news_event_groups', ['created_at'])
    op.create_index('ix_news_event_groups_news_count', 'news_event_groups', ['news_count'])
    
    # 创建新闻分组成员关系表
    op.create_table(
        'news_group_membership',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.String(50), nullable=False, comment='事件分组ID'),
        sa.Column('news_id', sa.Integer(), nullable=False, comment='新闻ID'),
        sa.Column('is_primary', sa.Boolean(), default=False, comment='是否为主要新闻'),
        sa.Column('similarity_to_primary', sa.Float(), default=0.0, comment='与主要新闻的相似度'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建索引
    op.create_index('ix_news_group_membership_unique', 'news_group_membership', ['group_id', 'news_id'], unique=True)
    op.create_index('ix_news_group_membership_group', 'news_group_membership', ['group_id'])
    op.create_index('ix_news_group_membership_news', 'news_group_membership', ['news_id'])
    op.create_index('ix_news_group_membership_primary', 'news_group_membership', ['is_primary'])


def downgrade():
    """删除相似度相关表"""
    
    # 删除索引
    op.drop_index('ix_news_group_membership_primary')
    op.drop_index('ix_news_group_membership_news')
    op.drop_index('ix_news_group_membership_group')
    op.drop_index('ix_news_group_membership_unique')
    
    op.drop_index('ix_news_event_groups_news_count')
    op.drop_index('ix_news_event_groups_created_at')
    op.drop_index('ix_news_event_groups_primary_news')
    op.drop_index('ix_news_event_groups_group_id')
    
    op.drop_index('ix_news_similarity_news2_score')
    op.drop_index('ix_news_similarity_news1_score')
    op.drop_index('ix_news_similarity_created_at')
    op.drop_index('ix_news_similarity_group')
    op.drop_index('ix_news_similarity_score')
    op.drop_index('ix_news_similarity_pair')
    
    # 删除表
    op.drop_table('news_group_membership')
    op.drop_table('news_event_groups')
    op.drop_table('news_similarity') 
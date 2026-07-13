"""KOL Profile 管理相关 Schema。

跨平台 KOL 身份管理，用于追踪同一 KOL 在不同平台的账号。

Trading style profile（交易风格画像）为双层结构：
- DeclaredTradingStyle：人工标注层（configs/creators/*.yaml 的 trading_style 块）
- ObservedTradingStyle：观测层（从 F5 TradeAction 统计聚合）
前端以「自述 vs 实际行为」对照展示两层。
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ENTRY_STYLE_LITERAL = Literal["left_side", "right_side", "mixed", "unknown"]


class PlatformIdentity(BaseModel):
    """平台身份信息。"""

    platform: str = Field(
        ...,
        description="平台标识：wechat, bilibili, feishu, twitter, weibo 等",
    )
    account_id: str = Field(
        ...,
        description="平台账号唯一标识",
    )
    account_name: Optional[str] = Field(
        default=None,
        description="账号显示名称",
    )
    avatar_url: Optional[str] = Field(
        default=None,
        description="头像 URL",
    )
    verified: bool = Field(
        default=False,
        description="是否已认证",
    )
    follower_count: Optional[int] = Field(
        default=None,
        description="粉丝数",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="平台特有元数据",
    )


class KOLProfile(BaseModel):
    """KOL 全局档案。"""

    kol_id: str = Field(
        ...,
        description="全局唯一 KOL ID，格式：kol_{uuid}",
    )
    display_name: str = Field(
        ...,
        description="显示名称",
    )
    platform_identities: list[PlatformIdentity] = Field(
        default_factory=list,
        description="各平台身份列表",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="标签：如 crypto, macro, tech",
    )
    rating: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=5.0,
        description="综合评分（0-5）",
    )
    bio: Optional[str] = Field(
        default=None,
        description="简介",
    )
    created_at: datetime = Field(
        ...,
        description="创建时间",
    )
    updated_at: datetime = Field(
        ...,
        description="最后更新时间",
    )

    def get_platform_identity(self, platform: str) -> Optional[PlatformIdentity]:
        """获取指定平台的身份信息。"""
        for identity in self.platform_identities:
            if identity.platform == platform:
                return identity
        return None

    def has_platform(self, platform: str) -> bool:
        """检查是否已关联某平台。"""
        return self.get_platform_identity(platform) is not None


class DeclaredTradingStyle(BaseModel):
    """人工标注的 KOL 交易风格（declared 层）。

    三态语义：None = 未标注（不知道），False = 明确不用，True = 明确使用。
    数据来源是 configs/creators/*.yaml 的 ``trading_style:`` 块。
    """

    uses_margin: Optional[bool] = Field(
        default=None,
        description="是否使用融资（两融）；None=未标注",
    )
    uses_leverage: Optional[bool] = Field(
        default=None,
        description="是否使用杠杆（合约/期货/倍数杠杆）；None=未标注",
    )
    does_short: Optional[bool] = Field(
        default=None,
        description="是否做空；None=未标注",
    )
    entry_style: ENTRY_STYLE_LITERAL = Field(
        default="unknown",
        description="入场风格：left_side=左侧（抄底/越跌越买），"
                    "right_side=右侧（突破追入/趋势确认），mixed=兼有",
    )
    evidence_notes: list[str] = Field(
        default_factory=list,
        description="标注依据（如：直播中自述从不融资）",
    )


class ObservedTradingStyle(BaseModel):
    """从 F5 TradeAction 统计聚合出的 KOL 交易风格（observed 层）。"""

    sample_size: int = Field(
        ...,
        ge=0,
        description="参与统计的该 KOL 归属 action 总数",
    )
    directional_sample_size: int = Field(
        ...,
        ge=0,
        description="方向性 action 数（primary step 非 HOLD/WATCH）",
    )
    short_side_count: int = Field(
        default=0,
        ge=0,
        description="空头侧 action 数（SHORT/CLOSE_SHORT/BUY_PUT/SELL_CALL）",
    )
    short_ratio: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="空头侧占方向性 action 的比例；无方向性样本时为 None",
    )
    margin_mention_count: int = Field(
        default=0,
        ge=0,
        description="提及融资的 action 数（metadata.margin_flag == true）",
    )
    leverage_mention_count: int = Field(
        default=0,
        ge=0,
        description="提及杠杆的 action 数（metadata.leverage_flag == true）",
    )
    left_side_count: int = Field(
        default=0,
        ge=0,
        description="左侧入场语义的 action 数（metadata.entry_timing_style）",
    )
    right_side_count: int = Field(
        default=0,
        ge=0,
        description="右侧入场语义的 action 数（metadata.entry_timing_style）",
    )
    entry_style_observed: ENTRY_STYLE_LITERAL = Field(
        default="unknown",
        description="多数决判定的入场风格：n>=5 且占比>=60% 判该侧；"
                    "两侧都显著为 mixed；否则 unknown",
    )
    entry_style_sample_size: int = Field(
        default=0,
        ge=0,
        description="携带左/右侧语义信号的 action 数",
    )
    low_sample: bool = Field(
        default=True,
        description="方向性样本不足（directional_sample_size < 5）",
    )
    computed_at: datetime = Field(
        ...,
        description="统计计算时间",
    )
    window_label: str = Field(
        default="ALL",
        description="统计窗口标签（v1 恒为 ALL 全历史）",
    )


class TradingStyleProfile(BaseModel):
    """KOL 交易风格画像：declared + observed 双层容器。"""

    creator_id: str = Field(
        ...,
        description="creator/KOL 标识",
    )
    display_name: Optional[str] = Field(
        default=None,
        description="显示名称（来自 creator 配置）",
    )
    declared: Optional[DeclaredTradingStyle] = Field(
        default=None,
        description="人工标注层；无 YAML 或无 trading_style 块时为 None",
    )
    observed: Optional[ObservedTradingStyle] = Field(
        default=None,
        description="观测层；该 KOL 无归属 action 数据时为 None",
    )


class CreatorProfile(BaseModel):
    """configs/creators/{creator_id}.yaml 的注册表档案。

    文件即真相源：KOLRegistry（services/kol_registry.py）只读加载本模型，
    TTL 到期自动重读——改档案 = 改 YAML，无写 API。主键 creator_id 与
    文件名 stem 一致（人类可读串，非 KOLProfileManager 的 kol_{uuid} 体系）。
    """

    model_config = ConfigDict(extra="ignore")

    creator_id: str = Field(
        ...,
        description="全系统人类可读主键；必须与 YAML 文件名 stem 一致",
    )
    display_name: Optional[str] = Field(
        default=None,
        description="产品展示名；缺省时消费方回退 creator_id",
    )
    handle: Optional[str] = Field(
        default=None,
        description="社媒昵称；缺省回退 display_name",
    )
    style_label: Optional[str] = Field(
        default=None,
        description="产品风格标签（radar 卡片展示，如「个股短线」）；未知留空",
    )
    specialties: list[str] = Field(
        default_factory=list,
        description="擅长领域标签（如 半导体、恒生科技）",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="指向该 creator 的一切别名：中文名、hashtag、历史 canonical id",
    )
    platforms: list[str] = Field(
        default_factory=list,
        description="内容来源平台：bilibili / feishu / wechat / image_upload 等",
    )
    platform_identities: list[PlatformIdentity] = Field(
        default_factory=list,
        description="平台账号身份（registry.resolve 的 {platform}:{account_id} 索引）",
    )
    content_types: list[str] = Field(
        default_factory=list,
        description="内容类型：weekly_strategy / daily_pre / chat_export 等",
    )
    markets: list[str] = Field(
        default_factory=list,
        description="覆盖市场：US / HK / A",
    )
    focus: list[str] = Field(
        default_factory=list,
        description="重点维度：sector / theme / single_stock",
    )
    default_horizons: list[str] = Field(
        default_factory=list,
        description="默认时间周期：daily / weekly / swing",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="备注（含建档来源与待补标记）",
    )
    trading_style: Optional[DeclaredTradingStyle] = Field(
        default=None,
        description="declared 交易风格标注；块缺失或无效均为 None（未标注）",
    )
    enabled: bool = Field(
        default=True,
        description="false = list 默认隐藏（档案保留，soft-off）",
    )


class KOLProfileCreate(BaseModel):
    """创建 KOL Profile 请求。"""

    display_name: str = Field(..., description="显示名称")
    platform: str = Field(..., description="初始平台")
    account_id: str = Field(..., description="平台账号 ID")
    account_name: Optional[str] = Field(default=None, description="账号名称")
    avatar_url: Optional[str] = Field(default=None, description="头像 URL")
    tags: list[str] = Field(default_factory=list, description="初始标签")
    bio: Optional[str] = Field(default=None, description="简介")


class PlatformLink(BaseModel):
    """平台关联请求。"""

    platform: str = Field(..., description="平台标识")
    account_id: str = Field(..., description="平台账号 ID")
    account_name: Optional[str] = Field(default=None, description="账号名称")
    avatar_url: Optional[str] = Field(default=None, description="头像 URL")
    verified: bool = Field(default=False, description="是否认证")
    follower_count: Optional[int] = Field(default=None, description="粉丝数")

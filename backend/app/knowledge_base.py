from typing import Dict, List, Optional

# 专家知识库：结构化索引 (参考 Source 135, 18, 93)
EXPERT_KNOWLEDGE = [
    {
        "id": "source_135",
        "topic": "碳钒转化点 (Tc)",
        "content": "碳钒转化临界温度 Tc 为 1361℃ (1634 K)。当熔池温度超过此点时，碳氧化速率激增，钒氧化受到热力学抑制。建议在此点到达前 60s 补加生铁块或氧化铁皮，强制抑制温升。",
        "keywords": ["Tc", "1361", "转化点", "碳氧化"]
    },
    {
        "id": "source_18",
        "topic": "低硅策略下的枪位轨迹",
        "content": "对于 Si < 0.20% 的低硅铁水，应采用“低-高-低”枪位轨迹。前期低枪位 (900mm) 促进脱硅，中期拉高枪位 (1200mm) 增加渣中 TFe 含量以强化钒氧化界面反应，后期回落压温。",
        "keywords": ["低硅", "枪位", "轨迹", "TFe"]
    },
    {
        "id": "source_93",
        "topic": "冷却剂强度选择",
        "content": "当铁水 [V] > 0.30% 且 [Si] < 0.25% 时，应优先选择氧化铁皮而非弃渣球，以减少对钒渣品位的稀释，确保 V2O5 > 12.5%。",
        "keywords": ["冷却剂", "V2O5", "品位", "氧化铁皮"]
    }
]

def query_knowledge(query: str) -> List[Dict]:
    """简单的 RAG 检索模拟"""
    results = []
    query_lower = query.lower()
    for item in EXPERT_KNOWLEDGE:
        if any(kw.lower() in query_lower for kw in item["keywords"]) or item["topic"].lower() in query_lower:
            results.append(item)
    return results
